"""Configuration for linkedin-mcp. Reads from env / .env only.

Required env:
    LINKEDIN_CLIENT_ID         — from LinkedIn App → Auth → Credentials
    LINKEDIN_CLIENT_SECRET     — same place
    LINKEDIN_ACCESS_TOKEN      — long-lived OAuth2 token, scope `w_member_social`
                                  (personal posts) OR `w_organization_social`
                                  + `r_organization_social` for company-page
                                  posting + analytics.
    LINKEDIN_PERSON_URN        — urn:li:person:{id} for member posts
                                  (only required if posting as a member)
    LINKEDIN_ORG_URN           — urn:li:organization:{id} for org posts
                                  (only required if posting as a page)

Optional env:
    LINKEDIN_REDIRECT_URI      — OAuth callback URL, must match App config.
                                  Defaults to https://hermes.paragu-ai.com/auth/linkedin/callback
    LINKEDIN_API_VERSION       — YYYYMM, default 202608
    LINKEDIN_API_BASE          — default https://api.linkedin.com
    LINKEDIN_RATE_PER_HOUR     — defensive throttle, default 800
    LINKEDIN_ENV_FILE          — override .env path
"""
from __future__ import annotations
import os
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LinkedInSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.environ.get("LINKEDIN_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- OAuth credentials ---
    linkedin_client_id: str = Field(...)
    linkedin_client_secret: str = Field(...)
    linkedin_access_token: str = Field(
        ..., description="Long-lived OAuth2 access token (60d, refresh via cron)."
    )
    linkedin_redirect_uri: str = Field(
        default="https://hermes.paragu-ai.com/auth/linkedin/callback"
    )

    # --- Identities ---
    linkedin_person_urn: Optional[str] = Field(
        default=None, description="urn:li:person:{id} for personal posts."
    )
    linkedin_org_urn: Optional[str] = Field(
        default=None, description="urn:li:organization:{id} for company-page posts."
    )

    # --- API config ---
    linkedin_api_version: str = Field(default="202608")
    linkedin_api_base: str = Field(default="https://api.linkedin.com")
    linkedin_rate_per_hour: int = Field(default=800)

    @field_validator("linkedin_access_token")
    @classmethod
    def _strip_token(cls, v: str) -> str:
        return v.strip()


def get_settings() -> LinkedInSettings:
    return LinkedInSettings()