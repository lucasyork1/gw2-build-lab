"""Strict, offline decoding for Guild Wars 2 Thief Build Template Codes."""

from __future__ import annotations

import base64
import binascii
import hashlib
from collections.abc import Mapping
from typing import Any

from gw2_wvw_data.builds.model import BuildRecord, ComponentRef


WEAPON_TYPE_IDS = {
    5: "Axe",
    47: "Dagger",
    54: "Pistol",
    85: "Rifle",
    86: "Scepter",
    89: "Staff",
    90: "Sword",
    107: "Shortbow",
    265: "Spear",
}

_SOURCE = "build-code"
_MINIMUM_BYTES = 44


class BuildCodeError(ValueError):
    """The supplied Build Template Code is malformed or unsupported."""


def _component(
    identifier: int,
    names: Mapping[int, str],
    *,
    confidence: str,
) -> ComponentRef:
    if identifier == 0:
        return ComponentRef(None, None, _SOURCE, "unknown")
    name = names.get(identifier)
    return ComponentRef(
        identifier,
        name,
        _SOURCE,
        confidence if name is not None else "unknown",
    )


def _normalize_and_decode(code: str) -> tuple[str, bytes]:
    if not isinstance(code, str) or not code.strip():
        raise BuildCodeError("build template code is empty")
    if len(code) > 512:
        raise BuildCodeError("build template code exceeds 512 characters")
    value = code.strip()
    if value.startswith("[") or value.endswith("]"):
        if not (value.startswith("[") and value.endswith("]")):
            raise BuildCodeError("build template brackets are malformed")
        value = value[1:-1]
    if not value.startswith("&"):
        raise BuildCodeError("build template code must use the & prefix")
    try:
        raw = base64.b64decode(value[1:], validate=True)
    except (binascii.Error, ValueError) as error:
        raise BuildCodeError("build template payload is not valid base64") from error
    canonical = "[&" + base64.b64encode(raw).decode("ascii") + "]"
    return canonical, raw


def _parse_dynamic_arrays(raw: bytes) -> tuple[list[int], list[int]]:
    if len(raw) == _MINIMUM_BYTES:
        return [], []
    cursor = _MINIMUM_BYTES
    weapon_count = raw[cursor]
    cursor += 1
    weapon_end = cursor + weapon_count * 2
    if weapon_end > len(raw):
        raise BuildCodeError("terrestrial weapon array is truncated")
    weapon_ids = [
        int.from_bytes(raw[offset : offset + 2], "little")
        for offset in range(cursor, weapon_end, 2)
    ]
    cursor = weapon_end
    if cursor >= len(raw):
        raise BuildCodeError("skill override count is truncated")
    override_count = raw[cursor]
    cursor += 1
    override_end = cursor + override_count * 4
    if override_end > len(raw):
        raise BuildCodeError("skill override array is truncated")
    override_ids = [
        int.from_bytes(raw[offset : offset + 4], "little")
        for offset in range(cursor, override_end, 4)
    ]
    if any(raw[override_end:]):
        raise BuildCodeError("build template has non-zero trailing bytes")
    return weapon_ids, override_ids


def _entity_names(records: Any) -> dict[int, str]:
    if not isinstance(records, list):
        return {}
    return {
        record["id"]: record["names"]["en"]
        for record in records
        if (
            isinstance(record, Mapping)
            and isinstance(record.get("id"), int)
            and isinstance(record.get("names"), Mapping)
            and isinstance(record["names"].get("en"), str)
        )
    }


