"""Ashby job-board fetcher.

Public endpoint (no auth):
    GET https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true

Response shape (fields we rely on):
    {"jobs": [
        {"id": "uuid", "title": "...", "location": "Remote",
         "isRemote": true, "jobUrl": "...", "applyUrl": "...",
         "descriptionPlain": "...", "descriptionHtml": "<...>",
         "publishedAt": "2024-..."}
    ]}
"""

from __future__ import annotations

from typing import Any

from ..models import Job
from ._http import get_client, looks_remote, strip_html

API = "https://api.ashbyhq.com/posting-api/job-board/{board}"


def fetch(config: dict[str, Any]) -> list[Job]:
    board = config.get("board")
    if not board:
        raise ValueError("ashby source requires a 'board'")
    display = config.get("display") or board

    with get_client() as client:
        resp = client.get(
            API.format(board=board), params={"includeCompensation": "true"}
        )
        resp.raise_for_status()
        payload = resp.json()

    jobs: list[Job] = []
    for item in payload.get("jobs", []):
        location = item.get("location", "") or ""
        title = item.get("title", "") or ""
        description = item.get("descriptionPlain") or strip_html(
            item.get("descriptionHtml")
        )
        jobs.append(
            Job(
                source="ashby",
                external_id=str(item.get("id")),
                company=display,
                title=title,
                url=item.get("jobUrl", "") or item.get("applyUrl", "") or "",
                location=location,
                remote=bool(item.get("isRemote")) or looks_remote(location, title),
                description=description,
                posted_at=item.get("publishedAt", "") or "",
            )
        )
    return jobs
