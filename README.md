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
- **Phase 2 — done:** the agent scoring loop (`jobbot run`) — a Claude Agent SDK
  perceive → decide → act loop that scores pending jobs against your criteria.
- **Phase 3 — done:** daily scheduling via `scripts/run_daily.sh` + cron.
- **Phase 4 (stretch):** Google Calendar events for interviews.

### How the agent loop works

`jobbot run` fetches new postings (deterministic), then starts an agent session
with three custom tools (`get_pending_jobs`, `record_evaluation`,
`fetch_new_jobs`) and your criteria in the system prompt. The agent pulls the
work queue, scores each job (0–100 + verdict + reasons), and records the
results — you watch the loop stream as it goes. A permission gate allows only
the `jobbot` tools, so the agent never touches the shell or filesystem.

Env knobs: `JOBBOT_MODEL` (default `sonnet`), `JOBBOT_MAX_USD` (per-run budget
cap, default `2.0`), `JOBBOT_DB` (default `./jobbot.db`).

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

## Run it daily (cron)

`scripts/run_daily.sh` is a cron-safe entrypoint: it cd's to the repo, loads
`.env`, sources nvm so the Agent SDK can find the `claude` CLI, pins the DB, and
logs each run to `logs/`.

Test it by hand first (tiny batch, temp DB):

```bash
JOBBOT_DB=/tmp/jobbot_test.db JOBBOT_LIMIT=2 ./scripts/run_daily.sh
```

Then schedule it. Edit your crontab with `crontab -e` and add (daily at 08:00):

```cron
0 8 * * * /Users/stevedooley/dev/job-bot/scripts/run_daily.sh
```

Tune cadence/volume with the cron time and `JOBBOT_LIMIT`. On macOS, if cron
can't run the job, grant **Full Disk Access** to `/usr/sbin/cron` in System
Settings → Privacy & Security. Logs older than 30 days are pruned automatically.

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
