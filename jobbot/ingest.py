"""Fetch postings from configured ATS boards and store new ones in SQLite.

Deterministic — no LLM. This is the "perceive" plumbing the agent loop builds on.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import db
from .config import load_sources
from .sources import fetch_source


@dataclass
class IngestResult:
    fetched: int = 0        # total postings pulled across all boards
    inserted: int = 0       # new jobs added to the DB
    errors: list[str] = None  # per-source error messages

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


def fetch_new_jobs(conn: sqlite3.Connection) -> IngestResult:
    """Poll every configured source, upsert results, return a summary.

    A failure on one board (network error, bad slug) is recorded and skipped so
    the others still ingest.
    """
    result = IngestResult()
    for source in load_sources():
        label = source.get("ats", "?")
        slug = source.get("token") or source.get("company") or source.get("board") or "?"
        try:
            jobs = fetch_source(source)
        except Exception as exc:  # noqa: BLE001 - report and continue
            result.errors.append(f"{label}:{slug} -> {exc}")
            continue

        result.fetched += len(jobs)
        for job in jobs:
            _job_id, inserted = db.upsert_job(conn, job)
            if inserted:
                result.inserted += 1
    return result
