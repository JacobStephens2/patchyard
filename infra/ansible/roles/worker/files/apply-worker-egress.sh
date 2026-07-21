#!/usr/bin/env bash
set -euo pipefail

if nft list table inet patchyard_worker_egress >/dev/null 2>&1; then
  nft delete table inet patchyard_worker_egress
fi

exec nft -f /etc/nftables/patchyard-worker-egress.nft
