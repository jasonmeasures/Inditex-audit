#!/usr/bin/env bash
# start.sh — one-click launcher for the 7501 Audit Dashboard
# Usage:  ./start.sh
#         PORT=5500 ./start.sh

set -euo pipefail
cd "$(dirname "$0")"

# Load optional .env overrides
if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

# Ensure Postgres is running
if ! brew services list 2>/dev/null | grep -q "postgresql.*started"; then
  echo "  ↻ Starting PostgreSQL 16..."
  brew services start postgresql@16
  sleep 2
fi

# Activate the virtual environment
if [ ! -d .venv ]; then
  echo "  ✗ .venv not found. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi
source .venv/bin/activate

exec python3 inditex_audit_server.py
