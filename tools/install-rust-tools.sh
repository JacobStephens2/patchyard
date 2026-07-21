#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
source "$REPO_ROOT/tools/rust-tool-versions.env"

case "$(uname -s):$(uname -m)" in
  Linux:x86_64) ;;
  *)
    echo "Pinned cargo-audit/cargo-deny archives support Linux x86_64 only" >&2
    exit 1
    ;;
esac

CARGO_BIN_HOME=${CARGO_HOME:-"$HOME/.cargo"}
install -d -m 0755 "$CARGO_BIN_HOME/bin"

TOOLS_TEMP=$(mktemp -d /tmp/patchyard-rust-tools.XXXXXX)
trap 'rm -r -- "$TOOLS_TEMP"' EXIT

install_archive() {
  local binary=$1 version=$2 url=$3 sha256=$4 member=$5
  local destination="$CARGO_BIN_HOME/bin/$binary"

  if [[ -x "$destination" ]] && "$destination" --version | grep -Fq " $version"; then
    echo "$binary $version already installed"
    return
  fi

  local archive="$TOOLS_TEMP/$binary.tgz"
  curl --fail --location --silent --show-error --output "$archive" "$url"
  printf '%s  %s\n' "$sha256" "$archive" | sha256sum --check
  tar -xzf "$archive" -C "$TOOLS_TEMP" "$member"
  install -m 0755 "$TOOLS_TEMP/$member" "$destination"
  "$destination" --version
}

install_archive \
  cargo-audit "$CARGO_AUDIT_VERSION" "$CARGO_AUDIT_URL" \
  "$CARGO_AUDIT_SHA256" "$CARGO_AUDIT_MEMBER"
install_archive \
  cargo-deny "$CARGO_DENY_VERSION" "$CARGO_DENY_URL" \
  "$CARGO_DENY_SHA256" "$CARGO_DENY_MEMBER"
