"""Shared HTTP client and HTML helpers for the ATS fetchers.

Kept separate from ``sources/__init__.py`` so the individual fetcher modules can
import these without a circular import back through the package.
"""

from __future__ import annotations

import html
import re

import httpx

USER_AGENT = "jobbot/0.1 (+https://github.com/steve-proton/job-bot)"
TIMEOUT = 30.0

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]*\n[ \t\n]*")


def get_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=TIMEOUT,
        follow_redirects=True,
    )


def strip_html(raw: str | None) -> str:
    """Best-effort HTML -> plain text for job descriptions."""
    if not raw:
        return ""
    text = html.unescape(raw)
    text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub("\n", text)
    return text.strip()


def looks_remote(*fields: str | None) -> bool:
    """True if any provided text field signals a remote role."""
    blob = " ".join(f for f in fields if f).lower()
    return "remote" in blob
