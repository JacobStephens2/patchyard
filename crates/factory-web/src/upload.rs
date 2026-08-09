//! Fail-closed screenshot neutralization and trusted-base-fd storage.
//!
//! Uploaded bytes and RFC 7578 metadata are untrusted under F2. Only decoded
//! pixels cross this module's neutralization boundary; originals are never
//! written to disk.

use std::{
    fs::File,
    future::Future,
    io::{self, Cursor, Read as _, Write},
    os::fd::OwnedFd,
    os::unix::ffi::OsStrExt as _,
    path::{Component, Path, PathBuf},
    sync::Arc,
    time::Duration,
};

use image::{
    DynamicImage, ExtendedColorType, ImageEncoder as _, ImageFormat, ImageReader, Limits,
    codecs::{
        jpeg::JpegEncoder,
        png::{CompressionType, FilterType, PngEncoder},
    },
};
use rustix::{
    fs::{
        AtFlags, FileType, Mode, OFlags, RenameFlags, fstat, fsync, mkdirat, open, openat,
        renameat_with, unlinkat,
    },
    io::Errno,
};
use sha2::{Digest as _, Sha256};
use tokio::sync::Semaphore;
use uuid::Uuid;

pub const MAX_MULTIPART_BYTES: usize = MAX_UPLOAD_BYTES + 128 * 1024;
pub const MAX_UPLOAD_BYTES: usize = 8 * 1024 * 1024;
pub const MAX_UPLOAD_FILES: usize = 2;
pub const UPLOAD_ACCEPT: &str = ".png,.jpg,.jpeg,image/png,image/jpeg";
pub const MAX_CLEAN_BYTES: usize = 32 * 1024 * 1024;
pub const MAX_IMAGE_WIDTH: u32 = 4_096;
pub const MAX_IMAGE_HEIGHT: u32 = 4_096;
pub const MAX_IMAGE_PIXELS: u64 = 16_777_216;
pub const MAX_DECODER_ALLOC: u64 = 128 * 1024 * 1024;
pub const MAX_CONCURRENT_DECODES: usize = 2;
pub const DECODE_TIMEOUT: Duration = Duration::from_secs(2);
const DECODE_QUEUE_TIMEOUT: Duration = Duration::from_secs(1);
const UPLOAD_ROOT_NAME: &str = "uploads";
const PENDING_NAME: &str = ".pending";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CleanFormat {
    Png,
    Jpeg,
}

impl CleanFormat {
    pub const fn extension(self) -> &'static str {
        match self {
            Self::Png => "png",
            Self::Jpeg => "jpg",
        }
    }

    pub const fn content_type(self) -> &'static str {
        match self {
            Self::Png => "image/png",
            Self::Jpeg => "image/jpeg",
        }
    }

    fn image_format(self) -> ImageFormat {
        match self {
            Self::Png => ImageFormat::Png,
            Self::Jpeg => ImageFormat::Jpeg,
        }
    }
}

#[derive(Debug)]
pub struct CleanImage {
    pub bytes: Vec<u8>,
    pub format: CleanFormat,
    pub width: u32,
    pub height: u32,
    pub sha256: [u8; 32],
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CanonicalUploadPath {
    pub id: Uuid,
    pub format: CleanFormat,
}

impl CanonicalUploadPath {
    pub fn new(id: Uuid, format: CleanFormat) -> Self {
        Self { id, format }
    }

    pub fn relative_path(&self) -> PathBuf {
        let id = self.id.to_string();
        PathBuf::from(UPLOAD_ROOT_NAME)
            .join(&id)
            .join(format!("{id}.{}", self.format.extension()))
    }

