#!/bin/bash
# Run remaining FX options sequentially

UNDERLYINGS=("6B" "6C" "6A" "6S" "6N" "6M" "6L" "6Z")

for underlying in "${UNDERLYINGS[@]}"; do
    echo "Starting $underlying..."
    .venv/bin/python scripts/backfill_options_PARALLEL.py --underlying "$underlying" --start 2010-06-06 --end 2026-02-02 --workers 1 > "/tmp/fx_${underlying}.log" 2>&1 &
    pid=$!
    echo "PID: $pid"
    
    # Wait for this one to finish before starting next
    wait $pid
    
    echo "$underlying completed"
    sleep 5
done

echo "All FX options backfill completed"
