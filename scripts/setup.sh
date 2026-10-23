#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source "$HOME/.nvm/nvm.sh"
nvm use
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.lock.txt
npm --prefix frontend ci
npm --prefix frontend run build
if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
fi
printf '%s\n' 'Setup complete. Configure .env, then run: bash scripts/run.sh'
