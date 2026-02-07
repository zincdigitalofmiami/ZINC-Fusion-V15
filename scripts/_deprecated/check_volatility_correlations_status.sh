#!/usr/bin/env bash
REPO="$(cd "$(dirname "$0")/.." && pwd)"
STATUS_FILE="$REPO/scripts/logs/runner_last.txt"

echo "=============================================="
echo "Volatility/Correlations Status"
echo "=============================================="

if [ -f "$STATUS_FILE" ]; then
  # shellcheck disable=SC1090
  source "$STATUS_FILE"
  echo "Started at: ${started_at:-unknown}"
  echo "Volatility PID: ${volatility_pid:-missing}"
  echo "Correlations PID: ${correlations_pid:-missing}"
  echo "Volatility log: ${volatility_log:-missing}"
  echo "Correlations log: ${correlations_log:-missing}"
  echo ""
  if [ -n "${volatility_pid:-}" ]; then
    if ps -p "$volatility_pid" >/dev/null 2>&1; then
      echo "Volatility: RUNNING"
    else
      echo "Volatility: NOT RUNNING"
    fi
  fi
  if [ -n "${correlations_pid:-}" ]; then
    if ps -p "$correlations_pid" >/dev/null 2>&1; then
      echo "Correlations: RUNNING"
    else
      echo "Correlations: NOT RUNNING"
    fi
  fi
else
  echo "No status file found: $STATUS_FILE"
  echo "Checking for any running processes..."
  pgrep -fl "calculate_volatility_CORRECT.py|complete_correlations_100pct.py" || echo "No running processes found."
fi

echo "=============================================="
