#!/usr/bin/env bash
# Deploy this repository to the factory control plane.
#
# /opt/patchyard holds no git credentials: its remote is HTTPS with no helper,
# no netrc and no key, so `git fetch origin` there fails and the checkout cannot
# update itself. Every deploy so far has been improvised by hand - build an
# incremental bundle, scp it, fetch from the file - which is how a stale
# revision goes unnoticed and how a deploy lands mid-run.
#
# This encodes that sequence, and the three refusals that matter:
#
#   1. Fast-forward only. A target that is not a descendant of the deployed
#      revision would silently roll the control plane backwards or sideways.
#   2. Clean tree only. A dirty checkout means someone edited in place; the
#      diff is theirs and a checkout would discard it.
#   3. No attended run in flight. A collector waiting on a prompt validated
#      the checkout during its preflight. Changing it underneath the run makes
#      the record describe a revision that is no longer there - and if the run
#      holds an open mutation window, the operator loses the instructions for
#      closing it.
#
# Git in /opt/patchyard must run as the owning account. Git refuses a
# repository whose owner is not the calling user, root included, so every
# remote git call goes through `sudo -u factory-manager`. The failure is
# "detected dubious ownership", which reads like drift and is not.
set -euo pipefail

HOST=${DEPLOY_HOST:-factory.example.com}
SSH_USER=${DEPLOY_SSH_USER:-conductor}
REMOTE_PATH=${DEPLOY_PATH:-/opt/patchyard}
REMOTE_OWNER=${DEPLOY_OWNER:-factory-manager}
COLLECTOR_STAGING=${DEPLOY_COLLECTOR_STAGING:-/run/patchyard-openai}
TARGET_REF=${1:-origin/master}
DRY_RUN=${DRY_RUN:-0}

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

say() { printf '%s\n' "$*"; }
die() { printf 'deploy: %s\n' "$*" >&2; exit 1; }

remote() { ssh -o BatchMode=yes "$SSH_USER@$HOST" "$@"; }
# Quoting note: the command is assembled here and run by the remote shell, so
# the path is embedded rather than passed as an argument.
remote_git() {
  remote "sudo -n -u $REMOTE_OWNER env -C $REMOTE_PATH git $*"
}

TARGET_SHA=$(git rev-parse --verify "$TARGET_REF^{commit}") \
  || die "cannot resolve $TARGET_REF locally"
say "target      $TARGET_REF -> $TARGET_SHA"

DEPLOYED_SHA=$(remote_git rev-parse HEAD) || die "cannot read the deployed revision"
say "deployed    $DEPLOYED_SHA"

if [[ "$DEPLOYED_SHA" == "$TARGET_SHA" ]]; then
  say "already at the target revision; nothing to do"
  exit 0
fi

# Refusal 2: a dirty tree is someone's uncommitted work.
DIRTY=$(remote_git status --short)
[[ -z "$DIRTY" ]] || die "deployed tree is dirty; refusing:"$'\n'"$DIRTY"

# Refusal 1: fast-forward only.
git merge-base --is-ancestor "$DEPLOYED_SHA" "$TARGET_SHA" \
  || die "$TARGET_SHA is not a descendant of the deployed $DEPLOYED_SHA; refusing to move sideways"

# Refusal 3: never land under a live attended run. `state` is read rather than
# the process table because a crashed run whose window is still open matters
# just as much as a live one.
#
# This runs under sudo and fails closed. On a control plane that predates the
# group-readable state fix, status.json is 0600 root:root, so reading it as the
# login user returns nothing - and "cannot read" would be indistinguishable
# from "no run is waiting". A guard that cannot see is not a guard.
# `echo`, not printf: the format string's escapes are mangled passing through
# two levels of quoting, and a refusal that misreports the path is worse than
# no refusal at all.
GUARD="for f in $COLLECTOR_STAGING/*/status.json; do [ -e \"\$f\" ] || continue; \
if grep -q awaiting_input \"\$f\"; then echo \"\$f\"; fi; done"
if ! WAITING=$(remote "sudo -n sh -c '$GUARD'"); then
  die "cannot inspect collector sessions on $HOST; refusing to deploy blind"
fi
if [[ -n "$WAITING" ]]; then
  die "an attended collector run is awaiting input; finish or abort it first:"$'\n'"$WAITING"
fi

if [[ "$DRY_RUN" != "0" ]]; then
  say "dry run: would ship $DEPLOYED_SHA..$TARGET_SHA"
  exit 0
fi

BUNDLE=$(mktemp -t patchyard-deploy-XXXXXX.bundle)
REMOTE_BUNDLE="/tmp/$(basename "$BUNDLE")"
cleanup() {
  rm -f "$BUNDLE"
  remote "rm -f $REMOTE_BUNDLE" || true
}
trap cleanup EXIT

git bundle create "$BUNDLE" "$DEPLOYED_SHA..$TARGET_SHA" >/dev/null 2>&1 \
  || die "could not build the incremental bundle"
# The bundle is read by the owning account, not by the login user.
chmod 644 "$BUNDLE"
scp -q "$BUNDLE" "$SSH_USER@$HOST:$REMOTE_BUNDLE"
remote "chmod 644 $REMOTE_BUNDLE"
remote_git bundle verify "$REMOTE_BUNDLE" >/dev/null \
  || die "the shipped bundle does not verify against the deployed checkout"
say "bundle      $(wc -c <"$BUNDLE") bytes, verified on the host"

remote_git fetch "$REMOTE_BUNDLE" "$TARGET_REF" >/dev/null
remote_git checkout --quiet FETCH_HEAD

LANDED=$(remote_git rev-parse HEAD)
[[ "$LANDED" == "$TARGET_SHA" ]] || die "landed $LANDED, expected $TARGET_SHA"
AFTER=$(remote_git status --short)
[[ -z "$AFTER" ]] || die "deployed tree is dirty after checkout:"$'\n'"$AFTER"

say "deployed    $LANDED (clean)"
