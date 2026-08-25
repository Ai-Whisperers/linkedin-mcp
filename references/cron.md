# Cron jobs for linkedin-mcp

## linkedin-token-refresh (weekly)

Runs every 7 days. Sanity-pings the token, estimates days-to-expiry (60d from issued_at), alerts if expiry < 14 days.

```bash
# /opt/data/agents/cron/linkedin-token-refresh/run.sh
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH=/opt/data/integrations/linkedin-mcp
export LINKEDIN_ENV_FILE=/opt/data/integrations/linkedin-mcp/.env
exec /opt/hermes/.venv/bin/python -m linkedin_mcp.scripts.check_token
```

Cron entry:

```yaml
- name: linkedin-token-refresh
  schedule: '0 9 * * 1'   # Mondays 09:00 PYT
  prompt: |
    You are the LinkedIn token-refresh cron. Run the check script:
        bash /opt/data/agents/cron/linkedin-token-refresh/run.sh
    Parse the JSON output. If `action` is REFRESH_SOON or TOKEN_EXPIRED,
    notify the user via the configured cron delivery target and propose
    re-running the OAuth flow at https://hermes.paragu-ai.com/auth/linkedin/start.
    If `action` is TOKEN_OK, stay silent (no need to deliver anything).
  skills: [linkedin-mcp]
  deliver: origin
  enabled_toolsets: [terminal]
```

## linkedin-publisher (every 15 min)

Runs every 15 minutes. Reads a queue of scheduled drafts from `/opt/data/scratchpad/linkedin-queue/` and publishes any that are due.

Queue file format:

```json
{
  "id": "li-2026-08-25-001",
  "scheduled_at": "2026-08-25T15:00:00-04:00",
  "author_urn": "urn:li:person:XXXX",
  "commentary": "...",
  "image_url": "https://...",      // optional
  "status": "pending"              // pending → published | failed
}
```

Cron entry:

```yaml
- name: linkedin-publisher
  schedule: '*/15 * * * *'
  prompt: |
    You are the LinkedIn publisher cron.
    1. List files in /opt/data/scratchpad/linkedin-queue/*.json
    2. For each file with status="pending" and scheduled_at <= now():
       - Call mcp_linkedin_mcp_create_text_post or create_image_post
       - On success: write status="published" and the returned post URN
       - On failure: write status="failed" and the error envelope
    3. Delete files older than 30 days.
    Do NOT post anything that has status != "pending". Do NOT skip the
    scheduled_at check (future posts should stay pending).
  skills: [linkedin-mcp]
  deliver: origin
  enabled_toolsets: [terminal]
```

## linkedin-engagement-rollup (daily)

Runs daily at 08:00 PYT. Fetches impressions / engagement for posts published in the last 7 days via the UGC Posts API (`/v2/ugcPosts?q=authors` with `r_member_social`). Writes a Markdown rollup to `/opt/data/scratchpad/linkedin-rollups/YYYY-MM-DD.md`.

> NOTE: `r_member_social` is a closed permission per LinkedIn. Until we have it (currently not accepting applications), this cron will stay disabled. Use `mcp_linkedin_mcp_get_post` for the posts we know about.

---

All cron jobs honor the org banlist: container names, scripts, log paths, public-facing output never contain upstream product names.