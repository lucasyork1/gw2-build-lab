"""Normalize raw ArenaNet responses into the Thief WvW data contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from gw2_wvw_data.io import write_json


ENTITY_FILES = (
    "specializations",
    "traits",
    "skills",
    "itemstats",
    "equipment",
    "upgrades",
    "consumables",
)


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _localized_by_id(records: Iterable[dict[str, Any]]) -> dict[Any, dict[str, Any]]:
    return {record["id"]: record for record in records}


def _entity(
    record: dict[str, Any],
    localized: dict[Any, dict[str, Any]],
    *,
    kind: str,
    game_build_id: int,
    fetched_at: str,
    source_name: str,
) -> dict[str, Any]:
    entity_id = record["id"]
    translated = localized.get(entity_id, {})
    payload = {
        key: value
        for key, value in record.items()
        if key not in {"id", "name"}
    }
    return {
        "id": entity_id,
        "kind": kind,
        "names": {
            "en": str(record.get("name", "")),
            "zh": str(translated.get("name", record.get("name", ""))),
        },
        "mode": "wvw",
        "game_build_id": game_build_id,
        "effective_patch": None,
        "fetched_at": fetched_at,
        "source_refs": [f"arenanet-api:{source_name}:{entity_id}"],
        "verification_status": "automated",
        "payload": payload,
    }


def _profession_skill_ids(profession: dict[str, Any]) -> set[int]:
    identifiers: set[int] = set()
    for skill in profession.get("skills", []):
        if isinstance(skill, int):
            identifiers.add(skill)
        elif isinstance(skill, dict) and isinstance(skill.get("id"), int):
            identifiers.add(skill["id"])
    return identifiers


def _normalize_items(
    english: list[dict[str, Any]],
    chinese: list[dict[str, Any]],
    *,
    game_build_id: int,
    fetched_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    localized = _localized_by_id(chinese)
    categories: dict[str, list[dict[str, Any]]] = {
        "equipment": [],
        "upgrades": [],
        "consumables": [],
    }
    kind_by_type = {
        "Armor": "equipment",
        "Weapon": "equipment",
        "UpgradeComponent": "upgrades",
        "Consumable": "consumables",
    }
    for record in english:
        category = kind_by_type.get(record.get("type"))
        if category is None or int(record.get("level", 0)) < 60:
            continue
        categories[category].append(
            _entity(
                record,
                localized,
                kind=category[:-1] if category.endswith("s") else category,
                game_build_id=game_build_id,
                fetched_at=fetched_at,
                source_name="items",
            )
        )
    for records in categories.values():
        records.sort(key=lambda value: value["id"])
    return (
        categories["equipment"],
        categories["upgrades"],
        categories["consumables"],
    )


def normalize_snapshot(
    snapshot_dir: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Create deterministic, linked Thief records from a complete snapshot."""

    snapshot = Path(snapshot_dir)
    output = Path(output_dir)
    raw_manifest = _read_json(snapshot / "manifest.json")
    game_build_id = int(raw_manifest["game_build_id"])
    fetched_at = str(raw_manifest["fetched_at"])

    profession_en = _read_json(snapshot / "profession.en.json")
    profession_zh = _read_json(snapshot / "profession.zh.json")
    specialization_en = _read_json(snapshot / "specializations.en.json")
    specialization_zh = _read_json(snapshot / "specializations.zh.json")
    trait_en = _read_json(snapshot / "traits.en.json")
    trait_zh = _read_json(snapshot / "traits.zh.json")
    skill_en = _read_json(snapshot / "skills.en.json")
    skill_zh = _read_json(snapshot / "skills.zh.json")
    itemstat_en = _read_json(snapshot / "itemstats.en.json")
    itemstat_zh = _read_json(snapshot / "itemstats.zh.json")
    item_en = _read_json(snapshot / "items.en.json")
    item_zh = _read_json(snapshot / "items.zh.json")

    thief_specializations = sorted(
        (record for record in specialization_en if record.get("profession") == "Thief"),
        key=lambda value: value["id"],
    )
    specialization_ids = {record["id"] for record in thief_specializations}
    trait_ids = {
        trait_id
        for record in thief_specializations
        for trait_id in record.get("major_traits", []) + record.get("minor_traits", [])
    }
    thief_traits = sorted(
        (
            record
            for record in trait_en
            if record.get("specialization") in specialization_ids
            or record.get("id") in trait_ids
        ),
        key=lambda value: value["id"],
    )
    available_trait_ids = {record["id"] for record in thief_traits}

    referenced_skill_ids = _profession_skill_ids(profession_en)
    thief_skills = sorted(
        (
            record
            for record in skill_en
            if "Thief" in record.get("professions", [])
            or record.get("id") in referenced_skill_ids
        ),
        key=lambda value: value["id"],
    )
    available_skill_ids = {record["id"] for record in thief_skills}

    unresolved_references = [
        {
            "kind": "trait",
            "id": trait_id,
            "referenced_by": f"specialization:{record['id']}",
        }
        for record in thief_specializations
        for trait_id in record.get("major_traits", []) + record.get("minor_traits", [])
        if trait_id not in available_trait_ids
    ]
    unresolved_references.extend(
        {
            "kind": "skill",
            "id": skill_id,
            "referenced_by": "profession:Thief",
        }
        for skill_id in sorted(referenced_skill_ids - available_skill_ids)
    )
    unresolved_references.sort(
        key=lambda value: (value["kind"], str(value["id"]), value["referenced_by"])
    )

    specialization_zh_by_id = _localized_by_id(specialization_zh)
    trait_zh_by_id = _localized_by_id(trait_zh)
    skill_zh_by_id = _localized_by_id(skill_zh)
    itemstat_zh_by_id = _localized_by_id(itemstat_zh)

    result: dict[str, Any] = {
        "profession": _entity(
            profession_en,
            {profession_zh["id"]: profession_zh},
            kind="profession",
            game_build_id=game_build_id,
            fetched_at=fetched_at,
            source_name="professions",
        ),
        "specializations": [
            _entity(
                record,
                specialization_zh_by_id,
                kind="specialization",
                game_build_id=game_build_id,
                fetched_at=fetched_at,
                source_name="specializations",
            )
            for record in thief_specializations
        ],
        "traits": [
            _entity(
                record,
                trait_zh_by_id,
                kind="trait",
                game_build_id=game_build_id,
                fetched_at=fetched_at,
                source_name="traits",
            )
            for record in thief_traits
        ],
        "skills": [
            _entity(
                record,
                skill_zh_by_id,
                kind="skill",
                game_build_id=game_build_id,
                fetched_at=fetched_at,
                source_name="skills",
            )
            for record in thief_skills
        ],
        "itemstats": [
            _entity(
                record,
                itemstat_zh_by_id,
                kind="itemstat",
                game_build_id=game_build_id,
                fetched_at=fetched_at,
                source_name="itemstats",
            )
            for record in sorted(itemstat_en, key=lambda value: value["id"])
        ],
    }
    equipment, upgrades, consumables = _normalize_items(
        item_en,
        item_zh,
        game_build_id=game_build_id,
        fetched_at=fetched_at,
    )
    result["equipment"] = equipment
    result["upgrades"] = upgrades
    result["consumables"] = consumables

    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "profession.json", result["profession"])
    for filename in ENTITY_FILES:
        write_json(output / f"{filename}.json", result[filename])
    result["manifest"] = {
        "schema_version": 1,
        "game_build_id": game_build_id,
        "fetched_at": fetched_at,
        "mode": "wvw",
        "files": [
            "profession.json",
            *(f"{filename}.json" for filename in ENTITY_FILES),
        ],
        "unresolved_references": unresolved_references,
    }
    write_json(output / "dataset-manifest.json", result["manifest"])
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for normalization."""

    parser = argparse.ArgumentParser(prog="gw2-wvw-data normalize")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    normalize_snapshot(arguments.snapshot, arguments.output)
    return 0
