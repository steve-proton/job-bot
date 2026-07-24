"""Load the YAML config files (criteria + sources)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    with path.open() as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a top-level mapping")
    return data


def load_criteria() -> dict[str, Any]:
    """Return the raw criteria mapping from config/criteria.yaml."""
    return _load("criteria.yaml")


def load_sources() -> list[dict[str, Any]]:
    """Return the list of ATS board configs from config/sources.yaml."""
    data = _load("sources.yaml")
    sources = data.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError("sources.yaml: 'sources' must be a list")
    return sources
