"""Command-line interface for the data pipeline."""

from __future__ import annotations

import argparse
import importlib
from collections.abc import Sequence


COMMAND_MODULES = {
    "fetch": "fetch",
    "normalize": "normalize",
    "apply-overrides": "overrides",
    "validate": "validate",
    "diff": "diff",
    "release": "release",
}


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""

    parser = argparse.ArgumentParser(prog="gw2-wvw-data")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in COMMAND_MODULES:
        subparsers.add_parser(command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch a CLI command to its focused module."""

    arguments, remaining = build_parser().parse_known_args(argv)
    module_name = COMMAND_MODULES[arguments.command]
    module = importlib.import_module(f"gw2_wvw_data.{module_name}")
    return int(module.main(remaining))


if __name__ == "__main__":
    raise SystemExit(main())
