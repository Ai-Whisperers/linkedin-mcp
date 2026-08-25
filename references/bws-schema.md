# BWS secret schema — linkedin-mcp + linkedin-oauth-worker

This is the canonical schema for the Bitwarden Secrets Manager entries these integrations need. UUIDs are filled in once we create the secrets in BWS.

## linkedin-mcp (read by the MCP server at runtime)

| Secret name | Type | Value | Notes |
|---|---|---|---|
| `LINKEDIN_CLIENT_ID` | string | `86xxxxxx` | from LinkedIn App → Auth → Credentials |
| `LINKEDIN_CLIENT_SECRET` | string | `••••••` | same place, never logged |
| `LINKEDIN_ACCESS_TOKEN` | string | `AQV...` | long-lived OAuth2 token, 60d |
| `LINKEDIN_TOKEN_ISSUED_AT` | ISO 8601 | `2026-08-25T14:00:00Z` | used for days-to-expiry |
| `LINKEDIN_TOKEN_SCOPES` | string | `openid profile email w_member_social` | written by OAuth worker |
| `LINKEDIN_PERSON_URN` | string | `urn:li:person:XXXX` | member URN for personal posts |
| `LINKEDIN_ORG_URN` | string (optional) | `urn:li:organization:XXXX` | only if org posting approved |
| `LINKEDIN_REFRESH_TOKEN` | string (optional) | `AQV...` | only if `offline_access` granted |

The MCP server reads these via `.env` file at `LINKEDIN_ENV_FILE`. The pattern is: an out-of-band script (`scripts/populate_env_from_bws.sh`) runs periodically (or on demand) and writes the values into `.env`. Hermes is not allowed to read BWS directly — the secret material is only ever on disk at the moment of writing.

## linkedin-oauth-worker (Cloudflare Worker secrets)

The Worker reads its secrets via `wrangler secret put`, not via BWS. The Worker itself writes back to BWS so the MCP server can pick up the refreshed token.

| Worker secret (in CF) | Source | UUID of BWS secret it writes to |
|---|---|---|
| `LINKEDIN_CLIENT_ID` | static | — |
| `LINKEDIN_CLIENT_SECRET` | static | — |
| `LINKEDIN_REDIRECT_URI` | static | — |
| `LINKEDIN_SCOPES` | static | — |
| `BWS_ACCESS_TOKEN` | static (service-account token) | — |
| `BWS_BASE_URL` | static | — |
| `BWS_SECRET_ID_ACCESS_TOKEN` | static (UUID) | `LINKEDIN_ACCESS_TOKEN` |
| `BWS_SECRET_ID_ISSUED_AT` | static (UUID) | `LINKEDIN_TOKEN_ISSUED_AT` |
| `BWS_SECRET_ID_SCOPES` | static (UUID) | `LINKEDIN_TOKEN_SCOPES` |
| `BWS_SECRET_ID_REFRESH_TOKEN` | static (UUID, optional) | `LINKEDIN_REFRESH_TOKEN` |

**Naming convention:** BWS secret names use `LINKEDIN_*` prefix. The Worker's `BWS_SECRET_ID_*` env vars contain the UUIDs of those secrets — the Worker uses them to PUT new values back.

## One-time setup checklist

```bash
# Step 1: Create the BWS project (do this once for the project)
bws project create "ai-whisperers-social" --description "LinkedIn + Meta tokens"

# Step 2: Create each secret and capture the UUID
for name in LINKEDIN_CLIENT_ID LINKEDIN_CLIENT_SECRET LINKEDIN_ACCESS_TOKEN \
            LINKEDIN_TOKEN_ISSUED_AT LINKEDIN_TOKEN_SCOPES \
            LINKEDIN_PERSON_URN LINKEDIN_REFRESH_TOKEN; do
  bws secret create "$name" --project "ai-whisperers-social"
  # Note the returned UUID — paste into env config
done

# Step 3: Set Worker secrets
cd /opt/data/integrations/linkedin-oauth-worker
wrangler secret put LINKEDIN_CLIENT_ID
wrangler secret put LINKEDIN_CLIENT_SECRET
wrangler secret put LINKEDIN_REDIRECT_URI
wrangler secret put LINKEDIN_SCOPES
wrangler secret put BWS_ACCESS_TOKEN
wrangler secret put BWS_BASE_URL
wrangler secret put BWS_SECRET_ID_ACCESS_TOKEN       # paste UUID from step 2
wrangler secret put BWS_SECRET_ID_ISSUED_AT          # paste UUID
wrangler secret put BWS_SECRET_ID_SCOPES             # paste UUID
wrangler secret put BWS_SECRET_ID_REFRESH_TOKEN      # paste UUID if used

# Step 4: Wire the UUIDs into the MCP server's .env file
# (populate_env_from_bws.sh reads from BWS using the same UUIDs)
```

## Rotation policy

| Secret | Rotation cadence |
|---|---|
| `LINKEDIN_ACCESS_TOKEN` | Auto on every OAuth callback (60d, but we run a re-auth flow at 50d) |
| `LINKEDIN_CLIENT_SECRET` | Manual, 6-month cadence |
| `BWS_ACCESS_TOKEN` (Worker) | Manual, 12-month cadence |
| `LINKEDIN_REFRESH_TOKEN` | Auto on every refresh |

The `linkedin-token-refresh` cron (weekly) reads `LINKEDIN_TOKEN_ISSUED_AT` and computes days-to-expiry. When days_remaining < 14 it alerts the user via the configured cron target.