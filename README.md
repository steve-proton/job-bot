# job-bot

An **agent-loop** job finder and application tracker. It pulls postings from
public ATS APIs (Greenhouse / Lever / Ashby), uses a Claude agent loop to score
each job against your criteria, and tracks your applications through to
interviews — all in a local SQLite database.

The point of the project is to gain hands-on experience with agent loops: the
deterministic plumbing (fetching, storage, CLI) is plain Python, and the
**scoring is a real perceive → decide → act loop** built on the
[Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk).

## Status

- **Phase 1 — done:** ATS ingestion, SQLite store, and the CLI tracker
  (`fetch`, `matches`, `apply`, `stage`, `interview`, `status`).
- **Phase 2 — next:** the agent scoring loop (`jobbot run`).
- **Phase 3:** daily cron scheduling.
- **Phase 4 (stretch):** Google Calendar events for interviews.

## Setup

Requires Python 3.11+. Using [uv](https://docs.astral.sh/uv/):

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
```

(or a plain `python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"`.)

Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY` (needed for Phase 2;
the Agent SDK also accepts an existing `claude` login).

## Configure

- `config/criteria.yaml` — your role criteria; drives the agent's fit scoring.
- `config/sources.yaml` — the ATS boards to poll. Replace the examples with
  companies you actually want to watch:
  - **greenhouse** `token` = the slug in `boards.greenhouse.io/<token>`
  - **lever** `company` = the slug in `jobs.lever.co/<company>`
  - **ashby** `board` = the slug in `jobs.ashbyhq.com/<board>`

## Use

```bash
jobbot fetch                     # pull new postings into the DB
jobbot run                       # (Phase 2) score pending jobs with the agent
jobbot matches --min-score 60    # show best-scored jobs
jobbot apply <job_id>            # log an application
jobbot stage <app_id> onsite     # move it through the pipeline
jobbot interview add <app_id> --round "system design" --when 2026-08-01T15:00
jobbot status                    # pipeline overview
jobbot interview list            # scheduled interviews
```

The database path defaults to `./jobbot.db` (override with `JOBBOT_DB`).

## Development

```bash
.venv/bin/python -m pytest
```

## Layout

```
jobbot/
  db.py          SQLite schema + queries
  models.py      dataclasses mirroring the schema
  config.py      loads criteria.yaml / sources.yaml
  sources/       deterministic ATS fetchers (greenhouse, lever, ashby)
  ingest.py      fetch + dedupe into SQLite
  agent/         (Phase 2) custom tools + the scoring loop
  cli.py         Typer CLI
```
