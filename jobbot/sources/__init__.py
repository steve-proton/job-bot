"""Deterministic ATS fetchers.

Each fetcher takes its board config (from sources.yaml) and returns a list of
normalized :class:`jobbot.models.Job` objects. HTTP lives here; no LLM.
"""

from __future__ import annotations

from typing import Any, Callable

from ..models import Job
from . import ashby, greenhouse, lever
from ._http import get_client, looks_remote, strip_html  # re-exported for convenience

# Registry: ats name -> fetcher(config) -> list[Job]
FETCHERS: dict[str, Callable[[dict[str, Any]], list[Job]]] = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
}

__all__ = ["FETCHERS", "fetch_source", "get_client", "strip_html", "looks_remote"]


def fetch_source(config: dict[str, Any]) -> list[Job]:
    """Dispatch one sources.yaml entry to its fetcher."""
    ats = config.get("ats")
    fetcher = FETCHERS.get(ats)
    if fetcher is None:
        raise ValueError(f"Unknown ats '{ats}' (known: {', '.join(FETCHERS)})")
    return fetcher(config)
