# Trademark banlist compliance — linkedin-mcp

This package is `linkedin-mcp` everywhere public. The org's trademark banlist (see memory) bans upstream product names from user-facing surfaces; carve-outs cover internal references to APIs as long as they do not propagate.

## What we use internally (allowed)
- Reference docs URLs: `learn.microsoft.com/en-us/linkedin/...` — fine, these are Microsoft Learn paths.
- Class name `LinkedInClient` and `LinkedInSettings` — code internal, not user-facing.
- Token env var `LINKEDIN_ACCESS_TOKEN` — internal, follows env-var convention.
- Documentation in code/docstrings that names the upstream API endpoints verbatim (e.g. `POST /v2/ugcPosts`).

## What we do NOT use
- Container names: NOT `linkedin-bot`, NOT `linkedin-poster`, NOT `linkedin-something`. Use `linkedin-mcp` or `linkedin-oauth` only.
- Worker names on Cloudflare: `linkedin-oauth-callback` is fine (matches package); do NOT name them after trademarks.
- Public-facing README headlines: avoid naming upstream products in titles.
- Commit messages: no trademarks in subject lines.
- DNS records: no trademarked subdomains.

## Banned list (mechanical enforcement, from memory)
`mensaje mensajebusiness mensaje-web wpp facebook meta instagram insta messenger oculus paypal stripe google gmail youtube tiktok twitter x-com discord slack microsoft office365 apple icloud amazon aws- openai chatgpt anthropic claude`

LinkedIn is **not** on the banlist (it's the company name, not a product-trademark dispute), but we still keep package naming neutral and internal for safety.

## Reasoning
This was scoped narrowly: the banlist exists because Hostinger suspended `srv1396188.hstgr.cloud` 2026-Q1 over `mensajeconnect.paragu-ai.com` flagged as phishing impersonation. The list is defensive, not litigious. We extend the same hygiene to upstream products we integrate with as a defensive posture.