"""jobbot command-line interface.

Phase 1 commands are deterministic (no LLM): fetch, matches, apply, stage,
interview, status. `run` (the agent scoring loop) is wired in Phase 2.
"""

from __future__ import annotations

import asyncio

import typer

from . import db
from .ingest import fetch_new_jobs
from .models import APPLICATION_STATUSES, Application, Interview

app = typer.Typer(add_completion=False, help="Agent-loop job finder & tracker.")
interview_app = typer.Typer(help="Log and view interviews.")
app.add_typer(interview_app, name="interview")


def _conn():
    conn = db.connect()
    db.init_db(conn)
    return conn


@app.command()
def fetch() -> None:
    """Poll configured ATS boards and store any new postings."""
    conn = _conn()
    result = fetch_new_jobs(conn)
    typer.echo(
        f"Fetched {result.fetched} postings, {result.inserted} new."
    )
    for err in result.errors:
        typer.secho(f"  ! {err}", fg=typer.colors.YELLOW)


@app.command()
def run(
    limit: int = typer.Option(15, help="Max pending jobs to score this run."),
    model: str = typer.Option(None, help="Model override (default env/JOBBOT_MODEL or 'sonnet')."),
    no_fetch: bool = typer.Option(False, "--no-fetch", help="Skip fetching new postings first."),
) -> None:
    """Run the agent scoring loop over pending jobs (fetches first by default)."""
    from .agent.loop import run_scoring_loop

    conn = _conn()
    if not no_fetch:
        result = fetch_new_jobs(conn)
        typer.echo(f"Fetched {result.fetched} postings, {result.inserted} new.")
        for err in result.errors:
            typer.secho(f"  ! {err}", fg=typer.colors.YELLOW)

    typer.secho("Running agent scoring loop...", fg=typer.colors.CYAN)
    summary = asyncio.run(
        run_scoring_loop(limit=limit, model=model, emit=typer.echo)
    )

    cost = f"${summary.cost_usd:.4f}" if summary.cost_usd is not None else "n/a"
    typer.secho(
        f"\nDone: {summary.recorded} evaluations recorded "
        f"({summary.tool_calls} tool calls, {summary.turns} turns, cost {cost}).",
        fg=typer.colors.GREEN if not summary.is_error else typer.colors.RED,
    )
    if summary.recorded:
        typer.echo("See top matches with: jobbot matches --min-score 60")


@app.command()
def matches(
    limit: int = typer.Option(20, help="Max rows to show."),
    min_score: int = typer.Option(0, help="Only show scores >= this."),
) -> None:
    """Show the best-scored jobs (requires the agent loop to have run)."""
    conn = _conn()
    rows = db.top_matches(conn, limit=limit, min_score=min_score)
    if not rows:
        typer.echo("No scored jobs yet. Run `jobbot run` (Phase 2) to score them.")
        raise typer.Exit()
    for r in rows:
        typer.secho(
            f"[{r['score']:>3}] {r['verdict']:<6} #{r['job_id']}  "
            f"{r['company']} — {r['title']}",
            fg=_score_color(r["score"]),
        )
        if r.get("location"):
            typer.echo(f"        {r['location']}  {r['url']}")


@app.command()
def apply(
    job_id: int = typer.Argument(..., help="Job id (see `jobbot matches`)."),
    notes: str = typer.Option("", help="Optional notes."),
) -> None:
    """Record that you applied to a job."""
    conn = _conn()
    job = db.get_job(conn, job_id)
    if job is None:
        typer.secho(f"No job with id {job_id}.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    app_id = db.add_application(conn, Application(job_id=job_id, notes=notes))
    typer.echo(f"Application #{app_id} created for {job.company} — {job.title}.")


@app.command()
def stage(
    app_id: int = typer.Argument(..., help="Application id (see `jobbot status`)."),
    status: str = typer.Argument(..., help=f"One of: {', '.join(APPLICATION_STATUSES)}"),
) -> None:
    """Move an application to a new pipeline stage."""
    if status not in APPLICATION_STATUSES:
        typer.secho(
            f"Invalid status '{status}'. Choose from: {', '.join(APPLICATION_STATUSES)}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)
    conn = _conn()
    if not db.set_application_status(conn, app_id, status):
        typer.secho(f"No application with id {app_id}.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    typer.echo(f"Application #{app_id} -> {status}.")


@app.command()
def status() -> None:
    """Show all applications and their current stage."""
    conn = _conn()
    rows = db.list_applications(conn)
    if not rows:
        typer.echo("No applications yet. Use `jobbot apply <job_id>`.")
        raise typer.Exit()
    for r in rows:
        typer.echo(
            f"#{r['app_id']:<3} {r['status']:<12} {r['company']} — {r['title']}"
        )
        if r.get("notes"):
            typer.echo(f"      note: {r['notes']}")


@interview_app.command("add")
def interview_add(
    app_id: int = typer.Argument(..., help="Application id."),
    round: str = typer.Option("", help="e.g. 'phone screen', 'system design'."),
    when: str = typer.Option("", "--when", help="Scheduled time, ISO-8601."),
    interviewer: str = typer.Option("", help="Interviewer name(s)."),
    notes: str = typer.Option("", help="Notes."),
) -> None:
    """Log an interview against an application."""
    conn = _conn()
    if db.get_application(conn, app_id) is None:
        typer.secho(f"No application with id {app_id}.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    intv_id = db.add_interview(
        conn,
        Interview(
            application_id=app_id,
            round=round,
            scheduled_at=when,
            interviewer=interviewer,
            notes=notes,
        ),
    )
    typer.echo(f"Interview #{intv_id} logged for application #{app_id}.")


@interview_app.command("list")
def interview_list(
    app_id: int = typer.Option(None, "--app", help="Filter by application id."),
) -> None:
    """List scheduled interviews."""
    conn = _conn()
    rows = db.list_interviews(conn, application_id=app_id)
    if not rows:
        typer.echo("No interviews logged.")
        raise typer.Exit()
    for r in rows:
        when = r["scheduled_at"] or "(unscheduled)"
        typer.echo(
            f"#{r['interview_id']:<3} app#{r['application_id']}  {when}  "
            f"{r['round'] or '?'}  {r['company']} — {r['title']}"
        )
        if r.get("interviewer"):
            typer.echo(f"      with: {r['interviewer']}")


def _score_color(score: int) -> str:
    if score >= 75:
        return typer.colors.GREEN
    if score >= 50:
        return typer.colors.YELLOW
    return typer.colors.WHITE


if __name__ == "__main__":
    app()
