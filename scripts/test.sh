#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source "$HOME/.nvm/nvm.sh"
nvm use
(cd backend && .venv/bin/python -m pytest -q)
npm --prefix frontend test
npm --prefix frontend run build
