"""Canonical project paths. Everything derives from the repository root."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
EXTERNAL = DATA / "external"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
MAPS = REPORTS / "maps"
TABLES = REPORTS / "tables"
DOCS = ROOT / "docs"


def ensure_dirs() -> None:
    for p in (RAW, INTERIM, PROCESSED, EXTERNAL, FIGURES, MAPS, TABLES):
        p.mkdir(parents=True, exist_ok=True)
