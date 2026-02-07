#!/usr/bin/env bash
# NOTE: ray.init(address='auto') gives 22 cores without melting your machine.
#
# Run volatility + ZL correlation scripts so they KEEP RUNNING
# after you close the terminal. Uses nohup and logs to scripts/logs/.
#
# Usage:
#   cd /path/to/ZINC-FUSION-V15
#   ./scripts/run_volatility_and_correlations_persistent.sh
#
# To check progress:
#   tail -f scripts/logs/volatility_*.log
#   tail -f scripts/logs/correlations_*.log
#

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
mkdir -p scripts/logs
mkdir -p "$REPO/.cursor"
TS=$(date +%Y%m%d_%H%M%S)
VOL_LOG="scripts/logs/volatility_${TS}.log"
CORR_LOG="scripts/logs/correlations_${TS}.log"
PY="$REPO/.venv/bin/python"
RUN_ID="runner_${TS}"
DEBUG_LOG_PATH="$REPO/.cursor/debug.log"
FALLBACK_LOG="$REPO/scripts/logs/runner_fallback.log"
STATUS_FILE="$REPO/scripts/logs/runner_last.txt"
SETSID_AVAILABLE=false
if command -v setsid >/dev/null 2>&1; then SETSID_AVAILABLE=true; fi
PY_SETSID_FALLBACK="import os,sys; os.setsid(); os.execv(sys.argv[1], sys.argv[1:])"

log_json() {
  local ts
  ts="$(date +%s%3N)"
  printf '{"sessionId":"debug-session","runId":"%s","hypothesisId":"%s","location":"%s","message":"%s","data":%s,"timestamp":%s}\n' \
    "$RUN_ID" "$1" "$2" "$3" "$4" "$ts" >> "$DEBUG_LOG_PATH" 2>/dev/null
  if [ $? -ne 0 ]; then
    printf '%s | %s | %s\n' "$ts" "$2" "$3" >> "$FALLBACK_LOG" 2>/dev/null || true
  fi
}

# Ensure debug log file exists (even if empty)
: > "$DEBUG_LOG_PATH" 2>/dev/null || true
printf '%s | runner_start\n' "$(date +%s%3N)" >> "$FALLBACK_LOG" 2>/dev/null || true

# Prevent duplicates unless FORCE_RESTART=1
existing_vol=$(pgrep -f "calculate_volatility_CORRECT.py" 2>/dev/null || true)
existing_corr=$(pgrep -f "complete_correlations_100pct.py" 2>/dev/null || true)
if [ -n "$existing_vol" ] || [ -n "$existing_corr" ]; then
  if [ "${FORCE_RESTART:-0}" != "1" ]; then
    log_json "H6" "run_volatility_and_correlations_persistent.sh:duplicate" "already_running" "{\"existing_vol\":\"$existing_vol\",\"existing_corr\":\"$existing_corr\"}"
    echo "⚠️  Existing runs detected. Not starting duplicates."
    echo "Set FORCE_RESTART=1 to kill and restart."
    echo ""
    echo "Existing volatility PIDs: ${existing_vol:-none}"
    echo "Existing correlation PIDs: ${existing_corr:-none}"
    exit 0
  else
    pkill -f "calculate_volatility_CORRECT.py" 2>/dev/null || true
    pkill -f "complete_correlations_100pct.py" 2>/dev/null || true
  fi
fi

run_cmd() {
  local label="$1"
  shift
  "$@"
  local code=$?
  log_json "H2" "run_volatility_and_correlations_persistent.sh:cmd" "cmd_result" "{\"label\":\"$label\",\"exit_code\":$code}"
  return $code
}

py_exists=false
env_file_exists=false
env_local_exists=false
if [ -x "$PY" ]; then py_exists=true; fi
if [ -f "$REPO/.env" ]; then env_file_exists=true; fi
if [ -f "$REPO/frontend/.env.local" ]; then env_local_exists=true; fi

