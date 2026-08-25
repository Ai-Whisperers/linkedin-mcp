# linkedin-mcp

Official LinkedIn REST API surface for the Hermes agent. Wraps the **Posts API** (`/rest/posts`), the legacy **UGC Posts API** (`/v2/ugcPosts` for Share on LinkedIn), **Sign In with LinkedIn** (OIDC userinfo), and the two-step **asset upload** protocol.

Naming reminder: this package, MCP server name, container names, env-var prefixes, and Worker names are `linkedin-mcp` (hyphen canonical). The org trademark banlist excludes upstream product names from every public string — see `references/trademark.md`.

## What it does

| Capability | Endpoint | Scope needed | Approval |
|---|---|---|---|
| Read own profile | `GET /v2/userinfo` | `openid profile email` | none (open) |
| Post text on behalf of member | `POST /rest/posts` | `w_member_social` | App Review |
| Post image/video on behalf of member | `POST /rest/assets` + `POST /rest/posts` | `w_member_social` | App Review |
| Share on LinkedIn (legacy) | `POST /v2/ugcPosts` | `w_member_social` | App Review |
| Post on behalf of company page | `POST /rest/posts` | `w_organization_social` | Community Mgmt API partner approval (months) |
| Read company-page analytics | `GET /rest/organizationalEntityShareStatistics` | `r_organization_social` | Community Mgmt API partner approval |

**Realistic timeline:** 1-3 weeks for `w_member_social`. Months for org posting.

## Required env

```ini
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
LINKEDIN_ACCESS_TOKEN=          # long-lived OAuth2 token, refresh every 60d
LINKEDIN_PERSON_URN=urn:li:person:XXXX     # for member posts
# Optional (only if approved for org posting):
LINKEDIN_ORG_URN=urn:li:organization:XXXX
# Optional:
LINKEDIN_REDIRECT_URI=https://hermes.paragu-ai.com/auth/linkedin/callback
LINKEDIN_API_VERSION=202608
LINKEDIN_API_BASE=https://api.linkedin.com
LINKEDIN_RATE_PER_HOUR=800
LINKEDIN_ENABLE_WRITES=true
```

## Install

```bash
# Sandbox / dev
uv pip install -p /opt/hermes/.venv/bin/python -e /opt/data/integrations/linkedin-mcp

# Standalone host
uv venv /opt/linkedin-mcp/.venv --python 3.11
uv pip install --python /opt/linkedin-mcp/.venv/bin/python -e /opt/data/integrations/linkedin-mcp
```

## Wire into Hermes

`/opt/data/.hermes/config.yaml`:

```yaml
mcp_servers:
  linkedin-mcp:
    command: "/opt/hermes/.venv/bin/python"
    args: ["-m", "linkedin_mcp"]
    env:
      PYTHONPATH: "/opt/data/integrations"
      LINKEDIN_ENV_FILE: "/opt/data/integrations/linkedin-mcp/.env"
    timeout: 120
    connect_timeout: 30
```

After restart, tools appear as `mcp_linkedin_mcp_<tool>`:

- `mcp_linkedin_mcp_get_my_profile`
- `mcp_linkedin_mcp_create_text_post`
- `mcp_linkedin_mcp_create_image_post`
- `mcp_linkedin_mcp_create_video_post`
- `mcp_linkedin_mcp_create_member_share` (legacy UGC)
- `mcp_linkedin_mcp_get_post`, `mcp_linkedin_mcp_delete_post`
- `mcp_linkedin_mcp_upload_image_from_url`
- `mcp_linkedin_mcp_sanity_ping`

## OAuth setup

The redirect URI must be registered on the LinkedIn App under **Auth → Authorized redirect URLs**. Default in config is `https://hermes.paragu-ai.com/auth/linkedin/callback` (served by the `linkedin-oauth` CF Worker — see `linkedin-oauth-worker/`).

Token flow:
1. User opens `https://hermes.paragu-ai.com/auth/linkedin/start` → redirects to LinkedIn authorize URL with `response_type=code`, `scope=w_member_social openid profile email`, `redirect_uri=...`, `client_id=...`.
2. LinkedIn redirects to `/auth/linkedin/callback?code=...`.
3. Worker exchanges `code` for `access_token` (60-day, no refresh token by default — re-run the OAuth flow at day 50).
4. Worker writes the new token to BWS secret `LINKEDIN_ACCESS_TOKEN` (overwrites previous).
5. `linkedin-token-refresh` cron runs every 7 days, sanity-pings the token, alerts if expiry < 14d.

For automatic refresh of *short-lived* tokens, request `offline_access` scope and a refresh token on initial grant.

## Posting flow (member, w_member_social)

```
draft commentary → mcp_linkedin_mcp_create_text_post(commentary=...)
```

For images:

```
upload image to public URL (R2 / VPS / CF Pages)
  → mcp_linkedin_mcp_create_image_post(commentary=..., image_url=https://...)
```

The tool internally:
1. `POST /rest/assets?action=registerUpload` with `recipes=["urn:li:digitalmediaRecipe:feedshare-image"]`
2. `PUT <uploadUrl>` with image bytes
3. `POST /rest/posts` with `content.media.id = asset_urn`

## Posting flow (organization, requires Community Mgmt API partner approval)

1. Set `LINKEDIN_ORG_URN=urn:li:organization:XXXX`
2. Token must include `w_organization_social` and `r_organization_social`.
3. `create_text_post(commentary=..., author_urn=$LINKEDIN_ORG_URN)` — author_urn overrides default.

## Notes on safety

- Never automate connection requests, InMail, or DMs.
- Never mass-comment on posts you don't own.
- Vary posting cadence — LinkedIn flags predictable cron-blast patterns.
- `LINKEDIN_ENABLE_WRITES=false` hides every write tool from the MCP tool list — useful during the App Review window.
- All errors return the LinkedIn envelope verbatim. `serviceErrorCode: 100` = "the token used has not been scoped to the correct permissions" — most common cause: App Review not yet approved, or wrong scope requested at OAuth time.