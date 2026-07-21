#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
source "$REPO_ROOT/tools/rust-tool-versions.env"

CARGO_BIN_HOME=${CARGO_HOME:-"$HOME/.cargo"}
RUSTUP="$CARGO_BIN_HOME/bin/rustup"

if [[ -x "$RUSTUP" ]] && "$RUSTUP" --version | grep -Fq "rustup $RUSTUP_INIT_VERSION "; then
  echo "rustup $RUSTUP_INIT_VERSION already installed"
else
  RUSTUP_TEMP=$(mktemp -d /tmp/patchyard-rustup.XXXXXX)
  trap 'rm -r -- "$RUSTUP_TEMP"' EXIT
  curl --fail --location --silent --show-error \
    --output "$RUSTUP_TEMP/rustup-init" "$RUSTUP_INIT_URL"
  printf '%s  %s\n' "$RUSTUP_INIT_SHA256" "$RUSTUP_TEMP/rustup-init" \
    | sha256sum --check
  chmod 0700 "$RUSTUP_TEMP/rustup-init"
  "$RUSTUP_TEMP/rustup-init" \
    -y --no-modify-path --profile minimal --default-toolchain none
fi

cd "$REPO_ROOT"
"$RUSTUP" show active-toolchain
"$RUSTUP" component list --installed | grep -Eq '^cargo-'
"$RUSTUP" component list --installed | grep -Eq '^clippy-'
"$RUSTUP" component list --installed | grep -Eq '^rustfmt-'
