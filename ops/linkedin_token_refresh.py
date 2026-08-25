#!/usr/bin/env python3
"""linkedin-token-refresh — checks LINKEDIN_ACCESS_TOKEN validity and refreshes if needed.

Runs as a cron (daily). When the token is within 14 days of expiry, calls the Worker's
/refresh endpoint with the stored refresh_token. The Worker handles the OAuth refresh
and writes the new token back to CF KV (which the kv-bws-sync cron then moves to BWS).

When LINKEDIN_REFRESH_TOKEN is missing, we cannot auto-refresh — silently skip.
"""
from __future__ import annotations
import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

# Worker URL — change to auth.hermes.paragu-ai.com once the custom hostname is provisioned
LINKEDIN_WORKER_URL = "https://linkedin-oauth.weissvanderpol-ivan.workers.dev/auth/linkedin/refresh"
REFRESH_THRESHOLD_DAYS = 14


def fetch_bws_secret(key):
    """Read a BWS secret via the SDK."""
    sys.path.insert(0, "/opt/data")
    from bitwarden_sdk import BitwardenClient, ClientSettings, DeviceType
    import uuid as _uuid
    token = open("/opt/data/.hermes/inbox/bws-token.secret").read().strip()
    org_id = open("/opt/data/.hermes/inbox/org-id.txt").read().strip()
    s = ClientSettings(
        api_url="https://api.bitwarden.com",
        identity_url="https://identity.bitwarden.com",
        user_agent="linkedin-token-refresh/1.0",
        device_type=DeviceType.SERVER,
    )
    c = BitwardenClient(s)
    c.auth().login_access_token(token, None)
    r = c.secrets().list(_uuid.UUID(org_id))
    for sec in r.to_dict()["data"]["data"]:
        if isinstance(sec, dict) and sec.get("key") == key:
            return c.secrets().get(sec["id"]).to_dict()["data"]["value"]
    return None


def main():
    print("Checking LinkedIn token validity...")
    issued_at = fetch_bws_secret("LINKEDIN_TOKEN_ISSUED_AT")
    refresh_token = fetch_bws_secret("LINKEDIN_REFRESH_TOKEN")
    access_token = fetch_bws_secret("LINKEDIN_ACCESS_TOKEN")

    if not issued_at or not access_token:
        print("  No LinkedIn token in BWS yet — skipping (OAuth not completed)")
        return 0

    # Parse issued_at
    try:
        issued = datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
    except Exception:
        print(f"  Could not parse LINKEDIN_TOKEN_ISSUED_AT: {issued_at!r}")
        return 0

    expires_at = issued.replace(tzinfo=timezone.utc) if issued.tzinfo is None else issued
    expires_at = issued + __import__("datetime").timedelta(days=60)  # 60-day LinkedIn default
    days_remaining = (expires_at - datetime.now(timezone.utc)).days

    print(f"  Token issued: {issued_at}")
    print(f"  Days remaining: {days_remaining}")

    if days_remaining > REFRESH_THRESHOLD_DAYS:
        print(f"  Token still valid (> {REFRESH_THRESHOLD_DAYS} days), no refresh needed")
        return 0

    if not refresh_token or refresh_token == "placeholder":
        print(f"  No refresh_token in BWS — cannot auto-refresh")
        print(f"  Alert: User needs to re-walk OAuth flow at {LINKEDIN_WORKER_URL.replace('/refresh', '/start')}")
        return 0

    print(f"  Refreshing token via Worker...")
    body = json.dumps({"refresh_token": refresh_token}).encode()
    req = urllib.request.Request(
        LINKEDIN_WORKER_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        if result.get("ok"):
            print(f"  ✓ Refresh succeeded. New expires_in: {result.get('expires_in')}s")
            print(f"  Worker wrote new token to CF KV. kv-bws-sync will move to BWS within 5 min.")
            return 0
        else:
            print(f"  ✗ Refresh failed: {result}")
            return 1
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")[:300]
        print(f"  ✗ Refresh HTTP {e.code}: {body}")
        return 1
    except Exception as e:
        print(f"  ✗ Refresh error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())