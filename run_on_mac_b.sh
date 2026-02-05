#!/bin/bash
# Run a command on Mac B (Jaymie's Mac mini)
# Usage: ./run_on_mac_b.sh "python script.py"

COMMAND="$*"
if [ -z "$COMMAND" ]; then
    echo "Usage: ./run_on_mac_b.sh <command>"
    echo "Example: ./run_on_mac_b.sh python -m fusion.core_training.run_pipeline --horizons 5"
    exit 1
fi

echo "=== Running on Mac B (192.168.100.2) ==="
echo "Command: $COMMAND"
echo "=================================="

ssh jaymiefillers@192.168.100.2 "export PATH=\"/opt/homebrew/bin:\$PATH\" && cd ~/ZINC-FUSION-V15 && source .venv/bin/activate && $COMMAND"
