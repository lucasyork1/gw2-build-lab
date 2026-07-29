"""Cross-file validation for normalized and applied datasets."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from gw2_wvw_data.overrides import load_dataset


@dataclass(frozen=True)
class ValidationIssue:
    """One stable, machine-readable dataset problem."""

    code: str
    entity_kind: str
    entity_id: str
    message: str


def _iter_entities(dataset: dict[str, Any]) -> Iterable[dict[str, Any]]:
    profession = dataset.get("profession")
    if isinstance(profession, dict) and "kind" in profession:
        yield profession
    for value in dataset.values():
        if isinstance(value, list):
            for record in value:
                if isinstance(record, dict) and "kind" in record:
                    yield record


def _source_id(source_ref: str) -> str:
    return source_ref.split(":", 1)[0]


def validate_dataset(
    dataset: dict[str, Any],
    *,
    source_ids: set[str] | None = None,
) -> list[ValidationIssue]:
    """Return every cross-file invariant violation in stable order."""

    sources = source_ids or {"arenanet-api", "wvw-override"}
    issues: list[ValidationIssue] = []
    manifest = dataset.get("manifest", {})
    build_id = manifest.get("game_build_id")
    if manifest.get("mode") != "wvw":
        issues.append(
            ValidationIssue("invalid_mode", "manifest", "", "manifest mode must be wvw")
        )

    seen: set[tuple[Any, Any]] = set()
    entities = list(_iter_entities(dataset))
    for entity in entities:
        kind = str(entity.get("kind", "unknown"))
        entity_id = entity.get("id", "")
        key = (kind, entity_id)
        if key in seen:
            issues.append(
                ValidationIssue(
                    "duplicate_entity",
                    kind,
                    str(entity_id),
                    f"duplicate entity key {kind}:{entity_id}",
                )
            )
        seen.add(key)
        if entity.get("mode") != "wvw":
            issues.append(
                ValidationIssue(
                    "invalid_mode",
                    kind,
                    str(entity_id),
                    "entity mode must be wvw",
                )
            )
        if entity.get("game_build_id") != build_id:
            issues.append(
                ValidationIssue(
                    "build_mismatch",
                    kind,
                    str(entity_id),
                    f"entity build {entity.get('game_build_id')} != manifest build {build_id}",
                )
            )
        for source_ref in entity.get("source_refs", []):
            if _source_id(str(source_ref)) not in sources:
                issues.append(
                    ValidationIssue(
                        "missing_source",
                        kind,
                        str(entity_id),
                        f"unknown source reference {source_ref}",
                    )
                )

    itemstat_ids = {
        entity.get("id")
        for entity in entities
        if entity.get("kind") == "itemstat"
    }
    for entity in entities:
        if entity.get("kind") != "equipment":
            continue
        itemstat_id = (
            entity.get("payload", {})
            .get("details", {})
            .get("infix_upgrade", {})
            .get("id")
        )
        if itemstat_id is not None and itemstat_id not in itemstat_ids:
            issues.append(
                ValidationIssue(
                    "missing_itemstat",
                    "equipment",
                    str(entity.get("id", "")),
                    f"equipment references missing itemstat {itemstat_id}",
                )
            )

    for reference in manifest.get("unresolved_references", []):
        issues.append(
            ValidationIssue(
                "unresolved_reference",
                str(reference.get("kind", "unknown")),
                str(reference.get("id", "")),
                f"unresolved reference from {reference.get('referenced_by', 'unknown')}",
            )
        )

    for override in dataset.get("applied_overrides", []):
        if override.get("verification_status") != "human_verified":
            issues.append(
                ValidationIssue(
                    "unreviewed_override",
                    str(override.get("entity_kind", "unknown")),
                    str(override.get("entity_id", "")),
                    "applied override is not human_verified",
                )
            )

    issues.sort(
        key=lambda issue: (
            issue.code,
            issue.entity_kind,
            issue.entity_id,
            issue.message,
        )
    )
    return issues


def _load_source_ids(path: Path) -> set[str]:
    payload = json.loads(path.read_text("utf-8"))
    return {source["source_id"] for source in payload["sources"]}


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for dataset validation."""

    parser = argparse.ArgumentParser(prog="gw2-wvw-data validate")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--sources",
        type=Path,
        default=Path("data/provenance/sources.json"),
    )
    arguments = parser.parse_args(argv)
    dataset = load_dataset(arguments.dataset)
    applied_path = arguments.dataset / "applied-overrides.json"
    if applied_path.exists():
        dataset["applied_overrides"] = json.loads(applied_path.read_text("utf-8"))
    issues = validate_dataset(dataset, source_ids=_load_source_ids(arguments.sources))
    print(json.dumps([asdict(issue) for issue in issues], ensure_ascii=False, indent=2))
    return 1 if issues else 0
