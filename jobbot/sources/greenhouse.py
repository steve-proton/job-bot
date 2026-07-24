"""Greenhouse job-board fetcher.

Public endpoint (no auth):
    GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

Response shape (fields we rely on):
    {"jobs": [
        {"id": 123, "title": "...", "absolute_url": "...",
         "location": {"name": "Remote - US"}, "content": "<escaped html>",
         "updated_at": "2024-...", "company_name"?: "..."}
    ]}
"""

from __future__ import annotations

import html as _html
from typing import Any

from ..models import Job
from ._http import get_client, looks_remote, strip_html

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def fetch(config: dict[str, Any]) -> list[Job]:
    token = config.get("token")
    if not token:
        raise ValueError("greenhouse source requires a 'token'")
    company = config.get("company") or token

    with get_client() as client:
        resp = client.get(API.format(token=token), params={"content": "true"})
        resp.raise_for_status()
        payload = resp.json()

    jobs: list[Job] = []
    for item in payload.get("jobs", []):
        location = (item.get("location") or {}).get("name", "") or ""
        # Greenhouse "content" is HTML-escaped, so unescape once before stripping.
        raw_content = _html.unescape(item.get("content") or "")
        title = item.get("title", "") or ""
        jobs.append(
            Job(
                source="greenhouse",
                external_id=str(item.get("id")),
                company=item.get("company_name") or company,
                title=title,
                url=item.get("absolute_url", "") or "",
                location=location,
                remote=looks_remote(location, title),
                description=strip_html(raw_content),
                posted_at=item.get("updated_at", "") or "",
            )
        )
    return jobs
