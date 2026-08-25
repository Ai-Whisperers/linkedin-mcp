#!/usr/bin/env bash
# linkedin-token-refresh.sh — wrapper invoked by the linkedin-token-refresh cron job (daily).
set -euo pipefail
exec /opt/data/.venv/bin/python /opt/data/scripts/linkedin_token_refresh.py