#!/bin/bash
# ZINC-Fusion Grafana Startup Script
# Starts Grafana with custom provisioning from this project

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load environment for Prisma password
source "$PROJECT_ROOT/.env"

# Extract password from DATABASE_URL
export PRISMA_PASSWORD=$(echo "$DATABASE_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')

echo "Starting Grafana for ZINC-Fusion..."
echo "Dashboard: http://localhost:3000"
echo "Login: admin / admin (change on first login)"
echo ""

# Start Grafana with custom provisioning
/opt/homebrew/opt/grafana/bin/grafana server \
    --config /opt/homebrew/etc/grafana/grafana.ini \
    --homepath /opt/homebrew/opt/grafana/share/grafana \
    --packaging=brew \
    cfg:default.paths.logs=/opt/homebrew/var/log/grafana \
    cfg:default.paths.data=/opt/homebrew/var/lib/grafana \
    cfg:default.paths.plugins=/opt/homebrew/var/lib/grafana/plugins \
    cfg:default.paths.provisioning="$SCRIPT_DIR/provisioning"
