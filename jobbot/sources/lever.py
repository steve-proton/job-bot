"""Lever job-board fetcher.

Public endpoint (no auth):
    GET https://api.lever.co/v0/postings/{company}?mode=json

Response is a JSON list of postings:
    [{"id": "uuid", "text": "Title", "hostedUrl": "...",
      "categories": {"location": "...", "commitment": "...", "team": "..."},
      "descriptionPlain": "...", "createdAt": 1700000000000,
      "workplaceType": "remote" | "on-site" | "hybrid"}]
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..models import Job
from ._http import get_client, looks_remote

API = "https://api.lever.co/v0/postings/{company}"


def _epoch_ms_to_iso(value: Any) -> str:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return ""


def fetch(config: dict[str, Any]) -> list[Job]:
    company_slug = config.get("company")
    if not company_slug:
        raise ValueError("lever source requires a 'company'")
    display = config.get("display") or company_slug

    with get_client() as client:
        resp = client.get(API.format(company=company_slug), params={"mode": "json"})
        resp.raise_for_status()
        postings = resp.json()

    jobs: list[Job] = []
    for item in postings:
        categories = item.get("categories") or {}
        location = categories.get("location", "") or ""
        workplace = item.get("workplaceType", "") or ""
        title = item.get("text", "") or ""
        jobs.append(
            Job(
                source="lever",
                external_id=str(item.get("id")),
                company=display,
                title=title,
                url=item.get("hostedUrl", "") or item.get("applyUrl", "") or "",
                location=location,
                remote=workplace.lower() == "remote" or looks_remote(location, title),
                description=item.get("descriptionPlain", "") or "",
                posted_at=_epoch_ms_to_iso(item.get("createdAt")),
            )
        )
    return jobs
