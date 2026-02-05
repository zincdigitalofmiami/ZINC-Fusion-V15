#!/bin/bash
# Ray Head Node Startup Script for Mac A

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export RAY_ENABLE_WINDOWS_OR_OSX_CLUSTER=1

# Wait for network to be ready
sleep 10

# Activate venv and start Ray head
cd "/Volumes/Satechi Hub/ZINC-FUSION-V15"
source .venv/bin/activate

# Stop any existing Ray
ray stop 2>/dev/null || true

# Start head node
ray start --head \
    --node-ip-address=192.168.100.1 \
    --port=6379 \
    --dashboard-host=0.0.0.0 \
    --disable-usage-stats

echo "$(date): Ray head started" >> /tmp/ray_head.log
