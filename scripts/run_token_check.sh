#!/usr/bin/env bash
# Wired into Hermes as a scheduled cron. Runs weekly.
#   - Sanity-pings the LinkedIn token
#   - Estimates days-to-expiry (60d from issued_at)
#   - Alerts via cron notify if expiry < 14d, or token invalid
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="/opt/data/integrations:${PYTHONPATH:-}"
export LINKEDIN_ENV_FILE="${LINKEDIN_ENV_FILE:-$HERE/.env}"
exec /opt/hermes/.venv/bin/python -m linkedin_mcp.scripts.check_token