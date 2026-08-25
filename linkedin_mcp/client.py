"""Thin httpx wrapper around the LinkedIn REST APIs.

Endpoints covered:
  - Posts (new):    POST /rest/posts, GET /rest/posts/{id}
  - UGC (legacy):   POST /v2/ugcPosts, GET /v2/ugcPosts/{id}  (kept for Share on LinkedIn use)
  - Assets:         POST /rest/assets, GET /rest/assets/{id}   (register + upload media)
  - Profile:        GET /v2/userinfo                           (Sign In w/ LinkedIn OIDC)
  - Org social:     GET /rest/organizationalEntityShareStatistics, /rest/posts

Per LinkedIn partner-program rules, organic posting requires:
  - `w_member_social`        (personal posts)
  - `w_organization_social`  (company-page posts)
  - `r_organization_social`  (read company-page analytics)

All write methods require:
  - Header `Linkedin-Version: YYYYMM`
  - Header `X-Restli-Protocol-Version: 2.0.0`

Every method raises `LinkedInError` on non-2xx so the MCP tool layer can quote
the canonical envelope to the caller.
"""
from __future__ import annotations
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
import httpx
from .config import get_settings

log = logging.getLogger(__name__)


class LinkedInError(RuntimeError):
    """Raised on any non-2xx LinkedIn response. Carries the LinkedIn error
    envelope so the MCP tool layer can surface `serviceErrorCode` and `message`
    to the caller verbatim."""

    def __init__(
        self,
        status: int,
        code: Optional[int] = None,
        message: str = "",
        service_error_code: Optional[int] = None,
    ):
        super().__init__(f"LinkedIn API error {status} (code={code}, svc={service_error_code}): {message}")
        self.status = status
        self.code = code
        self.message = message
        self.service_error_code = service_error_code