# #region agent log
log_json "H1" "run_volatility_and_correlations_persistent.sh:start" "runner_start" "{\"repo\":\"$REPO\",\"py_path\":\"$PY\",\"py_exists\":$py_exists,\"env_file_exists\":$env_file_exists,\"env_local_exists\":$env_local_exists,\"setsid_available\":$SETSID_AVAILABLE}"
# #endregion

echo "=============================================="
echo "Starting persistent volatility + correlations"
echo "=============================================="
echo "Repo: $REPO"
echo "Volatility log: $VOL_LOG"
echo "Correlations log: $CORR_LOG"
echo "=============================================="

# Volatility (Yang-Zhang + Garman-Klass) - survives terminal close
if [ "$SETSID_AVAILABLE" = true ]; then
  nohup setsid "$PY" "$REPO/scripts/calculate_volatility_CORRECT.py" </dev/null >> "$VOL_LOG" 2>&1 &
  VOL_DETACH="setsid"
else
  nohup "$PY" -c "$PY_SETSID_FALLBACK" "$PY" "$REPO/scripts/calculate_volatility_CORRECT.py" </dev/null >> "$VOL_LOG" 2>&1 &
  VOL_DETACH="py_setsid"
fi
VOL_PID=$!
VOL_START_CODE=$?
echo "Volatility PID: $VOL_PID"

# Correlations (ZL 30/60/90d to 100%) - survives terminal close
if [ "$SETSID_AVAILABLE" = true ]; then
  nohup setsid "$PY" "$REPO/scripts/complete_correlations_100pct.py" </dev/null >> "$CORR_LOG" 2>&1 &
  CORR_DETACH="setsid"
else
  nohup "$PY" -c "$PY_SETSID_FALLBACK" "$PY" "$REPO/scripts/complete_correlations_100pct.py" </dev/null >> "$CORR_LOG" 2>&1 &
  CORR_DETACH="py_setsid"
fi
CORR_PID=$!
CORR_START_CODE=$?
echo "Correlations PID: $CORR_PID"

# Disown so closing this shell does not kill them
disown "$VOL_PID" 2>/dev/null
DISOWN_VOL_CODE=$?
disown "$CORR_PID" 2>/dev/null
DISOWN_CORR_CODE=$?

# #region agent log
vol_pid_alive=false
corr_pid_alive=false
if ps -p "$VOL_PID" >/dev/null 2>&1; then vol_pid_alive=true; fi
if ps -p "$CORR_PID" >/dev/null 2>&1; then corr_pid_alive=true; fi

log_json "H2" "run_volatility_and_correlations_persistent.sh:after_start" "runner_started" "{\"vol_pid\":$VOL_PID,\"corr_pid\":$CORR_PID,\"vol_start_code\":$VOL_START_CODE,\"corr_start_code\":$CORR_START_CODE,\"disown_vol_code\":$DISOWN_VOL_CODE,\"disown_corr_code\":$DISOWN_CORR_CODE,\"vol_pid_alive\":$vol_pid_alive,\"corr_pid_alive\":$corr_pid_alive,\"vol_detach\":\"$VOL_DETACH\",\"corr_detach\":\"$CORR_DETACH\"}"
# #endregion

# Record status for quick checks
cat > "$STATUS_FILE" <<EOF
volatility_pid=$VOL_PID
correlations_pid=$CORR_PID
volatility_log=$VOL_LOG
correlations_log=$CORR_LOG
started_at=$TS
EOF

echo "=============================================="
echo "Both jobs are running in background."
echo "Close this terminal; they will keep running."
echo ""
echo "Check progress:"
echo "  tail -f $VOL_LOG"
echo "  tail -f $CORR_LOG"
echo "=============================================="

# #region agent log
log_json "H3" "run_volatility_and_correlations_persistent.sh:exit" "runner_exit" "{\"status\":\"printed_instructions\"}"
# #endregion
