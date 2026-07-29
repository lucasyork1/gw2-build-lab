"""Runtime enforcement for public JSON contracts and snapshot integrity."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from gw2_wvw_data.io import sha256_file


def schema_errors(instance: Any, schema_name: str) -> list[str]:
    """Return stable human-readable errors for one public schema."""

    schema_root = files("gw2_wvw_data").joinpath("schemas")
    schema_text = schema_root.joinpath(schema_name).read_text(encoding="utf-8")
    schema = json.loads(schema_text)
    registry = Registry()
    for schema_path in schema_root.iterdir():
        if schema_path.name.endswith(".schema.json"):
            resource = Resource.from_contents(
                json.loads(schema_path.read_text(encoding="utf-8"))
            )
            registry = registry.with_resource(
                f"urn:gw2-wvw-data:schema:{schema_path.name}",
                resource,
            )
    validator = Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
        registry=registry,
    )
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '/'}: {error.message}"
        for error in sorted(
            validator.iter_errors(instance),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
    ]


def verify_raw_snapshot(snapshot_dir: str | Path) -> dict[str, Any]:
    """Validate the raw manifest and every declared file hash."""

    root = Path(snapshot_dir)
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"raw manifest is unreadable: {error}") from error
    errors = schema_errors(manifest, "manifest.schema.json")
    if errors:
        raise ValueError(f"raw manifest schema invalid: {errors[0]}")

    declared: set[str] = set()
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        if relative.name != entry["path"] or relative.suffix != ".json":
            raise ValueError(f"unsafe raw manifest path: {entry['path']}")
        if entry["path"] in declared:
            raise ValueError(f"duplicate raw manifest path: {entry['path']}")
        declared.add(entry["path"])
        path = root / entry["path"]
        if not path.is_file():
            raise ValueError(f"raw manifest file is missing: {entry['path']}")
        if sha256_file(path) != entry["sha256"]:
            raise ValueError(f"raw file hash mismatch: {entry['path']}")

    actual = {
        path.name
        for path in root.glob("*.json")
        if path.name != "manifest.json"
    }
    if actual != declared:
        raise ValueError("raw manifest file list does not match snapshot files")
    return manifest
