#!/usr/bin/env bash
# Run linkedin-mcp directly without installing (dev).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="/opt/data/integrations:${PYTHONPATH:-}"
export LINKEDIN_ENV_FILE="${LINKEDIN_ENV_FILE:-$HERE/.env}"
exec /opt/hermes/.venv/bin/python -m linkedin_mcp "$@"