    pub fn parse(path: &Path) -> Option<Self> {
        if path.is_absolute() {
            return None;
        }
        let components = path.components().collect::<Vec<_>>();
        let [
            Component::Normal(root),
            Component::Normal(directory),
            Component::Normal(file),
        ] = components.as_slice()
        else {
            return None;
        };
        if root.to_str()? != UPLOAD_ROOT_NAME {
            return None;
        }
        let directory = directory.to_str()?;
        let id = Uuid::parse_str(directory).ok()?;
        if directory != id.to_string() {
            return None;
        }
        for format in [CleanFormat::Png, CleanFormat::Jpeg] {
            if file.to_str()? == format!("{directory}.{}", format.extension()) {
                let canonical = Self { id, format };
                return (path.as_os_str().as_bytes()
                    == canonical.relative_path().as_os_str().as_bytes())
                .then_some(canonical);
            }
        }
        None
    }
}

#[derive(Debug, thiserror::Error)]
pub enum UploadError {
    #[error("only PNG and JPEG screenshots are accepted")]
    UnsupportedType,
    #[error("image dimensions exceed {MAX_IMAGE_WIDTH}x{MAX_IMAGE_HEIGHT}")]
    Dimensions,
    #[error("screenshots exceed the per-request decoded-pixel ceiling")]
    RequestPixels,
    #[error("image decode or clean re-encode failed")]
    InvalidImage,
    #[error("clean image exceeds {MAX_CLEAN_BYTES} bytes")]
    CleanImageTooLarge,
    #[error("image decode exceeded the wall-clock limit")]
    DecodeTimeout,
    #[error("image decoder capacity is temporarily exhausted")]
    DecodeBusy,
    #[error("blocking image task failed")]
    BlockingTask,
    #[error("upload path is not canonical")]
    InvalidPath,
    #[error("upload filesystem object is not a private one-link regular file")]
    UnsafeFilesystemObject,
    #[error("upload storage is full")]
    DiskFull,
    #[error("upload storage operation failed: {0}")]
    Io(#[source] io::Error),
}

#[derive(Debug, thiserror::Error)]
#[error("screenshot {index} failed neutralization: {source}")]
pub struct BatchUploadError {
    pub index: usize,
    #[source]
    pub source: UploadError,
}

impl UploadError {
    fn from_errno(error: Errno) -> Self {
        if error == Errno::NOSPC {
            Self::DiskFull
        } else {
            Self::Io(io::Error::from_raw_os_error(error.raw_os_error()))
        }
    }