def decode_build_code(
    code: str,
    *,
    dataset: Mapping[str, Any],
) -> BuildRecord:
    """Decode one Thief Build Template Code against a local normalized dataset."""

    canonical, raw = _normalize_and_decode(code)
    if not raw or raw[0] != 0x0D:
        raise BuildCodeError("invalid build template header")
    if len(raw) > 1 and raw[1] != 5:
        raise BuildCodeError("only Thief build templates are supported")
    if len(raw) < _MINIMUM_BYTES:
        raise BuildCodeError("build template header is shorter than 44 bytes")

    weapon_ids, override_ids = _parse_dynamic_arrays(raw)
    specialization_records = dataset.get("specializations", [])
    specialization_names = _entity_names(specialization_records)
    specialization_by_id = {
        record["id"]: record
        for record in specialization_records
        if isinstance(record, Mapping) and isinstance(record.get("id"), int)
    }
    trait_names = _entity_names(dataset.get("traits", []))
    skill_names = _entity_names(dataset.get("skills", []))

    specializations: list[ComponentRef] = []
    traits: list[ComponentRef] = []
    for offset in range(2, 8, 2):
        specialization_id = raw[offset]
        packed_choices = raw[offset + 1]
        specializations.append(
            _component(specialization_id, specialization_names, confidence="exact")
        )
        record = specialization_by_id.get(specialization_id)
        major_traits = (
            record.get("payload", {}).get("major_traits", [])
            if isinstance(record, Mapping)
            else []
        )
        for tier, shift in enumerate((0, 2, 4)):
            choice = (packed_choices >> shift) & 0b11
            trait_id = (
                major_traits[tier * 3 + choice - 1]
                if (
                    choice
                    and isinstance(major_traits, list)
                    and len(major_traits) >= (tier + 1) * 3
                )
                else 0
            )
            traits.append(_component(trait_id, trait_names, confidence="mapped"))

    palette_pairs = (
        dataset.get("profession", {})
        .get("payload", {})
        .get("skills_by_palette", [])
    )
    skills_by_palette = {
        pair[0]: pair[1]
        for pair in palette_pairs
        if (
            isinstance(pair, list)
            and len(pair) == 2
            and isinstance(pair[0], int)
            and isinstance(pair[1], int)
        )
    }
    palette_ids = [
        int.from_bytes(raw[offset : offset + 2], "little")
        for offset in range(8, 28, 2)
    ]

    def skill_from_palette(palette_id: int) -> ComponentRef | None:
        if palette_id == 0:
            return None
        skill_id = skills_by_palette.get(palette_id)
        if skill_id is None:
            return ComponentRef(palette_id, None, _SOURCE, "unknown")
        return _component(skill_id, skill_names, confidence="mapped")

    land_skills = [
        skill_from_palette(identifier) for identifier in palette_ids[::2]
    ]
    aquatic_skills = tuple(
        skill_from_palette(identifier) for identifier in palette_ids[1::2]
    )
    weapons = [
        {
            "type": ComponentRef(
                identifier or None,
                WEAPON_TYPE_IDS.get(identifier),
                _SOURCE,
                "mapped" if identifier in WEAPON_TYPE_IDS else "unknown",
            ).to_dict()
        }
        for identifier in weapon_ids
    ]
    skill_overrides = [
        _component(identifier, skill_names, confidence="exact").to_dict()
        for identifier in override_ids
    ]
    fields = {
        path: {"source": _SOURCE}
        for path in (
            "profession",
            "specializations",
            "traits",
            "skills",
            "weapons",
            "assumptions.aquatic_skills",
            "assumptions.profession_specific",
            "assumptions.skill_overrides",
        )
    }
    return BuildRecord.from_dict(
        {
            "schema_version": 1,
            "build_id": "build-code-" + hashlib.sha256(raw).hexdigest(),
            "profession": "Thief",
            "mode": "wvw",
            "context": [],
            "specializations": [item.to_dict() for item in specializations],
            "traits": [item.to_dict() for item in traits],
            "skills": {
                "heal": land_skills[0].to_dict() if land_skills[0] else None,
                "utilities": [
                    item.to_dict() if item else None for item in land_skills[1:4]
                ],
                "elite": land_skills[4].to_dict() if land_skills[4] else None,
            },
            "weapons": weapons,
            "armor": {},
            "trinkets": {},
            "runes": [],
            "relic": None,
            "infusions": [],
            "consumables": {"food": None, "utility": None},
            "assumptions": {
                "aquatic_skills": [
                    item.to_dict() if item else None for item in aquatic_skills
                ],
                "profession_specific": list(raw[28:44]),
                "skill_overrides": skill_overrides,
            },
            "provenance": {
                "sources": [{"source": _SOURCE, "value": canonical}],
                "fields": fields,
                "conflicts": [],
            },
            "version_audit": {
                "status": "unverifiable",
                "game_build_id": None,
                "checked_at": None,
                "affected_components": [],
                "warnings": [
                    "Build Template Codes do not include complete equipment."
                ],
            },
        }
    )
