#!/usr/bin/env bash
# Pull environment variables from Vercel for both root Prisma and frontend
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Pulling Vercel env → root .env (Prisma) ==="
cd "$REPO_ROOT"
vercel env pull .env --yes 2>/dev/null || vercel env pull .env

echo ""
echo "=== Pulling Vercel env → frontend/.env.local ==="
cd "$REPO_ROOT/frontend"
vercel env pull .env.local --yes 2>/dev/null || vercel env pull .env.local

echo ""
echo "✅ Done. Files updated:"
echo "  - $REPO_ROOT/.env"
echo "  - $REPO_ROOT/frontend/.env.local"
