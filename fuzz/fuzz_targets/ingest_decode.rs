#![no_main]

use factory_web::upload::{
    MAX_CLEAN_BYTES, MAX_IMAGE_HEIGHT, MAX_IMAGE_WIDTH, MAX_UPLOAD_BYTES, sanitize_image_bytes,
    sniff_format,
};
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    // The production function has its own input bound. Avoid asking libFuzzer
    // to spend cycles growing inputs that can only take that fixed rejection.
    if data.len() > MAX_UPLOAD_BYTES + 1 {
        return;
    }
    if let Ok(clean) = sanitize_image_bytes(data) {
        assert!(clean.width > 0 && clean.width <= MAX_IMAGE_WIDTH);
        assert!(clean.height > 0 && clean.height <= MAX_IMAGE_HEIGHT);
        assert!(clean.bytes.len() <= MAX_CLEAN_BYTES);
        assert_eq!(sniff_format(&clean.bytes).ok(), Some(clean.format));
        assert!(sanitize_image_bytes(&clean.bytes).is_ok());
    }
});
