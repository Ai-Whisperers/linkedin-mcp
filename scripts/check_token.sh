#!/usr/bin/env bash
# Token sanity check + days-to-expiry check. Cron-friendly.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="/opt/data/integrations:${PYTHONPATH:-}"
export LINKEDIN_ENV_FILE="${LINKEDIN_ENV_FILE:-$HERE/.env}"
exec /opt/hermes/.venv/bin/python -m linkedin_mcp.scripts.check_token