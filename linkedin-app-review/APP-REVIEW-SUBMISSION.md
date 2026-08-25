# LinkedIn App Review — Submission Package

Submission package for Ai-Whisperers' LinkedIn App, requesting approval for **`Sign In with LinkedIn using OpenID Connect`** + **`Share on LinkedIn`** products (scope: `w_member_social` for personal-profile posting by Ai-Whisperers staff).

---

## App metadata

| Field | Value |
|---|---|
| App name | Ai-Whisperers Hermes |
| Company name | Ai-Whisperers (Asunción, Paraguay) |
| App type | Internal tooling for company content publishing |
| Products requested | Sign In with LinkedIn (OIDC), Share on LinkedIn |
| Scopes requested | `openid profile email w_member_social` |
| Authorized redirect URI | `https://auth.hermes.paragu-ai.com/auth/linkedin/callback` |
| App URL | `https://hermes.paragu-ai.com` |
| Privacy policy URL | `https://hermes.paragu-ai.com/privacy` |
| Terms of service URL | `https://hermes.paragu-ai.com/terms` |

---

## Use case description (paste into "App usage")

> Ai-Whisperers operates an autonomous AI content-publishing system ("Hermes")
> that helps our team draft and schedule LinkedIn posts on behalf of our
> employees' personal profiles, with explicit per-user OAuth consent.
>
> **What we do:**
> - Allow an authenticated user to compose a LinkedIn post (text, image, or video).
> - Submit that post to the LinkedIn API on behalf of the user under their own
>   LinkedIn identity, using OAuth 2.0 with the `w_member_social` scope.
> - Retrieve and delete posts we created (audit trail).
>
> **What we do NOT do:**
> - We do not scrape public profiles, send InMail, send connection requests,
>   or post on behalf of users who have not actively granted us OAuth consent.
> - We do not store or sell member data. We use the OIDC `email` and `profile`
>   claims only to identify which Ai-Whisperers team member is signed in.
> - We do not bulk-post or spam. Each post is reviewed by the authenticated
>   user before submission.
>
> **Volume:** estimated 5-20 posts per day across all team members combined.
> **Users:** Ai-Whisperers internal staff only (currently <10 accounts).
>
> We request approval for the `w_member_social` (Share on LinkedIn) and the
> OpenID Connect profile/email scopes to enable this workflow.

---

## Verification steps for LinkedIn reviewer

LinkedIn reviewers should be able to validate the integration end-to-end. Below is the walkthrough we expect the reviewer to follow.

### Step 1 — Visit the app
Open `https://hermes.paragu-ai.com/auth/linkedin/start` in a browser.

Expected: 302 redirect to `https://www.linkedin.com/oauth/v2/authorization?...` with the `state` parameter present.

### Step 2 — Sign in
Sign in with a LinkedIn test account (we will provide one below).

Expected: LinkedIn shows the standard consent screen listing the requested scopes (`openid profile email w_member_social`).

### Step 3 — Grant consent
Click "Allow".

Expected: 302 redirect back to `https://auth.hermes.paragu-ai.com/auth/linkedin/callback?code=...&state=...`. The callback page shows "LinkedIn connected ✓" with a successful BWS secret write.

### Step 4 — Confirm Hermes post flow
Open `https://hermes.paragu-ai.com/test/post` (reviewer-only test endpoint — disabled in production).

Expected: A simple form to enter commentary. Submitting it calls `POST /rest/posts` with the user's stored `w_member_social` token. A success message shows the new post's URN and a permalink to it on the user's profile.

### Step 5 — Inspect post
Open the post permalink returned in Step 4 on the test user's profile.

Expected: The post is visible, attributed to the test user (not Ai-Whisperers), and contains exactly the commentary entered in Step 4.

### Step 6 — Delete via Hermes
From `https://hermes.paragu-ai.com/test/post`, click "Delete".

Expected: The post is removed from the user's profile within seconds. The Hermes UI shows "deleted" with the post URN.

---

## Test credentials (provide to LinkedIn)

> **Do not include in public PRs. These are for the App Review submission form only.**

```
LinkedIn email:    linkedin-reviewer@aiwhisperers.com
LinkedIn password: <provided via secure channel>
2FA:              TOTP (Authenticator app), recovery codes in BWS
Person URN:       urn:li:person:XXXXXXXX
```

---

## Demo video script (60-90 sec, record and upload to LinkedIn reviewer portal)

```
[0:00] Screen: show https://hermes.paragu-ai.com dashboard. Narrate:
       "This is the Hermes dashboard for Ai-Whisperers, an internal AI agent
       system that helps our team draft and schedule LinkedIn posts."

[0:08] Click "Connect LinkedIn". Show the LinkedIn authorize screen.
       Narrate: "The user clicks Connect, gets the standard LinkedIn
       consent screen — Hermes only requests openid profile email and
       w_member_social scope, which is the minimum needed for posting
       on behalf of the authenticated user."

[0:18] Click "Allow". Show the Hermes success page.
       Narrate: "After consent, the OAuth callback writes the access
       token to our secrets manager. The token never appears in chat
       or in the browser URL."

[0:28] Open the Hermes "Compose Post" page.
       Narrate: "The user writes a post — this is text, but our
       endpoint also supports image and video uploads via the
       register+upload asset protocol."

[0:42] Click "Publish". Show the success message with the post URN.
       Narrate: "Hermes calls POST /rest/posts with the user's own
       access token. The post is attributed to the user, not to
       Ai-Whisperers. The post is visible on the user's profile."

[0:55] Open the LinkedIn profile of the test user. Show the post is live.
       Narrate: "Here's the post — it shows up exactly as if the user
       had posted it manually. We never post without per-user OAuth
       consent."

[1:05] Back in Hermes, click "Delete".
       Narrate: "We can also delete posts we created, which keeps
       us in line with LinkedIn's terms of service for the API."

[1:15] End. "Thank you. We're happy to provide more demos for the
       reviewer."
```

---

## Production deployment references

- LinkedIn App ID: `XXXXXX` (filled by LinkedIn after App creation)
- LinkedIn App Secret: stored in BWS, never shared in chat
- Hermes MCP server: `linkedin-mcp` (org-internal naming, no upstream trademarks)
- OAuth callback worker: `linkedin-oauth` hosted at `auth.hermes.paragu-ai.com`

---

## Approval window expectations

- **Expected first review:** 1-3 weeks for `w_member_social`.
- **Escalation path:** `linkedin-api-partner-support` if no response after 14 days.
- **Realistic for `w_organization_social` (org posting):** weeks to months via Community Management API partner program. Not requested in this submission.