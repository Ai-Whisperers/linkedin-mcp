"""MCP server implementation for linkedin-mcp.

Pattern follows the sibling server social-graph-mcp: low-level mcp.server
registration (not fastmcp decorators), so per-tool structured errors are
preserved end-to-end.

Tool surface (registered as `mcp_linkin_mcp_<tool>`):
  Profile
    - get_my_profile           OIDC userinfo: name, headline, email, sub
  Posts (new /rest/posts)
    - create_text_post        commentary-only post
    - create_image_post       image + commentary
    - create_video_post       video + commentary
    - get_post                fetch a post by URN
    - delete_post             delete a post by URN
  UGC (legacy /v2/ugcPosts)
    - create_member_share     Share on LinkedIn (w_member_social) member post
  Assets
    - upload_image_from_url   two-step: register upload → PUT bytes
  Diagnostics
    - sanity_ping             GET /v2/userinfo — verify token + version headers
"""
from __future__ import annotations
import json
import logging
import os
from typing import Any, Dict, Optional
import asyncio

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .client import LinkedInClient, LinkedInError
from .config import get_settings

log = logging.getLogger("linkedin_mcp")


SERVER_INSTRUCTIONS = """
linkedin-mcp — official LinkedIn REST API surface for the Hermes agent.

Scope (only what this server does):
  - Auth via Sign In with LinkedIn (OIDC) — read member profile.
  - Post on behalf of an authenticated member (`w_member_social`).
  - Post on behalf of an organization page (`w_organization_social`).
  - Read + delete the posts we created.
  - Upload images/videos via the two-step register+PUT asset protocol.

Approval posture:
  - Personal posting requires `Sign In with LinkedIn` + `Share on LinkedIn`
    products approved on the LinkedIn App. App Review typically 1-3 weeks.
  - Organization posting additionally requires `Community Management API`
    partner status — weeks to months. Out of scope here unless `LINKEDIN_ORG_URN`
    is configured and the token has the org scope.

Safety:
  - All write tools are gated by `enable_writes` (default true). Flip to false
    during the App Review window.
  - Each tool returns `{"result": <json>}` on success or
    `{"error": {"status", "code", "message", "serviceErrorCode"}}` with the
    LinkedIn error envelope surfaced.
"""


WRITE_TOOLS = {
    "create_text_post",
    "create_image_post",
    "create_video_post",
    "delete_post",
    "create_member_share",
    "upload_image_from_url",
}


# ---------- Tool registry ----------

TOOLS = [
    # Profile
    ("get_my_profile", "Get the authenticated member's profile (OIDC userinfo).",
        {"type": "object", "properties": {}, "additionalProperties": False}),

    # Posts (new Posts API)
    ("create_text_post", "Create a text-only post (3000 char max commentary).",
        {"type": "object", "properties": {
            "commentary": {"type": "string", "minLength": 1, "maxLength": 3000},
            "visibility": {"type": "string", "enum": ["PUBLIC", "CONNECTIONS", "LOGGED_IN"], "default": "PUBLIC"},
            "author_urn": {"type": "string", "description": "Override author (default = LINKEDIN_PERSON_URN)."},
        }, "required": ["commentary"], "additionalProperties": False}),

    ("create_image_post", "Create a post with one image. Requires the image to be at a publicly-reachable URL.",
        {"type": "object", "properties": {
            "commentary": {"type": "string", "minLength": 1, "maxLength": 3000},
            "image_url": {"type": "string", "format": "uri"},
            "visibility": {"type": "string", "enum": ["PUBLIC", "CONNECTIONS", "LOGGED_IN"], "default": "PUBLIC"},
            "author_urn": {"type": "string"},
        }, "required": ["commentary", "image_url"], "additionalProperties": False}),

    ("create_video_post", "Create a post with a video (mp4). URL must be publicly reachable.",
        {"type": "object", "properties": {
            "commentary": {"type": "string", "minLength": 1, "maxLength": 3000},
            "video_url": {"type": "string", "format": "uri"},
            "visibility": {"type": "string", "enum": ["PUBLIC", "CONNECTIONS", "LOGGED_IN"], "default": "PUBLIC"},
            "author_urn": {"type": "string"},
        }, "required": ["commentary", "video_url"], "additionalProperties": False}),

    ("get_post", "Fetch a post by its URN (urn:li:share:... or urn:li:ugcPost:...).",
        {"type": "object", "properties": {"post_urn": {"type": "string"}}, "required": ["post_urn"], "additionalProperties": False}),

    ("delete_post", "Delete a post by URN. Only works for posts created by this app's token.",
        {"type": "object", "properties": {"post_urn": {"type": "string"}}, "required": ["post_urn"], "additionalProperties": False}),

    # UGC (legacy /v2/ugcPosts)
    ("create_member_share", "Create a Share-on-LinkedIn member post (uses `w_member_social` legacy UGC endpoint).",
        {"type": "object", "properties": {
            "text": {"type": "string", "minLength": 1, "maxLength": 3000},
            "media_urns": {"type": "array", "items": {"type": "string"}},
            "article_url": {"type": "string"},
            "article_title": {"type": "string"},
            "visibility": {"type": "string", "enum": ["PUBLIC", "CONNECTIONS"], "default": "PUBLIC"},
            "author_urn": {"type": "string"},
        }, "required": ["text"], "additionalProperties": False}),

    # Assets
    ("upload_image_from_url", "Download an image from URL, register upload with LinkedIn, PUT the bytes. Returns asset URN.",
        {"type": "object", "properties": {
            "image_url": {"type": "string", "format": "uri"},
            "filename": {"type": "string", "default": "post-image.jpg"},
            "author_urn": {"type": "string"},
        }, "required": ["image_url"], "additionalProperties": False}),

    # Diagnostics
    ("sanity_ping", "Verify the configured access token works (cheap GET /v2/userinfo).",
        {"type": "object", "properties": {}, "additionalProperties": False}),
]


