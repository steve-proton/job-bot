"""Drive the Claude Agent SDK scoring loop.

`run_scoring_loop` builds the agent options (custom tools only, no filesystem or
shell), runs `query()`, streams a compact perceive->decide->act trace, and
returns a summary. This is where the agent-loop experience lives.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    query,
)

from .. import db
from ..config import load_criteria
from .prompt import build_system_prompt
from .tools import build_server


@dataclass
class LoopSummary:
    recorded: int = 0                 # evaluations written during this run
    tool_calls: int = 0
    turns: int = 0
    cost_usd: float | None = None
    is_error: bool = False
    trace: list[str] = field(default_factory=list)


async def _prompt_stream(text: str):
    """Single-message streaming input.

    The `can_use_tool` permission gate requires streaming-input mode, so the
    kickoff prompt is delivered as an async iterable rather than a plain string.
    """
    yield {"type": "user", "message": {"role": "user", "content": text}}


async def _only_jobbot_tools(tool_name, input_data, context):
    """Permission gate: auto-allow the jobbot tools, deny everything else.

    Runs headless, so this is what keeps the agent from reaching for built-in
    Bash/Read/Write tools even though the model is aware of them.
    """
    if tool_name.startswith("mcp__jobbot__"):
        return PermissionResultAllow(updated_input=input_data)
    return PermissionResultDeny(message=f"{tool_name} is not permitted", interrupt=False)


def _count_evaluations(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]


async def run_scoring_loop(
    limit: int = 15,
    model: str | None = None,
    emit: Callable[[str], None] | None = None,
) -> LoopSummary:
    """Score up to `limit` pending jobs via the agent loop.

    `emit` is an optional line printer (the CLI passes typer.echo) so the loop's
    steps are visible as they happen.
    """
    emit = emit or (lambda _s: None)
    model = model or os.environ.get("JOBBOT_MODEL", "sonnet")
    max_budget = float(os.environ.get("JOBBOT_MAX_USD", "2.0"))

    criteria = load_criteria()
    server = build_server()

    options = ClaudeAgentOptions(
        system_prompt=build_system_prompt(criteria),
        mcp_servers={"jobbot": server},
        # No allowed_tools: an allowlisted tool is auto-approved *before*
        # can_use_tool runs, which would shadow the gate. Letting every call
        # fall through to can_use_tool makes it authoritative — jobbot tools
        # allowed, built-in Bash/Read/Write/etc. denied.
        can_use_tool=_only_jobbot_tools,
        model=model,
        max_turns=limit * 2 + 10,          # room for one record_evaluation per job
        max_budget_usd=max_budget,
        setting_sources=[],                # ignore any local .claude settings
    )

    prompt = (
        f"Score the current batch of pending jobs. Call get_pending_jobs with "
        f"limit={limit}, then record an evaluation for every job returned."
    )

    # Count evaluations before/after so the summary reflects what actually landed.
    conn = db.connect()
    db.init_db(conn)
    before = _count_evaluations(conn)
    conn.close()

    summary = LoopSummary()

    async for message in query(prompt=_prompt_stream(prompt), options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    line = f"  \N{SPEECH BALLOON} {block.text.strip()}"
                    emit(line)
                    summary.trace.append(line)
                elif isinstance(block, ToolUseBlock):
                    summary.tool_calls += 1
                    short = block.name.replace("mcp__jobbot__", "")
                    detail = _tool_call_detail(short, block.input)
                    line = f"  \N{HAMMER} {short}{detail}"
                    emit(line)
                    summary.trace.append(line)
        elif isinstance(message, ResultMessage):
            summary.turns = message.num_turns
            summary.cost_usd = message.total_cost_usd
            summary.is_error = message.is_error

    conn = db.connect()
    after = _count_evaluations(conn)
    conn.close()
    summary.recorded = after - before
    return summary


def _tool_call_detail(name: str, args: dict) -> str:
    if name == "record_evaluation":
        return (
            f"(job {args.get('job_id')}: {args.get('score')} "
            f"{args.get('verdict')})"
        )
    if name == "get_pending_jobs":
        return f"(limit={args.get('limit')})"
    return ""
