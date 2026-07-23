#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
source "$REPO_ROOT/tools/rust-tool-versions.env"

case "$(uname -s):$(uname -m)" in
  Linux:x86_64) ;;
  *)
    echo "Pinned tokei source build supports Linux x86_64 CI only" >&2
    exit 1
    ;;
esac

CARGO_BIN_HOME=${CARGO_HOME:-"$HOME/.cargo"}
TOKEI_BINARY="$CARGO_BIN_HOME/bin/tokei"
if [[ -x "$TOKEI_BINARY" ]] \
  && [[ "$("$TOKEI_BINARY" --version | awk '{print $2}')" == "$TOKEI_VERSION" ]]; then
  "$TOKEI_BINARY" --version
  exit 0
fi

TOKEI_TEMP=$(mktemp -d /tmp/patchyard-tokei.XXXXXX)
trap 'rm -r -- "$TOKEI_TEMP"' EXIT
TOKEI_CRATE="$TOKEI_TEMP/tokei-$TOKEI_VERSION.crate"
curl --fail --location --silent --show-error \
  --output "$TOKEI_CRATE" "$TOKEI_CRATE_URL"
printf '%s  %s\n' "$TOKEI_CRATE_SHA256" "$TOKEI_CRATE" | sha256sum --check
tar -xf "$TOKEI_CRATE" -C "$TOKEI_TEMP"
cargo install --locked --path "$TOKEI_TEMP/tokei-$TOKEI_VERSION"
"$TOKEI_BINARY" --version
