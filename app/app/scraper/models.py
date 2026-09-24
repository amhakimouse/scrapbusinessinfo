"""Data shape for one scraped lead.

Kept intentionally flat (no nested objects) because it gets dumped
straight into a spreadsheet-style table in the frontend.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class Lead(BaseModel):
    domain: str
    url: str
    business_name: str | None = None
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    social_links: dict[str, str] = Field(default_factory=dict)  # e.g. {"instagram": "..."}
    niche_signal: str | None = None       # short text snippet that suggests it's an Amazon affiliate
    about_snippet: str | None = None      # business/blog description from meta or about page
    contact_url: str | None = None        # URL of the contact/about page where info was found
    source_keyword: str | None = None     # which seed/keyword led us here
    status: str = "scraped"               # scraped | no_email | error
    scraped_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def primary_email(self) -> str:
        return self.emails[0] if self.emails else ""
