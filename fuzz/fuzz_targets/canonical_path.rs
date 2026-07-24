#![no_main]

use std::{ffi::OsStr, os::unix::ffi::OsStrExt as _, path::Path};

use factory_web::upload::CanonicalUploadPath;
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    let original = Path::new(OsStr::from_bytes(data));
    if let Some(canonical) = CanonicalUploadPath::parse(original) {
        let round_trip = canonical.relative_path();
        assert_eq!(round_trip.as_os_str().as_bytes(), data);
        assert!(!round_trip.is_absolute());
        assert_eq!(round_trip.components().count(), 3);
    }
});
