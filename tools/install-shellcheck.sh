#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
source "$REPO_ROOT/infra/tool-versions.env"

case "$(uname -s):$(uname -m)" in
  Linux:x86_64) ;;
  *)
    echo "Pinned ShellCheck supports Linux x86_64 CI only" >&2
    exit 1
    ;;
esac

SHELLCHECK_BIN_DIR=${SHELLCHECK_BIN_DIR:-"$HOME/.local/bin"}
SHELLCHECK_BINARY="$SHELLCHECK_BIN_DIR/shellcheck"
if [[ -x "$SHELLCHECK_BINARY" ]] \
  && [[ "$("$SHELLCHECK_BINARY" --version |
    awk '$1 == "version:" { print $2 }')" == "$SHELLCHECK_VERSION" ]]; then
  "$SHELLCHECK_BINARY" --version
  exit 0
fi

SHELLCHECK_TEMP=$(mktemp -d /tmp/patchyard-shellcheck.XXXXXX)
trap 'rm -r -- "$SHELLCHECK_TEMP"' EXIT
SHELLCHECK_ARCHIVE="$SHELLCHECK_TEMP/shellcheck.tar.xz"
curl --fail --location --silent --show-error \
  --output "$SHELLCHECK_ARCHIVE" "$SHELLCHECK_URL"
printf '%s  %s\n' "$SHELLCHECK_SHA256" "$SHELLCHECK_ARCHIVE" |
  sha256sum --check
tar -xJf "$SHELLCHECK_ARCHIVE" -C "$SHELLCHECK_TEMP"
install -d -m 0755 "$SHELLCHECK_BIN_DIR"
install -m 0755 \
  "$SHELLCHECK_TEMP/shellcheck-v$SHELLCHECK_VERSION/shellcheck" \
  "$SHELLCHECK_BINARY"
"$SHELLCHECK_BINARY" --version
