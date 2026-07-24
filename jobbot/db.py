"""SQLite schema and access helpers.

One module owns the connection and every query. Rows are converted to/from the
dataclasses in :mod:`jobbot.models`. Uses stdlib ``sqlite3`` — no ORM.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .models import Application, Evaluation, Interview, Job

DEFAULT_DB = "jobbot.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,
    external_id  TEXT NOT NULL,
    company      TEXT NOT NULL,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL,
    location     TEXT NOT NULL DEFAULT '',
    remote       INTEGER NOT NULL DEFAULT 0,
    description  TEXT NOT NULL DEFAULT '',
    posted_at    TEXT NOT NULL DEFAULT '',
    fetched_at   TEXT NOT NULL,
    UNIQUE(source, external_id)
);

CREATE TABLE IF NOT EXISTS evaluations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    score       INTEGER NOT NULL,
    verdict     TEXT NOT NULL,
    reasons     TEXT NOT NULL DEFAULT '',
    model       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'applied',
    applied_at  TEXT NOT NULL,
    notes       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS interviews (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id    INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    round             TEXT NOT NULL DEFAULT '',
    scheduled_at      TEXT NOT NULL DEFAULT '',
    interviewer       TEXT NOT NULL DEFAULT '',
    notes             TEXT NOT NULL DEFAULT '',
    calendar_event_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_eval_job   ON evaluations(job_id);
CREATE INDEX IF NOT EXISTS idx_app_job    ON applications(job_id);
CREATE INDEX IF NOT EXISTS idx_intv_app   ON interviews(application_id);
"""


def db_path() -> str:
    """Resolve the database path (env override wins, else the default file)."""
    return os.environ.get("JOBBOT_DB", DEFAULT_DB)


def connect(path: str | None = None) -> sqlite3.Connection:
    """Open a connection with row access by name and FK enforcement on."""
    target = path or db_path()
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables and indexes if they don't exist."""
    conn.executescript(SCHEMA)
    conn.commit()


# ---------------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------------

def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        source=row["source"],
        external_id=row["external_id"],
        company=row["company"],
        title=row["title"],
        url=row["url"],
        location=row["location"],
        remote=bool(row["remote"]),
        description=row["description"],
        posted_at=row["posted_at"],
        fetched_at=row["fetched_at"],
    )


def upsert_job(conn: sqlite3.Connection, job: Job) -> tuple[int, bool]:
    """Insert a job if new. Returns (job_id, inserted).

    Dedupe key is (source, external_id). An existing job is left untouched so we
    don't clobber a description with a later empty fetch; ``inserted`` is False.
    """
    cur = conn.execute(
        "SELECT id FROM jobs WHERE source = ? AND external_id = ?",
        (job.source, job.external_id),
    )
    existing = cur.fetchone()
    if existing is not None:
        return existing["id"], False

    cur = conn.execute(
        """
        INSERT INTO jobs
            (source, external_id, company, title, url, location, remote,
             description, posted_at, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job.source, job.external_id, job.company, job.title, job.url,
            job.location, int(job.remote), job.description, job.posted_at,
            job.fetched_at,
        ),
    )
    conn.commit()
    return int(cur.lastrowid), True


def get_job(conn: sqlite3.Connection, job_id: int) -> Job | None:
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


def pending_jobs(
    conn: sqlite3.Connection,
    limit: int = 50,
    prioritize_terms: list[str] | None = None,
) -> list[Job]:
    """Jobs that have no evaluation yet — the agent's work queue.

    When ``prioritize_terms`` is given, jobs whose title contains any of the
    terms are returned first (then newest). This lets a bounded run spend its
    budget on the most relevant roles instead of wading through the whole board.
    """
    terms = [t.strip().lower() for t in (prioritize_terms or []) if t and t.strip()]
    if terms:
        # A CASE expression flags title matches; ties break on recency.
        match_sql = " OR ".join("instr(lower(j.title), ?) > 0" for _ in terms)
        rows = conn.execute(
            f"""
            SELECT j.* FROM jobs j
            LEFT JOIN evaluations e ON e.job_id = j.id
            WHERE e.id IS NULL
            ORDER BY (CASE WHEN {match_sql} THEN 1 ELSE 0 END) DESC,
                     j.fetched_at DESC
            LIMIT ?
            """,
            (*terms, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT j.* FROM jobs j
            LEFT JOIN evaluations e ON e.job_id = j.id
            WHERE e.id IS NULL
            ORDER BY j.fetched_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_job(r) for r in rows]


# ---------------------------------------------------------------------------
# evaluations
# ---------------------------------------------------------------------------

def add_evaluation(conn: sqlite3.Connection, ev: Evaluation) -> int:
    cur = conn.execute(
        """
        INSERT INTO evaluations (job_id, score, verdict, reasons, model, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ev.job_id, ev.score, ev.verdict, ev.reasons, ev.model, ev.created_at),
    )
    conn.commit()
    return int(cur.lastrowid)