    fn from_io(error: io::Error) -> Self {
        if error.raw_os_error() == Some(Errno::NOSPC.raw_os_error()) {
            Self::DiskFull
        } else if error.kind() == io::ErrorKind::WriteZero {
            Self::CleanImageTooLarge
        } else {
            Self::Io(error)
        }
    }
}

pub fn sniff_format(bytes: &[u8]) -> Result<CleanFormat, UploadError> {
    const PNG: &[u8; 8] = b"\x89PNG\r\n\x1a\n";
    if bytes.starts_with(PNG) {
        Ok(CleanFormat::Png)
    } else if bytes.starts_with(&[0xff, 0xd8, 0xff]) {
        Ok(CleanFormat::Jpeg)
    } else {
        Err(UploadError::UnsupportedType)
    }
}

/// Decode with explicit limits and re-encode pixels without metadata.
///
/// The async route calls this only through [`sanitize_image_timed`]. It is
/// public so the ingest fuzz target exercises the production implementation.
pub fn sanitize_image_bytes(bytes: &[u8]) -> Result<CleanImage, UploadError> {
    sanitize_image_bytes_with_limits(bytes, MAX_IMAGE_PIXELS, MAX_CLEAN_BYTES)
}

fn sanitize_image_bytes_with_limits(
    bytes: &[u8],
    pixel_limit: u64,
    clean_byte_limit: usize,
) -> Result<CleanImage, UploadError> {
    if bytes.len() > MAX_UPLOAD_BYTES {
        return Err(UploadError::UnsupportedType);
    }
    let format = sniff_format(bytes)?;
    let mut dimension_reader = ImageReader::with_format(Cursor::new(bytes), format.image_format());
    dimension_reader.limits(decoder_limits());
    let (width, height) = dimension_reader
        .into_dimensions()
        .map_err(map_decode_error)?;
    validate_dimensions(width, height, pixel_limit)?;

    let mut reader = ImageReader::with_format(Cursor::new(bytes), format.image_format());
    reader.limits(decoder_limits());
    let image = reader.decode().map_err(map_decode_error)?;
    let width = image.width();
    let height = image.height();
    validate_dimensions(width, height, pixel_limit)?;

    let mut output = BoundedWriter::new(clean_byte_limit);
    match format {
        CleanFormat::Png => encode_png(&image, &mut output)?,
        CleanFormat::Jpeg => encode_jpeg(&image, &mut output)?,
    }
    let bytes = output.finish();
    let sha256 = Sha256::digest(&bytes).into();
    Ok(CleanImage {
        bytes,
        format,
        width,
        height,
        sha256,
    })
}

fn decoder_limits() -> Limits {
    let mut limits = Limits::no_limits();
    limits.max_image_width = Some(MAX_IMAGE_WIDTH);
    limits.max_image_height = Some(MAX_IMAGE_HEIGHT);
    limits.max_alloc = Some(MAX_DECODER_ALLOC);
    limits
}

fn validate_dimensions(width: u32, height: u32, pixel_limit: u64) -> Result<(), UploadError> {
    if width == 0 || height == 0 || width > MAX_IMAGE_WIDTH || height > MAX_IMAGE_HEIGHT {
        return Err(UploadError::Dimensions);
    }
    let pixels = u64::from(width) * u64::from(height);
    if pixels > MAX_IMAGE_PIXELS {
        return Err(UploadError::Dimensions);
    }
    if pixels > pixel_limit {
        return Err(UploadError::RequestPixels);
    }
    Ok(())
}

fn map_decode_error(error: image::ImageError) -> UploadError {
    if matches!(
        error,
        image::ImageError::Limits(image::error::LimitError { .. })
    ) {
        UploadError::Dimensions
    } else {
        UploadError::InvalidImage
    }
}

pub async fn sanitize_image_timed(
    bytes: Vec<u8>,
    decode_slots: Arc<Semaphore>,
) -> Result<CleanImage, UploadError> {
    sanitize_image_timed_with_limits(bytes, decode_slots, MAX_IMAGE_PIXELS, MAX_CLEAN_BYTES).await
}

async fn sanitize_image_timed_with_limits(
    bytes: Vec<u8>,
    decode_slots: Arc<Semaphore>,
    pixel_limit: u64,
    clean_byte_limit: usize,
) -> Result<CleanImage, UploadError> {
    // Classify before consuming a blocking slot. This is a fixed-prefix check,
    // not a decoder and not authority derived from multipart metadata.
    sniff_format(&bytes)?;
    let permit = tokio::time::timeout(DECODE_QUEUE_TIMEOUT, decode_slots.acquire_owned())
        .await
        .map_err(|_| UploadError::DecodeBusy)?
        .map_err(|_| UploadError::DecodeBusy)?;
    let task = tokio::task::spawn_blocking(move || {
        // The permit stays with the blocking job even if the request timeout
        // drops its JoinHandle; detached timed-out work cannot exceed the
        // declared concurrency.
        let _permit = permit;
        sanitize_image_bytes_with_limits(&bytes, pixel_limit, clean_byte_limit)
    });
    tokio::time::timeout(DECODE_TIMEOUT, task)
        .await
        .map_err(|_| UploadError::DecodeTimeout)?
        .map_err(|_| UploadError::BlockingTask)?
}

/// Neutralize a request's screenshots serially under the shared decode bound.
///
/// Awaiting each decode before starting the next prevents one request from
/// occupying more than one of the global decode slots. Cumulative decoded
/// pixels and clean output are capped at the bounds previously available to
/// one screenshot.
pub async fn sanitize_images_timed(
    originals: Vec<Vec<u8>>,
    decode_slots: Arc<Semaphore>,
) -> Result<Vec<CleanImage>, BatchUploadError> {
    sanitize_images_timed_with_limits(originals, decode_slots, MAX_IMAGE_PIXELS, MAX_CLEAN_BYTES)
        .await
}

async fn sanitize_images_timed_with_limits(
    originals: Vec<Vec<u8>>,
    decode_slots: Arc<Semaphore>,
    pixel_limit: u64,
    clean_byte_limit: usize,
) -> Result<Vec<CleanImage>, BatchUploadError> {
    let (images, _, _) = try_fold_serial(
        originals,
        (Vec::new(), 0_usize, 0_u64),
        move |(mut images, clean_bytes, pixels), bytes| {
            let decode_slots = Arc::clone(&decode_slots);
            async move {
                let remaining_pixels = pixel_limit
                    .checked_sub(pixels)
                    .ok_or(UploadError::RequestPixels)?;
                let remaining_clean_bytes = clean_byte_limit
                    .checked_sub(clean_bytes)
                    .filter(|remaining| *remaining > 0)
                    .ok_or(UploadError::CleanImageTooLarge)?;
                let image = sanitize_image_timed_with_limits(
                    bytes,
                    decode_slots,
                    remaining_pixels,
                    remaining_clean_bytes,
                )
                .await?;
                let clean_bytes = clean_bytes
                    .checked_add(image.bytes.len())
                    .filter(|total| *total <= clean_byte_limit)
                    .ok_or(UploadError::CleanImageTooLarge)?;
                let pixels = pixels
                    .checked_add(u64::from(image.width) * u64::from(image.height))
                    .filter(|total| *total <= pixel_limit)
                    .ok_or(UploadError::RequestPixels)?;
                images.push(image);
                Ok((images, clean_bytes, pixels))
            }
        },
    )
    .await
    .map_err(|(index, source)| BatchUploadError { index, source })?;
    Ok(images)
}

async fn try_fold_serial<T, S, E, F, Fut>(
    items: impl IntoIterator<Item = T>,
    mut state: S,
    mut step: F,
) -> Result<S, (usize, E)>
where
    F: FnMut(S, T) -> Fut,
    Fut: Future<Output = Result<S, E>>,
{
    for (index, item) in items.into_iter().enumerate() {
        state = step(state, item).await.map_err(|error| (index, error))?;
    }
    Ok(state)
}

fn encode_png(image: &DynamicImage, output: &mut BoundedWriter) -> Result<(), UploadError> {
    let pixels = image.to_rgba8();
    // A fixed filter preserves the neutralization boundary while avoiding the
    // adaptive filter's per-row search inside the wall-clock decode budget.
    let result = PngEncoder::new_with_quality(&mut *output, CompressionType::Fast, FilterType::Sub)
        .write_image(
            pixels.as_raw(),
            image.width(),
            image.height(),
            ExtendedColorType::Rgba8,
        );
    encode_result(result, output)
}

fn encode_jpeg(image: &DynamicImage, output: &mut BoundedWriter) -> Result<(), UploadError> {
    let pixels = image.to_rgb8();
    let result = JpegEncoder::new_with_quality(&mut *output, 90).write_image(
        pixels.as_raw(),
        image.width(),
        image.height(),
        ExtendedColorType::Rgb8,
    );
    encode_result(result, output)
}

fn encode_result(
    result: Result<(), image::ImageError>,
    output: &BoundedWriter,
) -> Result<(), UploadError> {
    if output.limit_exceeded {
        Err(UploadError::CleanImageTooLarge)
    } else {
        result.map_err(map_encode_error)
    }
}

fn map_encode_error(error: image::ImageError) -> UploadError {
    match error {
        image::ImageError::IoError(error) if error.kind() == io::ErrorKind::WriteZero => {
            UploadError::CleanImageTooLarge
        }
        _ => UploadError::InvalidImage,
    }
}

struct BoundedWriter {
    bytes: Vec<u8>,
    maximum: usize,
    limit_exceeded: bool,
}

impl BoundedWriter {
    fn new(maximum: usize) -> Self {
        Self {
            bytes: Vec::new(),
            maximum,
            limit_exceeded: false,
        }
    }

