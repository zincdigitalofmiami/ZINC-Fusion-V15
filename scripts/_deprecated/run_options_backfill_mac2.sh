#!/usr/bin/env bash
# Mac Mini 2: run from repo root. Handles underlyings 1,3,5,...,19 (second half).
# NOTE: ray.init(address='auto') gives 22 cores without melting your machine.
set -e
cd "$(dirname "$0")/.."
echo "Stopping any existing backfill..."
pkill -f backfill_options_PARALLEL || true
sleep 2
.venv/bin/python -u scripts/backfill_options_PARALLEL.py \
  --all --start 2010-06-06 --end 2026-02-02 \
  --worker-index 1 --worker-total 2 --workers 8 --batch-months 3 \
  --progress-file /tmp/options_progress_mac2.log
