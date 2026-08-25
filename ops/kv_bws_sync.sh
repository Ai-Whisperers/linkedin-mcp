#!/usr/bin/env bash
# kv_bws_sync.sh — invoked by the kv-bws-sync cron job (every 5 min).
# Bridges CF KV → BWS via the SDK.
set -euo pipefail

# Run via the project venv python (has bitwarden_sdk + pydantic installed).
# Pull CF_API_TOKEN from BWS via the existing bridge so the script has the credential.
export CF_API_TOKEN=$(/opt/data/.venv/bin/python -c '
from bitwarden_sdk import BitwardenClient, ClientSettings, DeviceType
import uuid as _uuid
token = open("/opt/data/.hermes/inbox/bws-token.secret").read().strip()
org_id = open("/opt/data/.hermes/inbox/org-id.txt").read().strip()
s = ClientSettings(api_url="https://api.bitwarden.com", identity_url="https://identity.bitwarden.com", user_agent="inv/1.0", device_type=DeviceType.SERVER)
c = BitwardenClient(s); c.auth().login_access_token(token, None)
r = c.secrets().list(_uuid.UUID(org_id))
for sec in r.to_dict()["data"]["data"]:
    if isinstance(sec, dict) and sec.get("key") == "CF_API_TOKEN":
        print(c.secrets().get(sec["id"]).to_dict()["data"]["value"], end="")
        break
')

# Run the sync. Only fails print to stderr; cron captures that.
exec /opt/data/.venv/bin/python /opt/data/scripts/kv_bws_sync.py