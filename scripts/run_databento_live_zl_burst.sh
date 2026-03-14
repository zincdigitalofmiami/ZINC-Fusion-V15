#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for env_file in "${ROOT_DIR}/.env" "${ROOT_DIR}/.env.local"; do
  if [ -f "${env_file}" ]; then
    set -a
    # shellcheck disable=SC1090
    . "${env_file}"
    set +a
  fi
done

# Inngest event intake currently requires branch env routing.
# Keep event forwarding off by default so live DB updates continue cleanly.
export DATABENTO_SEND_INNGEST_EVENTS="${DATABENTO_SEND_INNGEST_EVENTS:-0}"

if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
  PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi

exec "${PYTHON_BIN}" "${ROOT_DIR}/scripts/ingest_databento_live_zl.py" --run-seconds 120
