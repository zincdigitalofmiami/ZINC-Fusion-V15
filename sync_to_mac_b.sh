#!/bin/bash
# Sync project files to Mac B
# Run this before executing training on Mac B

echo "=== Syncing ZINC-FUSION-V15 to Mac B ==="

rsync -avz --progress \
  --exclude '.venv' \
  --exclude 'node_modules' \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'AutogluonModels' \
  --exclude 'logs' \
  --exclude '.pytest_cache' \
  "/Volumes/Satechi Hub/ZINC-FUSION-V15/" \
  "jaymiefillers@192.168.100.2:~/ZINC-FUSION-V15/"

echo "=== Sync complete ==="
