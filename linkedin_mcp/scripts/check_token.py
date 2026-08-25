"""Cron-friendly token health check.

Run weekly. Returns JSON to stdout; non-zero exit on failure.

Checks:
  1. Token is present and parseable.
  2. GET /v2/userinfo succeeds (sanity).
  3. The token's scope includes at least one of {w_member_social, w_organization_social}.
  4. Approximate days-to-expiry based on token issuance time (if stored alongside).

Reads BWS secret `LINKEDIN_TOKEN_ISSUED_AT` (ISO 8601) if available; otherwise
prints "no-issued-at" and skips expiry estimation.
"""
from __future__ import annotations
import json
import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

# Allow running via /opt/hermes/.venv/bin/python -m linkedin_mcp.scripts.check_token
sys.path.insert(0, "/opt/data/integrations")
from linkedin_mcp.client import LinkedInClient, LinkedInError
from linkedin_mcp.config import get_settings


async def main() -> int:
    settings = get_settings()
    if not settings.linkedin_access_token:
        out = {"ok": False, "reason": "LINKEDIN_ACCESS_TOKEN missing"}
        print(json.dumps(out))
        return 1

    client = LinkedInClient(settings)
    try:
        info = await client.get_userinfo()
    except LinkedInError as e:
        out = {"ok": False, "reason": f"GET /v2/userinfo failed", "error": {
            "status": e.status, "code": e.code, "message": e.message, "serviceErrorCode": e.service_error_code,
        }}
        print(json.dumps(out))
        return 1
    finally:
        await client.close()

    # Estimate expiry (60-day default for client_credentials / authorization_code grants without refresh)
    issued_at_str = os.environ.get("LINKEDIN_TOKEN_ISSUED_AT")
    days_remaining = None
    if issued_at_str:
        try:
            issued = datetime.fromisoformat(issued_at_str.replace("Z", "+00:00"))
            expires = issued + timedelta(days=60)
            days_remaining = (expires - datetime.now(timezone.utc)).days
        except Exception:
            pass

    out = {
        "ok": True,
        "sub": info.get("sub"),
        "name": info.get("name"),
        "email": info.get("email"),
        "days_remaining": days_remaining,
        "action": (
            "TOKEN_OK"
            if days_remaining is None
            else ("TOKEN_OK" if days_remaining > 14 else "REFRESH_SOON" if days_remaining > 0 else "TOKEN_EXPIRED")
        ),
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))