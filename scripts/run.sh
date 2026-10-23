#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ ! -f frontend/dist/index.html ]]; then
  printf '%s\n' 'Frontend build missing. Run: bash scripts/setup.sh' >&2
  exit 1
fi
exec backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
