use std::{
    fs,
    io::Cursor,
    path::{Path, PathBuf},
};

use image::{DynamicImage, ImageBuffer, ImageFormat, Rgb};

fn write(root: &Path, relative: &str, bytes: &[u8]) {
    let path = root.join(relative);
    fs::create_dir_all(path.parent().expect("seed has parent")).expect("create corpus directory");
    fs::write(path, bytes).expect("write corpus seed");
}

fn encoded(width: u32, height: u32, format: ImageFormat) -> Vec<u8> {
    let image = DynamicImage::ImageRgb8(ImageBuffer::from_pixel(width, height, Rgb([17, 34, 51])));
    let mut output = Cursor::new(Vec::new());
    image
        .write_to(&mut output, format)
        .expect("encode corpus seed");
    output.into_inner()
}

fn main() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("corpus");
    write(
        &root,
        "ingest_decode/valid-1x1.png",
        &encoded(1, 1, ImageFormat::Png),
    );
    write(
        &root,
        "ingest_decode/valid-1x1.jpg",
        &encoded(1, 1, ImageFormat::Jpeg),
    );
    write(
        &root,
        "ingest_decode/truncated-png",
        b"\x89PNG\r\n\x1a\ntruncated",
    );
    write(
        &root,
        "ingest_decode/truncated-jpeg",
        b"\xff\xd8\xfftruncated",
    );
    write(
        &root,
        "ingest_decode/svg-active",
        b"<svg xmlns=\"http://www.w3.org/2000/svg\"><script>alert(1)</script></svg>",
    );
    write(&root, "ingest_decode/zip-magic", b"PK\x03\x04not-an-image");
    write(&root, "ingest_decode/elf-magic", b"\x7fELFnot-an-image");
    write(
        &root,
        "ingest_decode/png-oversize-dimensions",
        &encoded(4_097, 1, ImageFormat::Png),
    );
    write(
        &root,
        "ingest_decode/jpeg-malformed-segments",
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00malformed-segments",
    );

    write(
        &root,
        "canonical_path/canonical-png",
        b"uploads/00000000-0000-0000-0000-000000000000/00000000-0000-0000-0000-000000000000.png",
    );
    write(
        &root,
        "canonical_path/canonical-jpeg",
        b"uploads/ffffffff-ffff-4fff-8fff-ffffffffffff/ffffffff-ffff-4fff-8fff-ffffffffffff.jpg",
    );
    write(
        &root,
        "canonical_path/traversal",
        b"uploads/../../escape.png",
    );
    write(
        &root,
        "canonical_path/double-extension",
        b"uploads/00000000-0000-0000-0000-000000000000/00000000-0000-0000-0000-000000000000.png.php",
    );
    write(
        &root,
        "canonical_path/absolute",
        b"/uploads/00000000-0000-0000-0000-000000000000/00000000-0000-0000-0000-000000000000.png",
    );
    write(
        &root,
        "canonical_path/encoded-separator",
        b"uploads%2f00000000-0000-0000-0000-000000000000%2f00000000-0000-0000-0000-000000000000.png",
    );
    write(
        &root,
        "canonical_path/non-utf8",
        b"uploads/00000000-0000-0000-0000-000000000000/\xff.png",
    );
}
