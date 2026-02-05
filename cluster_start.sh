#!/bin/bash
# Start the Ray cluster (Mac A as head, Mac B as worker)

echo "=== Starting Ray Cluster ==="

# Stop any existing Ray processes
source "/Volumes/Satechi Hub/ZINC-FUSION-V15/.venv/bin/activate"
ray stop 2>/dev/null

# Start head node on Mac A
echo "Starting head node on Mac A..."
RAY_ENABLE_WINDOWS_OR_OSX_CLUSTER=1 ray start --head \
    --node-ip-address=192.168.100.1 \
    --port=6379 \
    --dashboard-host=0.0.0.0

sleep 2

# Connect Mac B as worker
echo "Connecting Mac B as worker..."
ssh jaymiefillers@192.168.100.2 'export PATH="/opt/homebrew/bin:$PATH" && cd ~/ZINC-FUSION-V15 && source .venv/bin/activate && ray stop 2>/dev/null; RAY_ENABLE_WINDOWS_OR_OSX_CLUSTER=1 ray start --address="192.168.100.1:6379" --node-ip-address=192.168.100.2'

echo ""
echo "=== Cluster Status ==="
ray status

echo ""
echo "Dashboard: http://192.168.100.1:8265"
echo ""
echo "To use in Python:"
echo "  import ray"
echo "  ray.init(address='auto')"
