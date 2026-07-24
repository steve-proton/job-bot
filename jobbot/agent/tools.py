"""Custom in-process tools exposed to the agent, plus the MCP server wrapper.

These are the agent's hands: `get_pending_jobs` is how it perceives the work
queue, `record_evaluation` is how it acts, and `fetch_new_jobs` lets it pull
fresh postings. Each tool opens a short-lived SQLite connection (tools run in the
same event loop as the query, so this is safe).
"""

from __future__ import annotations

import json
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from .. import db
from ..ingest import fetch_new_jobs as _ingest
from ..models import VERDICTS, Evaluation

DESC_LIMIT = 900   # chars of description handed to the agent per job


def _text(payload: str) -> dict[str, Any]:
    """Wrap a string as the tool-result content the SDK expects."""
    return {"content": [{"type": "text", "text": payload}]}


@tool(
    "get_pending_jobs",
    "Return unscored jobs (the work queue) as JSON. Each item has job_id, "
    "company, title, location, remote, and a truncated description. Score every "
    "one with record_evaluation.",
    {"limit": int},
)
async def get_pending_jobs(args: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit") or 20)
    conn = db.connect()
    db.init_db(conn)
    try:
        jobs = db.pending_jobs(conn, limit=limit)
    finally:
        conn.close()

    items = [
        {
            "job_id": j.id,
            "company": j.company,
            "title": j.title,
            "location": j.location,
            "remote": j.remote,
            "description": (j.description or "")[:DESC_LIMIT],
        }
        for j in jobs
    ]
    return _text(json.dumps({"count": len(items), "jobs": items}, ensure_ascii=False))


@tool(
    "record_evaluation",
    "Record your fit verdict for one job. score is 0-100; verdict is one of "
    "'strong', 'maybe', 'no'; reasons is a short justification.",
    {"job_id": int, "score": int, "verdict": str, "reasons": str},
)
async def record_evaluation(args: dict[str, Any]) -> dict[str, Any]:
    try:
        job_id = int(args["job_id"])
        score = max(0, min(100, int(args["score"])))
    except (KeyError, TypeError, ValueError):
        return _text("ERROR: job_id and score are required integers.")

    verdict = str(args.get("verdict", "")).lower().strip()
    if verdict not in VERDICTS:
        return _text(f"ERROR: verdict must be one of {', '.join(VERDICTS)}.")

    reasons = str(args.get("reasons", "")).strip()
    model = _current_model()

    conn = db.connect()
    db.init_db(conn)
    try:
        if db.get_job(conn, job_id) is None:
            return _text(f"ERROR: no job with id {job_id}.")
        db.add_evaluation(
            conn,
            Evaluation(job_id=job_id, score=score, verdict=verdict,
                       reasons=reasons, model=model),
        )
    finally:
        conn.close()
    return _text(f"Recorded job {job_id}: {score} ({verdict}).")


@tool(
    "fetch_new_jobs",
    "Poll the configured ATS boards and store any new postings. Returns how many "
    "were fetched and how many were new.",
    {},
)
async def fetch_new_jobs(args: dict[str, Any]) -> dict[str, Any]:
    conn = db.connect()
    db.init_db(conn)
    try:
        result = _ingest(conn)
    finally:
        conn.close()
    return _text(
        json.dumps({"fetched": result.fetched, "inserted": result.inserted,
                    "errors": result.errors})
    )


def _current_model() -> str:
    import os
    return os.environ.get("JOBBOT_MODEL", "sonnet")


def build_server():
    """Create the in-process MCP server exposing the jobbot tools.

    Registered tool names become ``mcp__jobbot__<tool>``; the loop's permission
    gate allows exactly that prefix.
    """
    return create_sdk_mcp_server(
        name="jobbot",
        version="0.1.0",
        tools=[get_pending_jobs, record_evaluation, fetch_new_jobs],
    )
