"""Plain dataclasses mirroring the SQLite schema.

These are lightweight value objects — the source fetchers build `Job`s, and the
db layer reads/writes rows as these types. No ORM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> str:
    """UTC timestamp in ISO-8601, the format stored in every TEXT date column."""
    return datetime.now(timezone.utc).isoformat()


# Allowed application pipeline stages, in rough order.
APPLICATION_STATUSES = (
    "applied",
    "phone_screen",
    "onsite",
    "offer",
    "rejected",
    "withdrawn",
)

# Verdicts the scoring agent assigns.
VERDICTS = ("strong", "maybe", "no")


@dataclass
class Job:
    source: str          # "greenhouse" | "lever" | "ashby"
    external_id: str     # id within that ATS (unique per source)
    company: str
    title: str
    url: str
    location: str = ""
    remote: bool = False
    description: str = ""
    posted_at: str = ""          # ISO-8601 or "" if the ATS didn't provide one
    fetched_at: str = field(default_factory=_now)
    id: int | None = None        # set once persisted


@dataclass
class Evaluation:
    job_id: int
    score: int           # 0-100 fit score
    verdict: str         # one of VERDICTS
    reasons: str
    model: str
    created_at: str = field(default_factory=_now)
    id: int | None = None


@dataclass
class Application:
    job_id: int
    status: str = "applied"      # one of APPLICATION_STATUSES
    applied_at: str = field(default_factory=_now)
    notes: str = ""
    id: int | None = None


@dataclass
class Interview:
    application_id: int
    round: str = ""              # e.g. "phone screen", "system design"
    scheduled_at: str = ""       # ISO-8601
    interviewer: str = ""
    notes: str = ""
    calendar_event_id: str | None = None   # filled by the Calendar phase
    id: int | None = None