# ---------- Server bootstrap ----------

def _build_tool_objects() -> list[Tool]:
    out: list[Tool] = []
    for name, desc, schema in TOOLS:
        out.append(Tool(
            name=name,
            description=desc,
            inputSchema=schema,
        ))
    return out


def _resolve_author(provided: Optional[str], settings) -> str:
    """Honor explicit author_urn, else default to person URN, else org URN."""
    if provided:
        return provided
    if settings.linkedin_person_urn:
        return settings.linkedin_person_urn
    if settings.linkedin_org_urn:
        return settings.linkedin_org_urn
    raise LinkedInError(0, None, "No author_urn provided and neither LINKEDIN_PERSON_URN nor LINKEDIN_ORG_URN is configured.")


async def _run() -> None:
    server = Server("linkedin-mcp")
    settings = get_settings()
    enable_writes = os.environ.get("LINKEDIN_ENABLE_WRITES", "true").lower() in ("1", "true", "yes")

    tool_objects = _build_tool_objects()
    tool_by_name = {t.name: t for t in tool_objects}

    @server.list_tools()
    async def list_tools():
        if enable_writes:
            return tool_objects
        # Hide write tools during App Review / dry-run
        return [t for t in tool_objects if t.name not in WRITE_TOOLS]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        if name in WRITE_TOOLS and not enable_writes:
            return [{"type": "text", "text": json.dumps({"error": {
                "status": 423, "code": "WRITES_DISABLED",
                "message": "Write tools are disabled (LINKEDIN_ENABLE_WRITES=false). Flip once the App Review is approved."
            }})}]

        client = LinkedInClient(settings)
        try:
            result: Dict[str, Any]

            if name == "get_my_profile":
                result = await client.get_userinfo()
            elif name == "sanity_ping":
                result = await client.sanity_ping()
            elif name == "create_text_post":
                result = await client.create_post(
                    author_urn=_resolve_author(arguments.get("author_urn"), settings),
                    commentary=arguments["commentary"],
                    visibility=arguments.get("visibility", "PUBLIC"),
                )
            elif name == "create_image_post":
                author = _resolve_author(arguments.get("author_urn"), settings)
                asset = await client.register_asset_upload(author, media_type="image", filename="post-image.jpg")
                # Upload bytes from image_url
                import httpx as _hx
                async with _hx.AsyncClient(timeout=60.0) as c:
                    r = await c.get(arguments["image_url"])
                    r.raise_for_status()
                    img_bytes = r.content
                upload_url = (
                    asset.get("value", {}).get("uploadMechanism", {})
                        .get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {})
                        .get("uploadUrl")
                )
                asset_urn = asset.get("value", {}).get("asset")
                if not upload_url or not asset_urn:
                    raise LinkedInError(0, None, f"register_asset_upload missing uploadUrl/asset: {asset}")
                await client.upload_asset_bytes(upload_url, img_bytes, content_type="image/jpeg")
                result = await client.create_post(
                    author_urn=author,
                    commentary=arguments["commentary"],
                    visibility=arguments.get("visibility", "PUBLIC"),
                    media_urn=asset_urn,
                    media_category="IMAGE",
                )
            elif name == "create_video_post":
                author = _resolve_author(arguments.get("author_urn"), settings)
                asset = await client.register_asset_upload(author, media_type="video", filename="post-video.mp4")
                import httpx as _hx
                async with _hx.AsyncClient(timeout=300.0) as c:
                    r = await c.get(arguments["video_url"])
                    r.raise_for_status()
                    video_bytes = r.content
                upload_url = (
                    asset.get("value", {}).get("uploadMechanism", {})
                        .get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {})
                        .get("uploadUrl")
                )
                asset_urn = asset.get("value", {}).get("asset")
                if not upload_url or not asset_urn:
                    raise LinkedInError(0, None, f"register_asset_upload missing uploadUrl/asset: {asset}")
                await client.upload_asset_bytes(upload_url, video_bytes, content_type="video/mp4")
                result = await client.create_post(
                    author_urn=author,
                    commentary=arguments["commentary"],
                    visibility=arguments.get("visibility", "PUBLIC"),
                    media_urn=asset_urn,
                    media_category="VIDEO",
                )
            elif name == "get_post":
                result = await client.get_post(arguments["post_urn"])
            elif name == "delete_post":
                result = await client.delete_post(arguments["post_urn"])
            elif name == "create_member_share":
                result = await client.create_ugc_post(
                    author_urn=_resolve_author(arguments.get("author_urn"), settings),
                    text=arguments["text"],
                    media_urns=arguments.get("media_urns"),
                    article_url=arguments.get("article_url"),
                    article_title=arguments.get("article_title"),
                    visibility=arguments.get("visibility", "PUBLIC"),
                )
            elif name == "upload_image_from_url":
                author = _resolve_author(arguments.get("author_urn"), settings)
                asset = await client.register_asset_upload(author, media_type="image", filename=arguments.get("filename", "post-image.jpg"))
                import httpx as _hx
                async with _hx.AsyncClient(timeout=60.0) as c:
                    r = await c.get(arguments["image_url"])
                    r.raise_for_status()
                    img_bytes = r.content
                upload_url = (
                    asset.get("value", {}).get("uploadMechanism", {})
                        .get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {})
                        .get("uploadUrl")
                )
                asset_urn = asset.get("value", {}).get("asset")
                if not upload_url or not asset_urn:
                    raise LinkedInError(0, None, f"register_asset_upload missing uploadUrl/asset: {asset}")
                await client.upload_asset_bytes(upload_url, img_bytes, content_type="image/jpeg")
                result = {"asset_urn": asset_urn, "upload_url_expires_in_minutes": 60}
            else:
                return [{"type": "text", "text": json.dumps({"error": {
                    "status": 404, "code": "UNKNOWN_TOOL", "message": f"no tool named {name}"
                }})}]

            return [{"type": "text", "text": json.dumps({"result": result})}]

        except LinkedInError as e:
            return [{"type": "text", "text": json.dumps({"error": {
                "status": e.status,
                "code": e.code,
                "message": e.message,
                "serviceErrorCode": e.service_error_code,
            }})}]
        except Exception as e:
            log.exception("tool %s failed", name)
            return [{"type": "text", "text": json.dumps({"error": {
                "status": 500, "code": "UNHANDLED", "message": f"{type(e).__name__}: {e}"
            }})}]
        finally:
            await client.close()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="linkedin-mcp",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities={},
                ),
            ),
        )


def main() -> None:
    logging.basicConfig(level=os.environ.get("LINKEDIN_LOG_LEVEL", "INFO"))
    asyncio.run(_run())


if __name__ == "__main__":
    main()