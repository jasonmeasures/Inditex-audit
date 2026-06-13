#!/usr/bin/env bash
# start.sh — starts PostgreSQL, Flask API, and opens the dashboard
# Usage: ./start.sh
#        PORT=5500 ./start.sh

set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-5252}"
URL="http://localhost:${PORT}"

# Load optional .env overrides
if [ -f .env ]; then
  set -a; source .env; set +a
fi

echo ""
echo "📊  7501 Audit Tool"
echo "────────────────────────────────────"

# 1. PostgreSQL
if brew services list 2>/dev/null | grep -q "postgresql.*started"; then
  echo "  ✓  PostgreSQL 16  (already running)"
else
  echo "  ↻  Starting PostgreSQL 16..."
  brew services start postgresql@16
  sleep 2
  echo "  ✓  PostgreSQL 16  started"
fi

# 2. Python venv
if [ ! -d .venv ]; then
  echo ""
  echo "  ✗  .venv not found."
  echo "     Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi
source .venv/bin/activate
echo "  ✓  Python venv    activated"

# 3. Kill any stale server on the target port
if lsof -ti tcp:"${PORT}" &>/dev/null; then
  echo "  ↻  Port ${PORT} in use — stopping old process..."
  lsof -ti tcp:"${PORT}" | xargs kill -9 2>/dev/null || true
  sleep 1
fi

# 4. Start Flask in background, capture log
LOG_FILE="/tmp/audit-server.log"
python3 inditex_audit_server.py >"${LOG_FILE}" 2>&1 &
SERVER_PID=$!
echo "  ↻  Flask server   starting (pid ${SERVER_PID})..."

# 5. Wait up to 8 s for /api/health
READY=0
for i in $(seq 1 16); do
  sleep 0.5
  if curl -sf "${URL}/api/health" >/dev/null 2>&1; then
    READY=1
    break
  fi
done

if [ "${READY}" -eq 0 ]; then
  echo ""
  echo "  ✗  Server did not respond at ${URL} after 8 s."
  echo "     Last log output:"
  tail -20 "${LOG_FILE}" | sed 's/^/     /'
  exit 1
fi

echo "  ✓  Flask server   ready"

# 6. Open browser
echo "  ↻  Opening browser..."
open "${URL}" 2>/dev/null || true

echo "────────────────────────────────────"
echo "  🚀  Dashboard →  ${URL}"
echo "      API health →  ${URL}/api/health"
echo "      Server log →  ${LOG_FILE}"
echo "      Stop:  kill ${SERVER_PID}  (or 'audit-stop')"
echo ""

# 7. Stream server logs so Ctrl-C stops everything cleanly
trap "echo ''; echo '  Stopping server (pid ${SERVER_PID})...'; kill ${SERVER_PID} 2>/dev/null; exit 0" INT TERM
tail -f "${LOG_FILE}" &
wait "${SERVER_PID}"