class LinkedInClient:
    def __init__(self, settings=None):
        self.s = settings or get_settings()
        self._client: Optional[httpx.AsyncClient] = None
        self._hour_window: List[float] = []

    async def _ensure(self):
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.s.linkedin_api_base,
                timeout=httpx.Timeout(30.0, connect=10.0),
                headers={
                    "Authorization": f"Bearer {self.s.linkedin_access_token}",
                    "Linkedin-Version": self.s.linkedin_api_version,
                    "X-Restli-Protocol-Version": "2.0.0",
                    "User-Agent": "linkedin-mcp/0.1 (+internal)",
                },
            )

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _throttle(self):
        now = time.monotonic()
        cutoff = now - 3600.0
        self._hour_window = [t for t in self._hour_window if t > cutoff]
        if len(self._hour_window) >= self.s.linkedin_rate_per_hour:
            raise LinkedInError(429, None, "Per-client rate cap exceeded. Pause until next hour.")

    def _common_headers(self) -> Dict[str, str]:
        return {
            "Linkedin-Version": self.s.linkedin_api_version,
            "X-Restli-Protocol-Version": "2.0.0",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        await self._ensure()
        await self._throttle()
        h = dict(self._common_headers())
        if headers:
            h.update(headers)
        try:
            r = await self._client.request(
                method,
                path.lstrip("/"),
                json=json,
                params=params,
                headers=h,
            )
        except httpx.HTTPError as e:
            raise LinkedInError(0, None, f"transport error: {e}") from e

        if r.status_code >= 400:
            # LinkedIn error envelope is JSON like:
            # {"serviceErrorCode": 100, "message": "...", "status": 401, ...}
            try:
                body = r.json()
            except Exception:
                body = {"message": r.text[:500]}
            raise LinkedInError(
                status=r.status_code,
                code=body.get("status"),
                message=body.get("message", "(no message)"),
                service_error_code=body.get("serviceErrorCode"),
            )
        # 2xx — return parsed JSON if any, else {}
        if not r.content:
            return {}
        try:
            return r.json()
        except Exception:
            return {"raw": r.text[:2000]}

    # ============== PROFILE (Sign In w/ LinkedIn OIDC) ==============

    async def get_userinfo(self) -> Dict[str, Any]:
        """OpenID Connect userinfo — name, headline, email, sub."""
        return await self._request("GET", "/v2/userinfo")

    # ============== ASSET UPLOAD (for image/video posts) ==============

    async def register_asset_upload(
        self,
        owner_urn: str,
        *,
        media_type: str = "image",
        filename: str = "asset.jpg",
    ) -> Dict[str, Any]:
        """Step 1 of image/video upload. Returns the upload URL + asset URN."""
        # LinkedIn upload protocol:
        # https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api
        # Body shape (image): {"registerUploadRequest": {"recipes": [...], "owner": "...", "filename": "..."}}
        recipes = (
            ["urn:li:digitalmediaRecipe:feedshare-image"]
            if media_type == "image"
            else ["urn:li:digitalmediaRecipe:feedshare-video"]
        )
        return await self._request(
            "POST",
            "/rest/assets?action=registerUpload",
            json={
                "registerUploadRequest": {
                    "owner": owner_urn,
                    "recipes": recipes,
                    "filename": filename,
                }
            },
        )

    async def upload_asset_bytes(self, upload_url: str, content: bytes, content_type: str = "image/jpeg") -> Dict[str, Any]:
        """Step 2: PUT the binary to the returned upload URL."""
        # upload_url is a one-time signed URL returned by register_asset_upload
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0)) as c:
            r = await c.put(
                upload_url,
                content=content,
                headers={"Content-Type": content_type, "Authorization": "Bearer " + self.s.linkedin_access_token},
            )
        if r.status_code >= 400:
            raise LinkedInError(r.status_code, None, f"asset upload failed: {r.text[:300]}")
        return {"status": r.status_code}

    # ============== POSTS (new Posts API) ==============

    async def create_post(
        self,
        *,
        author_urn: str,
        commentary: str,
        visibility: str = "PUBLIC",
        media_urn: Optional[str] = None,
        media_category: Optional[str] = None,
        distribution_feed: bool = True,
    ) -> Dict[str, Any]:
        """Create a post via the new Posts API (`/rest/posts`)."""
        body: Dict[str, Any] = {
            "author": author_urn,
            "commentary": commentary[:3000],  # hard cap
            "visibility": visibility,
            "distribution": {
                "feedDistribution": "MAIN_FEED" if distribution_feed else "NONE",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        if media_urn and media_category:
            body["content"] = {"media": {"id": media_urn, "title": commentary[:200]}}
            body["content"]["media"]["mediaCategory"] = media_category  # IMAGE / VIDEO / DOCUMENT / ARTICLE
        return await self._request("POST", "/rest/posts", json=body)

    async def get_post(self, post_urn: str) -> Dict[str, Any]:
        return await self._request("GET", f"/rest/posts/{post_urn}")

    async def delete_post(self, post_urn: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/rest/posts/{post_urn}")

    # ============== UGC (legacy — kept for Share on LinkedIn) ==============

    async def create_ugc_post(
        self,
        *,
        author_urn: str,
        text: str,
        media_urns: Optional[List[str]] = None,
        media_category: Optional[str] = None,
        article_url: Optional[str] = None,
        article_title: Optional[str] = None,
        visibility: str = "PUBLIC",
    ) -> Dict[str, Any]:
        """Create a UGC post (Share on LinkedIn path). Use for member-level posts
        with `w_member_social`. The Posts API is preferred for new code."""
        share_media_category = media_category or "NONE"
        media = []
        for urn in media_urns or []:
            media.append({"status": "READY", "media": urn, "description": {"text": ""}})
        if article_url and article_title:
            media.append({
                "status": "READY",
                "originalUrl": article_url,
                "title": {"text": article_title},
            })
        body = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": visibility},
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text[:3000]},
                    "shareMediaCategory": share_media_category,
                    "media": media,
                }
            },
        }
        return await self._request("POST", "/v2/ugcPosts", json=body)

    # ============== SANITY ==============

    async def sanity_ping(self) -> Dict[str, Any]:
        """Cheap check that the token + version headers work."""
        return await self._request("GET", "/v2/userinfo")