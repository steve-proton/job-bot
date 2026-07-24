"""Schema + dedupe + tracking round-trips against an in-memory DB."""

from jobbot import db
from jobbot.models import Application, Evaluation, Interview, Job


def make_db():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return conn


def sample_job(**over):
    base = dict(
        source="greenhouse", external_id="1", company="Acme",
        title="Senior Engineer", url="https://x/1",
    )
    base.update(over)
    return Job(**base)


def test_upsert_dedupes_on_source_and_external_id():
    conn = make_db()
    job_id, inserted = db.upsert_job(conn, sample_job())
    assert inserted is True

    # Same (source, external_id) -> no new row, same id.
    job_id2, inserted2 = db.upsert_job(conn, sample_job(title="Different title"))
    assert inserted2 is False
    assert job_id2 == job_id

    # Different external_id -> new row.
    _id3, inserted3 = db.upsert_job(conn, sample_job(external_id="2"))
    assert inserted3 is True


def test_pending_and_evaluation_flow():
    conn = make_db()
    job_id, _ = db.upsert_job(conn, sample_job())

    assert [j.id for j in db.pending_jobs(conn)] == [job_id]

    db.add_evaluation(
        conn, Evaluation(job_id=job_id, score=82, verdict="strong",
                         reasons="great fit", model="sonnet")
    )
    # Once scored, it drops out of the pending queue.
    assert db.pending_jobs(conn) == []

    matches = db.top_matches(conn)
    assert len(matches) == 1
    assert matches[0]["score"] == 82
    assert matches[0]["verdict"] == "strong"


def test_application_and_interview_tracking():
    conn = make_db()
    job_id, _ = db.upsert_job(conn, sample_job())

    app_id = db.add_application(conn, Application(job_id=job_id, notes="applied via referral"))
    assert db.set_application_status(conn, app_id, "phone_screen") is True
    assert db.get_application(conn, app_id).status == "phone_screen"
    assert db.set_application_status(conn, 999, "onsite") is False  # missing

    intv_id = db.add_interview(
        conn, Interview(application_id=app_id, round="phone screen",
                        scheduled_at="2026-08-01T15:00:00+00:00", interviewer="Dana")
    )
    interviews = db.list_interviews(conn, application_id=app_id)
    assert len(interviews) == 1
    assert interviews[0]["interview_id"] == intv_id
    assert interviews[0]["company"] == "Acme"


def test_foreign_key_cascade():
    conn = make_db()
    job_id, _ = db.upsert_job(conn, sample_job())
    app_id = db.add_application(conn, Application(job_id=job_id))
    db.add_interview(conn, Interview(application_id=app_id, round="screen"))

    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    # Cascades: application and its interview are gone.
    assert db.list_applications(conn) == []
    assert db.list_interviews(conn) == []
