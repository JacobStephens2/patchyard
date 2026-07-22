#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
cd "$REPO_ROOT"

scratch=$(mktemp -d)
cleanup() {
    [[ -n "$scratch" && "$scratch" == /tmp/* && -d "$scratch" ]] && rm -rf -- "$scratch"
}
trap cleanup EXIT

source_date_epoch=$(git show -s --format=%ct HEAD)
common_env=(env CARGO_INCREMENTAL=0 SOURCE_DATE_EPOCH="$source_date_epoch")

"${common_env[@]}" CARGO_TARGET_DIR="$scratch/build-a" \
    cargo build --locked --release -p factory-verify
"${common_env[@]}" CARGO_TARGET_DIR="$scratch/build-b" \
    cargo build --locked --release -p factory-verify

binary_a="$scratch/build-a/release/factory-verify"
binary_b="$scratch/build-b/release/factory-verify"
sha_a=$(sha256sum -- "$binary_a" | awk '{print $1}')
sha_b=$(sha256sum -- "$binary_b" | awk '{print $1}')
[[ "$sha_a" == "$sha_b" ]] || {
    echo "factory-verify release builds differ: $sha_a != $sha_b" >&2
    exit 1
}

# The debug build is a distinct, runnable prior version for the rollback drill.
cargo build --locked -p factory-verify
prior=target/debug/factory-verify
prior_sha=$(sha256sum -- "$prior" | awk '{print $1}')
[[ "$prior_sha" != "$sha_a" ]] || {
    echo "factory-verify install drill requires distinct prior and candidate binaries" >&2
    exit 1
}

mkdir "$scratch/install"
destination="$scratch/install/factory-verify"
rollback_copy="$scratch/install/factory-verify.rollback"
install -m 0755 -- "$prior" "$destination"
tools/install-factory-verify.sh install "$binary_a" "$sha_a" "$destination" "$rollback_copy"
[[ $(sha256sum -- "$destination" | awk '{print $1}') == "$sha_a" ]]
"$destination" --version >/dev/null
tools/install-factory-verify.sh rollback "$destination" "$rollback_copy" "$prior_sha"
[[ $(sha256sum -- "$destination" | awk '{print $1}') == "$prior_sha" ]]
"$destination" --version >/dev/null

echo "factory-verify reproducible SHA-256: $sha_a"
echo "factory-verify checksum install and rollback: pass"
