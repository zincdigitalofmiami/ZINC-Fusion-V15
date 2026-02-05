#!/bin/bash
# Stop the Ray cluster on both Macs

echo "=== Stopping Ray Cluster ==="

# Stop on Mac A
source "/Volumes/Satechi Hub/ZINC-FUSION-V15/.venv/bin/activate"
ray stop

# Stop on Mac B
ssh jaymiefillers@192.168.100.2 'export PATH="/opt/homebrew/bin:$PATH" && cd ~/ZINC-FUSION-V15 && source .venv/bin/activate && ray stop'

echo "Cluster stopped."
