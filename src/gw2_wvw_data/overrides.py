"""Apply reviewed WvW-only corrections without changing raw facts."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from gw2_wvw_data.contracts import schema_errors
from gw2_wvw_data.io import write_json
from gw2_wvw_data.normalize import ENTITY_FILES


class OverrideConflictError(RuntimeError):
    """Raised when an override cannot safely apply to its declared base."""


REQUIRED_FIELDS = {
    "entity_kind",
    "entity_id",
    "json_pointer",
    "mode",
    "value",
    "previous_value",
    "effective_patch",
    "source_url",
    "verification_status",
    "notes",
}


def _validate_override(override: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_FIELDS - override.keys())
    if missing:
        raise ValueError(f"override is missing required field: {missing[0]}")
    if override["mode"] != "wvw":
        raise ValueError("override mode must be wvw")
    if override["verification_status"] != "human_verified":
        raise ValueError("override verification_status must be human_verified")
    parsed = urlparse(str(override["source_url"]))
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("override source_url must use HTTPS")
    try:
        date.fromisoformat(str(override["effective_patch"]))
    except ValueError as error:
        raise ValueError("override effective_patch must be YYYY-MM-DD") from error
    if not str(override["json_pointer"]).startswith("/"):
        raise ValueError("override json_pointer must start with /")
    errors = schema_errors(override, "override.schema.json")
    if errors:
        raise ValueError(f"override schema invalid: {errors[0]}")


def _iter_entities(dataset: dict[str, Any]):
    profession = dataset.get("profession")
    if isinstance(profession, dict) and "kind" in profession:
        yield profession
    for value in dataset.values():
        if isinstance(value, list):
            for record in value:
                if isinstance(record, dict) and "kind" in record:
                    yield record


def _decode_pointer_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _resolve_pointer(entity: dict[str, Any], pointer: str) -> tuple[Any, str | int]:
    tokens = [_decode_pointer_token(token) for token in pointer.lstrip("/").split("/")]
    parent: Any = entity
    for token in tokens[:-1]:
        if isinstance(parent, list):
            parent = parent[int(token)]
        elif isinstance(parent, dict) and token in parent:
            parent = parent[token]
        else:
            raise OverrideConflictError(f"json pointer does not exist: {pointer}")
    final: str | int = int(tokens[-1]) if isinstance(parent, list) else tokens[-1]
    if isinstance(parent, list):
        if not 0 <= final < len(parent):
            raise OverrideConflictError(f"json pointer does not exist: {pointer}")
    elif not isinstance(parent, dict) or final not in parent:
        raise OverrideConflictError(f"json pointer does not exist: {pointer}")
    return parent, final


def apply_overrides(
    dataset: dict[str, Any],
    overrides: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a copy of *dataset* with reviewed WvW field corrections applied."""

    result = deepcopy(dataset)
    entities = {
        (entity["kind"], entity["id"]): entity
        for entity in _iter_entities(result)
    }
    seen_targets: dict[tuple[Any, ...], Any] = {}
    for override in overrides:
        _validate_override(override)
        target_key = (
            override["entity_kind"],
            override["entity_id"],
            override["json_pointer"],
            override["effective_patch"],
        )
        if target_key in seen_targets:
            raise OverrideConflictError(
                "conflicting overrides for "
                f"entity_id={override['entity_id']} pointer={override['json_pointer']}"
            )
        seen_targets[target_key] = override["value"]
        entity_key = (override["entity_kind"], override["entity_id"])
        if entity_key not in entities:
            raise OverrideConflictError(
                "override target does not exist: "
                f"entity_kind={override['entity_kind']} "
                f"entity_id={override['entity_id']}"
            )
        entity = entities[entity_key]
        parent, final = _resolve_pointer(entity, override["json_pointer"])
        actual = parent[final]
        expected = override["previous_value"]
        if actual != expected:
            raise OverrideConflictError(
                f"entity_id={override['entity_id']} expected {expected!r} "
                f"at {override['json_pointer']}, found {actual!r}"
            )
        parent[final] = deepcopy(override["value"])
        entity["effective_patch"] = override["effective_patch"]
        entity["verification_status"] = "human_verified"
        source_ref = f"wvw-override:{override['source_url']}"
        if source_ref not in entity["source_refs"]:
            entity["source_refs"].append(source_ref)
            entity["source_refs"].sort()
    result["applied_overrides"] = deepcopy(overrides)
    return result


def load_dataset(path: str | Path) -> dict[str, Any]:
    """Load a normalized dataset directory into the in-memory contract."""

    root = Path(path)
    dataset = {
        "profession": json.loads((root / "profession.json").read_text("utf-8")),
        "manifest": json.loads((root / "dataset-manifest.json").read_text("utf-8")),
    }
    for filename in ENTITY_FILES:
        dataset[filename] = json.loads((root / f"{filename}.json").read_text("utf-8"))
    return dataset


def write_dataset(path: str | Path, dataset: dict[str, Any]) -> None:
    """Write an applied dataset directory in canonical form."""

    root = Path(path)
    write_json(root / "profession.json", dataset["profession"])
    for filename in ENTITY_FILES:
        write_json(root / f"{filename}.json", dataset[filename])
    write_json(root / "dataset-manifest.json", dataset["manifest"])
    write_json(root / "applied-overrides.json", dataset.get("applied_overrides", []))


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for applying reviewed corrections."""

    parser = argparse.ArgumentParser(prog="gw2-wvw-data apply-overrides")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    dataset = load_dataset(arguments.dataset)
    overrides = json.loads(arguments.overrides.read_text("utf-8"))
    write_dataset(arguments.output, apply_overrides(dataset, overrides))
    return 0
