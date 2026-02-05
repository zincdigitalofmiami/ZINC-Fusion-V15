#!/bin/bash
# Full fill: backfill mkt.options_1d with all 15 stat columns from Databento.
# Run from repo root. Log: /tmp/options_full_fill.log
# NOTE: ray.init(address='auto') gives 22 cores without melting your machine.
set -e
cd "$(dirname "$0")/.."
exec .venv/bin/python scripts/backfill_options_PARALLEL.py \
  --start 2010-06-06 \
  --end 2026-02-02 \
  --all \
  --progress-file /tmp/options_full_fill.log