    fn finish(self) -> Vec<u8> {
        self.bytes
    }
}

impl Write for BoundedWriter {
    fn write(&mut self, buffer: &[u8]) -> io::Result<usize> {
        if buffer.len() > self.maximum.saturating_sub(self.bytes.len()) {
            self.limit_exceeded = true;
            return Err(io::Error::new(
                io::ErrorKind::WriteZero,
                "clean image output limit reached",
            ));
        }
        self.bytes.extend_from_slice(buffer);
        Ok(buffer.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

#[derive(Clone)]
pub struct UploadStorage {
    root: Arc<OwnedFd>,
}

impl UploadStorage {
    /// Open the Ansible-provisioned 0700 root once and retain its descriptor.
    pub fn open(artifact_root: &Path) -> Result<Self, UploadError> {
        let path = artifact_root.join(UPLOAD_ROOT_NAME);
        let root = open(
            &path,
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )
        .map_err(UploadError::from_errno)?;
        let stat = fstat(&root).map_err(UploadError::from_errno)?;
        if !FileType::from_raw_mode(stat.st_mode).is_dir()
            || Mode::from_raw_mode(stat.st_mode).bits() & 0o077 != 0
        {
            return Err(UploadError::UnsafeFilesystemObject);
        }
        Ok(Self {
            root: Arc::new(root),
        })
    }

    pub fn store(&self, id: Uuid, image: &CleanImage) -> Result<PathBuf, UploadError> {
        let canonical = CanonicalUploadPath::new(id, image.format);
        let directory_name = id.to_string();
        mkdirat(&self.root, &directory_name, Mode::RWXU).map_err(UploadError::from_errno)?;
        let directory = match self.open_directory(&directory_name) {
            Ok(value) => value,
            Err(error) => {
                let _ = unlinkat(&self.root, &directory_name, AtFlags::REMOVEDIR);
                return Err(error);
            }
        };
        let final_name = format!("{directory_name}.{}", image.format.extension());
        let result = self.write_and_publish(&directory, &final_name, &image.bytes);
        if let Err(error) = result {
            let _ = unlinkat(&directory, PENDING_NAME, AtFlags::empty());
            let _ = unlinkat(&directory, &final_name, AtFlags::empty());
            let _ = fsync(&directory);
            let _ = unlinkat(&self.root, &directory_name, AtFlags::REMOVEDIR);
            return Err(error);
        }
        Ok(canonical.relative_path())
    }

    pub fn read(
        &self,
        expected_id: Uuid,
        relative_path: &Path,
    ) -> Result<(Vec<u8>, CleanFormat), UploadError> {
        let canonical =
            CanonicalUploadPath::parse(relative_path).ok_or(UploadError::InvalidPath)?;
        if canonical.id != expected_id {
            return Err(UploadError::InvalidPath);
        }
        let directory_name = canonical.id.to_string();
        let directory = self.open_directory(&directory_name)?;
        let file_name = format!("{directory_name}.{}", canonical.format.extension());
        let fd = openat(
            &directory,
            &file_name,
            OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )
        .map_err(UploadError::from_errno)?;
        enforce_private_regular(&fd)?;
        let mut file = File::from(fd);
        let mut bytes = Vec::new();
        std::io::Read::by_ref(&mut file)
            .take((MAX_CLEAN_BYTES + 1) as u64)
            .read_to_end(&mut bytes)
            .map_err(UploadError::from_io)?;
        if bytes.len() > MAX_CLEAN_BYTES {
            return Err(UploadError::CleanImageTooLarge);
        }
        Ok((bytes, canonical.format))
    }

    /// Fallible cleanup used whenever database registration fails closed.
    pub fn remove(&self, id: Uuid, relative_path: &Path) -> Result<(), UploadError> {
        let canonical =
            CanonicalUploadPath::parse(relative_path).ok_or(UploadError::InvalidPath)?;
        if canonical.id != id {
            return Err(UploadError::InvalidPath);
        }
        let directory_name = id.to_string();
        let directory = self.open_directory(&directory_name)?;
        let file_name = format!("{directory_name}.{}", canonical.format.extension());
        unlinkat(&directory, &file_name, AtFlags::empty()).map_err(UploadError::from_errno)?;
        fsync(&directory).map_err(UploadError::from_errno)?;
        unlinkat(&self.root, &directory_name, AtFlags::REMOVEDIR)
            .map_err(UploadError::from_errno)?;
        fsync(&self.root).map_err(UploadError::from_errno)?;
        Ok(())
    }

    fn open_directory(&self, name: &str) -> Result<OwnedFd, UploadError> {
        let directory = openat(
            &self.root,
            name,
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )
        .map_err(UploadError::from_errno)?;
        let stat = fstat(&directory).map_err(UploadError::from_errno)?;
        if !FileType::from_raw_mode(stat.st_mode).is_dir()
            || Mode::from_raw_mode(stat.st_mode).bits() & 0o077 != 0
        {
            return Err(UploadError::UnsafeFilesystemObject);
        }
        Ok(directory)
    }

    fn write_and_publish(
        &self,
        directory: &OwnedFd,
        final_name: &str,
        bytes: &[u8],
    ) -> Result<(), UploadError> {
        let fd = openat(
            directory,
            PENDING_NAME,
            OFlags::WRONLY | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::RUSR | Mode::WUSR,
        )
        .map_err(UploadError::from_errno)?;
        enforce_private_regular(&fd)?;
        let mut file = File::from(fd);
        file.write_all(bytes).map_err(UploadError::from_io)?;
        file.sync_all().map_err(UploadError::from_io)?;
        drop(file);
        renameat_with(
            directory,
            PENDING_NAME,
            directory,
            final_name,
            RenameFlags::NOREPLACE,
        )
        .map_err(UploadError::from_errno)?;
        fsync(directory).map_err(UploadError::from_errno)?;
        Ok(())
    }
}

fn enforce_private_regular(fd: &OwnedFd) -> Result<(), UploadError> {
    let stat = fstat(fd).map_err(UploadError::from_errno)?;
    if !FileType::from_raw_mode(stat.st_mode).is_file()
        || stat.st_nlink != 1
        || Mode::from_raw_mode(stat.st_mode).bits() & 0o177 != 0
    {
        return Err(UploadError::UnsafeFilesystemObject);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::{
        fs,
        os::unix::fs::{PermissionsExt as _, symlink},
        sync::atomic::{AtomicUsize, Ordering},
        time::Duration,
    };

    use image::{ImageBuffer, Rgb};
    use tempfile::TempDir;

    use super::*;

    fn encoded(format: CleanFormat) -> Vec<u8> {
        let image = DynamicImage::ImageRgb8(ImageBuffer::from_pixel(1, 1, Rgb([1, 2, 3])));
        let mut output = Cursor::new(Vec::new());
        image
            .write_to(&mut output, format.image_format())
            .expect("fixture should encode");
        output.into_inner()
    }

    fn storage() -> (TempDir, UploadStorage) {
        let temporary = tempfile::tempdir().expect("temporary root");
        let root = temporary.path().join(UPLOAD_ROOT_NAME);
        fs::create_dir(&root).expect("upload root");
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).expect("private root");
        let storage = UploadStorage::open(temporary.path()).expect("storage should open");
        (temporary, storage)
    }

    #[test]
    fn magic_allowlist_and_reencode_accept_only_png_and_jpeg() {
        for format in [CleanFormat::Png, CleanFormat::Jpeg] {
            let source = encoded(format);
            let clean = sanitize_image_bytes(&source).expect("valid fixture");
            assert_eq!(clean.format, format);
            assert_eq!((clean.width, clean.height), (1, 1));
            assert_eq!(sniff_format(&clean.bytes).expect("clean magic"), format);
        }
        for active in [
            b"<svg xmlns='http://www.w3.org/2000/svg'/>".as_slice(),
            b"PK\x03\x04archive".as_slice(),
            b"\x7fELFbinary".as_slice(),
            b"#!/bin/sh".as_slice(),
        ] {
            assert!(matches!(
                sanitize_image_bytes(active),
                Err(UploadError::UnsupportedType)
            ));
        }
    }

    #[test]
    fn reencode_drops_trailing_polyglot_bytes() {
        let mut source = encoded(CleanFormat::Png);
        source.extend_from_slice(b"<script>alert(1)</script>");
        let clean = sanitize_image_bytes(&source).expect("pixels remain valid");
        assert!(
            !clean
                .bytes
                .windows(b"<script>".len())
                .any(|window| window == b"<script>")
        );
        assert!(clean.bytes.len() < source.len());
    }

    #[test]
    fn canonical_path_parser_has_exact_shape() {
        let id = Uuid::new_v4();
        for format in [CleanFormat::Png, CleanFormat::Jpeg] {
            let canonical = CanonicalUploadPath::new(id, format);
            assert_eq!(
                CanonicalUploadPath::parse(&canonical.relative_path()),
                Some(canonical)
            );
        }
        for path in [
            "../escape.png",
            "/absolute.png",
            "uploads/../../escape.png",
            "uploads/not-a-uuid/file.png",
            "uploads/00000000-0000-0000-0000-000000000000/file.png.php",
            "uploads/00000000-0000-0000-0000-000000000000/other.png",
            "uploads/ffffffff-ffff-4fff-8fff-ffffffffffff//ffffffff-ffff-4fff-8fff-ffffffffffff.jpg",
            "uploads/ffffffff-ffff-4fff-8fff-ffffffffffff/ffffffff-ffff-4fff-8fff-ffffffffffff.jpg/",
        ] {
            assert!(CanonicalUploadPath::parse(Path::new(path)).is_none());
        }
    }

    #[test]
    fn storage_round_trip_uses_private_uuid_only_objects() {
        let (temporary, storage) = storage();
        let id = Uuid::new_v4();
        let clean = sanitize_image_bytes(&encoded(CleanFormat::Png)).expect("clean fixture");
        let relative = storage.store(id, &clean).expect("store");
        let (bytes, format) = storage.read(id, &relative).expect("read");
        assert_eq!(format, CleanFormat::Png);
        assert_eq!(Sha256::digest(&bytes).as_slice(), clean.sha256.as_slice());
        let directory = temporary.path().join(UPLOAD_ROOT_NAME).join(id.to_string());
        assert_eq!(
            fs::metadata(&directory)
                .expect("directory")
                .permissions()
                .mode()
                & 0o777,
            0o700
        );
        assert_eq!(
            fs::metadata(temporary.path().join(&relative))
                .expect("file")
                .permissions()
                .mode()
                & 0o777,
            0o600
        );
        storage.remove(id, &relative).expect("cleanup");
        assert!(!directory.exists());
    }

    #[test]
    fn storage_refuses_symlinked_upload_directory() {
        let (temporary, storage) = storage();
        let id = Uuid::new_v4();
        let outside = tempfile::tempdir().expect("outside");
        symlink(
            outside.path(),
            temporary.path().join(UPLOAD_ROOT_NAME).join(id.to_string()),
        )
        .expect("symlink fixture");
        let clean = sanitize_image_bytes(&encoded(CleanFormat::Png)).expect("clean fixture");
        assert!(storage.store(id, &clean).is_err());
        assert!(
            fs::read_dir(outside.path())
                .expect("outside readable")
                .next()
                .is_none()
        );
    }

    #[test]
    fn storage_refuses_hardlinked_clean_file() {
        let (temporary, storage) = storage();
        let id = Uuid::new_v4();
        let clean = sanitize_image_bytes(&encoded(CleanFormat::Png)).expect("clean fixture");
        let relative = storage.store(id, &clean).expect("store");
        let linked = temporary.path().join("unexpected-hardlink.png");
        fs::hard_link(temporary.path().join(&relative), &linked).expect("hardlink fixture");
        assert!(matches!(
            storage.read(id, &relative),
            Err(UploadError::UnsafeFilesystemObject)
        ));
        fs::remove_file(linked).expect("remove hardlink fixture");
        storage.remove(id, &relative).expect("cleanup");
    }

    #[test]
    fn disk_full_is_a_distinct_fail_closed_error() {
        assert!(matches!(
            UploadError::from_io(io::Error::from_raw_os_error(Errno::NOSPC.raw_os_error())),
            UploadError::DiskFull
        ));
    }

    #[tokio::test]
    async fn screenshot_batches_decode_serially_and_report_the_failing_index() {
        let active = Arc::new(AtomicUsize::new(0));
        let peak = Arc::new(AtomicUsize::new(0));
        let observed = try_fold_serial([0, 1], Vec::new(), {
            let active = Arc::clone(&active);
            let peak = Arc::clone(&peak);
            move |mut observed, item| {
                let active = Arc::clone(&active);
                let peak = Arc::clone(&peak);
                async move {
                    let now = active.fetch_add(1, Ordering::SeqCst) + 1;
                    peak.fetch_max(now, Ordering::SeqCst);
                    tokio::time::sleep(Duration::from_millis(10)).await;
                    active.fetch_sub(1, Ordering::SeqCst);
                    observed.push(item);
                    Ok::<_, UploadError>(observed)
                }
            }
        })
        .await
        .expect("serial fold");
        assert_eq!(observed, [0, 1]);
        assert_eq!(peak.load(Ordering::SeqCst), 1);

        let valid = encoded(CleanFormat::Png);
        let malformed = b"\x89PNG\r\n\x1a\nmalformed".to_vec();
        let slots = Arc::new(Semaphore::new(MAX_CONCURRENT_DECODES));
        let error = sanitize_images_timed(vec![valid.clone(), malformed], Arc::clone(&slots))
            .await
            .expect_err("second screenshot must fail");
        assert_eq!(error.index, 1);
        assert!(matches!(error.source, UploadError::InvalidImage));
        assert_eq!(slots.available_permits(), MAX_CONCURRENT_DECODES);

        let error = sanitize_images_timed_with_limits(
            vec![valid.clone(), valid],
            Arc::clone(&slots),
            1,
            MAX_CLEAN_BYTES,
        )
        .await
        .expect_err("the second pixel must exceed the request budget");
        assert_eq!(error.index, 1);
        assert!(matches!(error.source, UploadError::RequestPixels));
        assert_eq!(slots.available_permits(), MAX_CONCURRENT_DECODES);

        let valid = encoded(CleanFormat::Png);
        let one_clean_image = sanitize_image_bytes(&valid)
            .expect("clean fixture")
            .bytes
            .len();
        let error = sanitize_images_timed_with_limits(
            vec![valid.clone(), valid],
            Arc::clone(&slots),
            MAX_IMAGE_PIXELS,
            one_clean_image,
        )
        .await
        .expect_err("the second clean image must exceed the request budget");
        assert_eq!(error.index, 1);
        assert!(matches!(error.source, UploadError::CleanImageTooLarge));
        assert_eq!(slots.available_permits(), MAX_CONCURRENT_DECODES);
    }
}
