#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "usage: $0 install <candidate> <candidate-sha256> <destination> <rollback-copy>" >&2
    echo "       $0 rollback <destination> <rollback-copy> <rollback-sha256>" >&2
    exit 64
}

verify_sha() {
    local path=$1
    local expected=$2
    local actual
    [[ "$expected" =~ ^[0-9a-f]{64}$ ]] || {
        echo "install-factory-verify: expected checksum is not canonical SHA-256" >&2
        exit 1
    }
    actual=$(sha256sum -- "$path" | awk '{print $1}')
    [[ "$actual" == "$expected" ]] || {
        echo "install-factory-verify: checksum mismatch for $path" >&2
        exit 1
    }
}

[[ $# -ge 1 ]] || usage
operation=$1
shift

case "$operation" in
    install)
        [[ $# -eq 4 ]] || usage
        candidate=$1
        candidate_sha=$2
        destination=$3
        rollback_copy=$4
        [[ -f "$candidate" && ! -L "$candidate" ]] || {
            echo "install-factory-verify: candidate must be a regular file" >&2
            exit 1
        }
        [[ -d "$(dirname -- "$destination")" ]] || {
            echo "install-factory-verify: destination directory does not exist" >&2
            exit 1
        }
        verify_sha "$candidate" "$candidate_sha"
        install -m 0755 -- "$candidate" "${destination}.next"
        verify_sha "${destination}.next" "$candidate_sha"
        if [[ -e "$destination" ]]; then
            [[ -f "$destination" && ! -L "$destination" ]] || {
                echo "install-factory-verify: existing destination is not a regular file" >&2
                exit 1
            }
            install -m 0755 -- "$destination" "${rollback_copy}.next"
            mv -f -- "${rollback_copy}.next" "$rollback_copy"
        fi
        mv -f -- "${destination}.next" "$destination"
        verify_sha "$destination" "$candidate_sha"
        ;;
    rollback)
        [[ $# -eq 3 ]] || usage
        destination=$1
        rollback_copy=$2
        rollback_sha=$3
        [[ -f "$rollback_copy" && ! -L "$rollback_copy" ]] || {
            echo "install-factory-verify: rollback copy must be a regular file" >&2
            exit 1
        }
        verify_sha "$rollback_copy" "$rollback_sha"
        install -m 0755 -- "$rollback_copy" "${destination}.next"
        verify_sha "${destination}.next" "$rollback_sha"
        mv -f -- "${destination}.next" "$destination"
        verify_sha "$destination" "$rollback_sha"
        ;;
    *)
        usage
        ;;
esac
