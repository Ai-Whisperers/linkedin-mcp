---
name: linkedin-mcp
description: 'Post to LinkedIn on behalf of a member via the official Posts API. Use when user asks to draft/publish LinkedIn posts, schedule content, or check post analytics.'
version: 0.1.0
author: Hermes Agent
license: MIT
platforms:
- linux
- macos
metadata:
  hermes:
    tags:
    - linkedin
    - social-media
    - mcp-server
    - content-publishing
provenance:
  owner: team-aiw
  last_review: '2026-08-25'
model_hints:
  temp: 0.3
  top_p: 0.9
alwaysApply: false
id: skill.linkedin.mcp.v1
kind: skill
---

# linkedin-mcp — Posting to LinkedIn via official REST API

This skill is the playbook for the Hermes `linkedin-mcp` server. When the user asks to post on LinkedIn, schedule content, or query LinkedIn analytics, the agent uses tools registered under `mcp_linkedin_mcp_*`.

## When to use

- User asks to "post on LinkedIn", "publish to LinkedIn", "schedule a LinkedIn post".
- User asks to draft LinkedIn content and we are the ones posting it.
- User asks to check the status of a previously published post.
- User asks to delete a post that Hermes published.
- User asks to verify the LinkedIn token is healthy.

When **not** to use:
- User asks to scrape LinkedIn profiles, send connection requests, send InMail, or read arbitrary posts (out of scope — these violate LinkedIn ToS).
- User asks to post on behalf of a company page and we don't have `w_organization_social` approved (the tool will return 403 / `serviceErrorCode: 100`).

## Tool surface

| Tool | Action | Auth scope |
|---|---|---|
| `mcp_linkedin_mcp_get_my_profile` | Read the authenticated member's profile | `openid profile email` |
| `mcp_linkedin_mcp_create_text_post` | Publish a text-only post | `w_member_social` |
| `mcp_linkedin_mcp_create_image_post` | Publish a post with one image (URL must be public) | `w_member_social` |
| `mcp_linkedin_mcp_create_video_post` | Publish a post with one video | `w_member_social` |
| `mcp_linkedin_mcp_create_member_share` | Legacy Share-on-LinkedIn (UGC) member post | `w_member_social` |
| `mcp_linkedin_mcp_get_post` | Fetch one of our posts by URN | `r_member_social` |
| `mcp_linkedin_mcp_delete_post` | Delete a post we created | `w_member_social` |
| `mcp_linkedin_mcp_upload_image_from_url` | Upload an image and get an asset URN | `w_member_social` |
| `mcp_linkedin_mcp_sanity_ping` | Verify token + version headers work | `openid` |

## Standard flows

### Flow 1 — Publish a text post (the common case)

1. Confirm the post text fits (≤3000 chars). If longer, trim or split.
2. Call `mcp_linkedin_mcp_create_text_post(commentary="...", visibility="PUBLIC")`.
3. The result includes the post URN. Surface it to the user.

### Flow 2 — Publish a post with an image

1. Verify the image URL is publicly reachable (Hermes can host on VPS / R2 / CF Pages).
2. Call `mcp_linkedin_mcp_create_image_post(commentary="...", image_url="https://...")`.
3. The tool internally does register-upload → PUT bytes → create post.
4. Return the post URN.

### Flow 3 — Draft-only (don't post)

The user wants a draft but not a publish. Write the commentary to a file (e.g. `~/hermes/scratchpad/li-draft-2026-08-25.md`) and surface a "post now?" CTA. Never auto-publish without explicit confirmation — even with the API, every post is visible to the user's network.

### Flow 4 — Scheduled post

The LinkedIn API does NOT have a native "schedule" endpoint. To schedule, store the draft + intended publish time in a cron schedule; the cron handler will call `create_text_post` at the scheduled moment. We have a `linkedin-publisher` cron ready (see `references/cron.md`).

### Flow 5 — Verify token health (diagnostic)

Call `mcp_linkedin_mcp_sanity_ping`. If it returns 401 or `serviceErrorCode: 100`, the token is invalid or has the wrong scope. Tell the user to re-run OAuth at `https://hermes.paragu-ai.com/auth/linkedin/start`.

## Safety rules

1. **Never auto-post without explicit user confirmation.** The API is one call away from publishing to a professional network.
2. **Never send connection requests, InMail, or DMs** — these are out of scope and violate LinkedIn ToS.
3. **Never mass-post** (e.g. 50 posts in 5 minutes) — LinkedIn's behavioral pattern detection will flag and ban the API app, killing it for all users.
4. **Never store member data beyond what's needed.** The OIDC `email` and `profile` claims are used only to identify the signed-in user.
5. **Honor the write-gate.** If `LINKEDIN_ENABLE_WRITES=false`, the server hides all write tools. This is intentional during the App Review window.
6. **Posts are visible forever.** Even deleted posts may have been seen / cached. Don't post anything the user would regret.

## Error envelope

Every tool returns `{"result": {...}}` on success or `{"error": {"status", "code", "message", "serviceErrorCode"}}` on failure. Common service codes:

| serviceErrorCode | Meaning | Action |
|---|---|---|
| 100 | Token lacks the requested scope | Re-run OAuth with correct scope |
| 401 | Token invalid / expired | Re-run OAuth |
| 403 | Permission denied | Likely App Review not yet approved |
| 422 | Duplicate content (same as recent post) | Edit commentary before retrying |
| 429 | Rate limited | Pause and retry per the Retry-After header |

## Approval state

| Capability | Approval needed | Realistic timeline |
|---|---|---|
| Member posts (`w_member_social`) | App Review | 1-3 weeks |
| Company page posts (`w_organization_social`) | Community Mgmt API partner | weeks-months |
| Read company analytics (`r_organization_social`) | Community Mgmt API partner | weeks-months |
| Member analytics (`r_member_social`) | Currently CLOSED — LinkedIn not accepting requests | n/a |

## Related

- `references/trademark.md` — package-naming rules, no upstream product names
- `references/oauth-worker-contract.md` — what the `linkedin-oauth` CF Worker does
- `linkedin-app-review/APP-REVIEW-SUBMISSION.md` — what to paste into LinkedIn App Review form
- `references/cron.md` — scheduled publisher cron job