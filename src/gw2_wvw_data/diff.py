"""Semantic, field-level comparison of two GW2 datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from gw2_wvw_data.io import write_json
from gw2_wvw_data.overrides import load_dataset


IGNORED_KEYS = frozenset({"fetched_at", "sha256"})


def _iter_entities(dataset: dict[str, Any]) -> Iterable[dict[str, Any]]:
    profession = dataset.get("profession")
    if isinstance(profession, dict) and "kind" in profession:
        yield profession
    for value in dataset.values():
        if isinstance(value, list):
            for record in value:
                if isinstance(record, dict) and "kind" in record:
                    yield record


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _field_changes(old: Any, new: Any, path: str = "") -> list[tuple[str, Any, Any]]:
    if isinstance(old, dict) and isinstance(new, dict):
        changes: list[tuple[str, Any, Any]] = []
        for key in sorted((old.keys() | new.keys()) - IGNORED_KEYS):
            child_path = f"{path}/{_pointer_token(str(key))}"
            if key not in old:
                changes.append((child_path, None, new[key]))
            elif key not in new:
                changes.append((child_path, old[key], None))
            else:
                changes.extend(_field_changes(old[key], new[key], child_path))
        return changes
    if isinstance(old, list) and isinstance(new, list):
        changes = []
        for index in range(max(len(old), len(new))):
            child_path = f"{path}/{index}"
            if index >= len(old):
                changes.append((child_path, None, new[index]))
            elif index >= len(new):
                changes.append((child_path, old[index], None))
            else:
                changes.extend(_field_changes(old[index], new[index], child_path))
        return changes
    return [] if old == new else [(path or "/", old, new)]


def diff_datasets(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Return added, removed, and changed entity facts."""

    old_entities = {
        (record["kind"], record["id"]): record for record in _iter_entities(old)
    }
    new_entities = {
        (record["kind"], record["id"]): record for record in _iter_entities(new)
    }
    old_keys = set(old_entities)
    new_keys = set(new_entities)
    added = [
        {"entity_kind": kind, "entity_id": entity_id}
        for kind, entity_id in sorted(new_keys - old_keys, key=lambda key: (key[0], str(key[1])))
    ]
    removed = [
        {"entity_kind": kind, "entity_id": entity_id}
        for kind, entity_id in sorted(old_keys - new_keys, key=lambda key: (key[0], str(key[1])))
    ]
    changed = []
    for kind, entity_id in sorted(old_keys & new_keys, key=lambda key: (key[0], str(key[1]))):
        changes = _field_changes(old_entities[(kind, entity_id)], new_entities[(kind, entity_id)])
        if not changes:
            continue
        paths = [change[0] for change in changes]
        old_value: Any
        new_value: Any
        if len(changes) == 1:
            old_value, new_value = changes[0][1], changes[0][2]
        else:
            old_value = {path: value for path, value, _ in changes}
            new_value = {path: value for path, _, value in changes}
        changed.append(
            {
                "entity_kind": kind,
                "entity_id": entity_id,
                "paths": paths,
                "old": old_value,
                "new": new_value,
            }
        )
    return {
        "old_game_build_id": old.get("manifest", {}).get("game_build_id"),
        "new_game_build_id": new.get("manifest", {}).get("game_build_id"),
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for semantic dataset comparison."""

    parser = argparse.ArgumentParser(prog="gw2-wvw-data diff")
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    report = diff_datasets(load_dataset(arguments.old), load_dataset(arguments.new))
    if arguments.output:
        write_json(arguments.output, report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0
