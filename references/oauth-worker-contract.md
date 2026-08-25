"""linkedin-oauth-worker — Cloudflare Worker spec for the LinkedIn OAuth callback.

The actual worker lives in a sibling repo (`linkedin-oauth-worker/`). This file
documents the contract the worker must implement. Code below is reference
implementation — the deployed worker is its own repo.

Routes:
  GET /auth/linkedin/start
      - Reads LINKEDIN_CLIENT_ID from env/secrets.
      - Generates state, stores in KV with 10-min TTL.
      - 302 to LinkedIn authorize:
          https://www.linkedin.com/oauth/v2/authorization
            ?response_type=code
            &client_id=...
            &redirect_uri=...
            &state={csrf}
            &scope=openid%20profile%20email%20w_member_social
            (optionally +w_organization_social%20r_organization_social%20r_ads_reporting
             if org posting is approved)

  GET /auth/linkedin/callback?code=...&state=...
      - Validate state from KV.
      - POST https://www.linkedin.com/oauth/v2/accessToken
          grant_type=authorization_code, code, redirect_uri, client_id, client_secret
      - Receive {access_token, expires_in, scope, ...}
      - Write access_token to BWS via REST:
          PUT https://vault.bitwarden.com/api/secrets/{id}
            Authorization: Bearer $BWS_TOKEN
            body: LINKEDIN_ACCESS_TOKEN = <token>
            + LINKEDIN_TOKEN_ISSUED_AT = now ISO 8601
            + LINKEDIN_TOKEN_SCOPES = <scope>
      - Return friendly HTML "LinkedIn connected. Token expires in N days."

  POST /auth/linkedin/refresh
      - For refreshable tokens (offline_access scope). Exchange refresh_token
        for a new access_token. Same write path as callback.

Env (worker, set via `wrangler secret put`):
  LINKEDIN_CLIENT_ID
  LINKEDIN_CLIENT_SECRET
  LINKEDIN_REDIRECT_URI
  BWS_TOKEN               machine token for Bitwarden Secrets Manager
  BWS_SECRET_LINKEDIN_TOKEN   secret UUID for LINKEDIN_ACCESS_TOKEN
  BWS_SECRET_TOKEN_ISSUED_AT  secret UUID for LINKEDIN_TOKEN_ISSUED_AT
  BWS_SECRET_TOKEN_SCOPES      secret UUID for LINKEDIN_TOKEN_SCOPES
  CF_KV_LINKEDIN_STATE        KV namespace binding
"""
# This file is reference only — actual Worker code lives in linkedin-oauth-worker/
from __future__ import annotations
DOCS = """See header docstring above."""