def top_matches(conn: sqlite3.Connection, limit: int = 20, min_score: int = 0) -> list[dict]:
    """Best-scored jobs (latest evaluation per job) joined with job details."""
    rows = conn.execute(
        """
        SELECT j.id AS job_id, j.company, j.title, j.location, j.url,
               e.score, e.verdict, e.reasons
        FROM jobs j
        JOIN evaluations e ON e.job_id = j.id
        JOIN (
            SELECT job_id, MAX(created_at) AS latest
            FROM evaluations GROUP BY job_id
        ) latest ON latest.job_id = e.job_id AND latest.latest = e.created_at
        WHERE e.score >= ?
        ORDER BY e.score DESC
        LIMIT ?
        """,
        (min_score, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# applications
# ---------------------------------------------------------------------------

def add_application(conn: sqlite3.Connection, app: Application) -> int:
    cur = conn.execute(
        "INSERT INTO applications (job_id, status, applied_at, notes) VALUES (?, ?, ?, ?)",
        (app.job_id, app.status, app.applied_at, app.notes),
    )
    conn.commit()
    return int(cur.lastrowid)


def set_application_status(conn: sqlite3.Connection, app_id: int, status: str) -> bool:
    cur = conn.execute(
        "UPDATE applications SET status = ? WHERE id = ?", (status, app_id)
    )
    conn.commit()
    return cur.rowcount > 0


def get_application(conn: sqlite3.Connection, app_id: int) -> Application | None:
    row = conn.execute(
        "SELECT * FROM applications WHERE id = ?", (app_id,)
    ).fetchone()
    if not row:
        return None
    return Application(
        id=row["id"], job_id=row["job_id"], status=row["status"],
        applied_at=row["applied_at"], notes=row["notes"],
    )


def list_applications(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT a.id AS app_id, a.status, a.applied_at, a.notes,
               j.company, j.title, j.url
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        ORDER BY a.applied_at DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# interviews
# ---------------------------------------------------------------------------

def add_interview(conn: sqlite3.Connection, intv: Interview) -> int:
    cur = conn.execute(
        """
        INSERT INTO interviews
            (application_id, round, scheduled_at, interviewer, notes, calendar_event_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (intv.application_id, intv.round, intv.scheduled_at, intv.interviewer,
         intv.notes, intv.calendar_event_id),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_interviews(conn: sqlite3.Connection, application_id: int | None = None) -> list[dict]:
    sql = (
        "SELECT i.id AS interview_id, i.application_id, i.round, i.scheduled_at, "
        "i.interviewer, i.notes, j.company, j.title "
        "FROM interviews i "
        "JOIN applications a ON a.id = i.application_id "
        "JOIN jobs j ON j.id = a.job_id "
    )
    params: tuple = ()
    if application_id is not None:
        sql += "WHERE i.application_id = ? "
        params = (application_id,)
    sql += "ORDER BY i.scheduled_at"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]
