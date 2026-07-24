#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$REPO_ROOT/tools/rust-tool-versions.env"

ACTUAL_VERSION=$(cargo +"$CARGO_FUZZ_TOOLCHAIN" fuzz --version | awk '{print $2}')
if [[ "$ACTUAL_VERSION" != "$CARGO_FUZZ_VERSION" ]]; then
    echo "cargo-fuzz $CARGO_FUZZ_VERSION is required; found $ACTUAL_VERSION" >&2
    exit 1
fi

cd "$REPO_ROOT"
cargo +"$CARGO_FUZZ_TOOLCHAIN" fuzz run ingest_decode fuzz/corpus/ingest_decode -- \
    -max_len=8388609 -max_total_time=120
cargo +"$CARGO_FUZZ_TOOLCHAIN" fuzz run canonical_path fuzz/corpus/canonical_path -- \
    -max_len=4096 -max_total_time=120
