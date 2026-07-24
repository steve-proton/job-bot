"""Ingest orchestration: dedupe across runs and per-source error isolation.

We stub the network by monkeypatching the fetcher registry, so these tests are
offline and deterministic.
"""

import jobbot.ingest as ingest
from jobbot import db
from jobbot.models import Job


def make_db():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return conn


def test_fetch_new_jobs_inserts_then_dedupes(monkeypatch):
    conn = make_db()

    jobs = [
        Job(source="greenhouse", external_id="1", company="Acme",
            title="Backend Engineer", url="https://x/1"),
        Job(source="greenhouse", external_id="2", company="Acme",
            title="Staff Engineer", url="https://x/2"),
    ]
    monkeypatch.setattr(ingest, "load_sources", lambda: [{"ats": "greenhouse", "token": "acme"}])
    monkeypatch.setattr(ingest, "fetch_source", lambda cfg: jobs)

    first = ingest.fetch_new_jobs(conn)
    assert (first.fetched, first.inserted) == (2, 0 + 2)
    assert first.errors == []

    # Second run: same postings -> fetched again, none newly inserted.
    second = ingest.fetch_new_jobs(conn)
    assert second.fetched == 2
    assert second.inserted == 0


def test_source_error_is_isolated(monkeypatch):
    conn = make_db()

    good = [Job(source="lever", external_id="9", company="Beta",
                title="SRE", url="https://x/9")]

    def fake_fetch(cfg):
        if cfg["ats"] == "greenhouse":
            raise RuntimeError("boom: bad token")
        return good

    monkeypatch.setattr(ingest, "load_sources", lambda: [
        {"ats": "greenhouse", "token": "broken"},
        {"ats": "lever", "company": "beta"},
    ])
    monkeypatch.setattr(ingest, "fetch_source", fake_fetch)

    result = ingest.fetch_new_jobs(conn)
    assert result.inserted == 1                 # the good source still ingested
    assert len(result.errors) == 1
    assert "greenhouse:broken" in result.errors[0]
