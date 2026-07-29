"""Deterministic persistence for canonical build records."""

from __future__ import annotations

import json
from pathlib import Path

from gw2_wvw_data.builds.model import BuildRecord
from gw2_wvw_data.io import write_json


def load_build(path: str | Path) -> BuildRecord:
    """Load one schema-validated canonical build record."""

    return BuildRecord.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def write_build(path: str | Path, build: BuildRecord) -> None:
    """Write one canonical build record with stable JSON formatting."""

    write_json(path, build.to_dict())
