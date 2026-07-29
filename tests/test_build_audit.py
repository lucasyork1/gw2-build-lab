import json
from copy import deepcopy
from pathlib import Path

import pytest

from gw2_wvw_data.audit import DatasetIndex, PatchEvent, audit_build
from gw2_wvw_data.builds.model import BuildRecord
from gw2_wvw_data.contracts import schema_errors


FIXTURE = Path(__file__).parent / "fixtures" / "builds" / "patch-events.json"

ARMOR_SLOTS = ("helm", "shoulders", "coat", "gloves", "leggings", "boots")
TRINKET_SLOTS = ("back", "amulet", "earring1", "earring2", "ring1", "ring2")
ARMOR_TYPES = ("Helm", "Shoulders", "Coat", "Gloves", "Leggings", "Boots")


def _entity(identifier, kind, payload, *, build=101, removed=False):
    return {
        "id": identifier,
        "kind": kind,
        "names": {"en": f"{kind}-{identifier}", "zh": f"{kind}-{identifier}"},
        "mode": "wvw",
        "game_build_id": build,
        "effective_patch": "2026-07-01",
        "fetched_at": "2026-07-28T20:00:00Z",
        "source_refs": [f"fixture:{kind}:{identifier}"],
        "verification_status": "automated",
        "payload": {**payload, **({"removed": True} if removed else {})},
    }


@pytest.fixture
def dataset():
    specializations = [
        _entity(
            7,
            "specialization",
            {
                "profession": "Thief",
                "elite": True,
                "major_traits": list(range(701, 710)),
                "minor_traits": [],
            },
        ),
        _entity(
            28,
            "specialization",
            {
                "profession": "Thief",
                "elite": False,
                "major_traits": list(range(2801, 2810)),
                "minor_traits": [],
            },
        ),
        _entity(
            44,
            "specialization",
            {
                "profession": "Thief",
                "elite": False,
                "major_traits": list(range(4401, 4410)),
                "minor_traits": [],
            },
        ),
        _entity(
            58,
            "specialization",
            {
                "profession": "Thief",
                "elite": True,
                "major_traits": list(range(5801, 5810)),
                "minor_traits": [],
            },
        ),
    ]
    traits = []
    for specialization in specializations:
        for offset, trait_id in enumerate(
            specialization["payload"]["major_traits"]
        ):
            traits.append(
                _entity(
                    trait_id,
                    "trait",
                    {
                        "specialization": specialization["id"],
                        "tier": offset // 3 + 1,
                        "slot": "Major",
                    },
                )
            )
    skills = [
        _entity(13027, "skill", {"slot": "Heal", "type": "Heal"}),
        _entity(13002, "skill", {"slot": "Utility", "type": "Utility"}),
        _entity(13062, "skill", {"slot": "Utility", "type": "Utility"}),
        _entity(13035, "skill", {"slot": "Utility", "type": "Utility"}),
        _entity(13082, "skill", {"slot": "Elite", "type": "Elite"}),
        _entity(13106, "skill", {"slot": "Utility", "type": "Utility"}),
        _entity(
            13999,
            "skill",
            {"slot": "Utility", "type": "Utility"},
            removed=True,
        ),
    ]
    equipment = [
        *[
            _entity(
                identifier,
                "equipment",
                {
                    "type": "Armor",
                    "details": {
                        "type": armor_type,
                        "weight_class": "Medium",
                        "infusion_slots": [],
                    },
                },
            )
            for identifier, armor_type in zip(
                range(2001, 2007), ARMOR_TYPES, strict=True
            )
        ],
        *[
            _entity(
                identifier,
                "equipment",
                {
                    "type": "Back" if slot == "back" else "Trinket",
                    "details": {
                        "type": (
                            "Accessory"
                            if slot.startswith("earring")
                            else "Ring"
                            if slot.startswith("ring")
                            else "Amulet"
                            if slot == "amulet"
                            else None
                        ),
                        "infusion_slots": [],
                    },
                },
            )
            for identifier, slot in enumerate(TRINKET_SLOTS, 2101)
        ],
        *[
            _entity(
                identifier,
                "equipment",
                {
                    "type": "Weapon",
                    "details": {
                        "type": weapon_type,
                        "infusion_slots": [],
                    },
                },
            )
            for identifier, weapon_type in enumerate(
                (
                    "Dagger",
                    "Pistol",
                    "Sword",
                    "ShortBow",
                    "Rifle",
                    "Speargun",
                ),
                2201,
            )
        ],
    ]
    return {
        "manifest": {"game_build_id": 101, "fetched_at": "2026-07-28T20:00:00Z"},
        "profession": _entity(
            "Thief",
            "profession",
            {
                "weapons": {
                    "Dagger": {"flags": ["Mainhand", "Offhand"]},
                    "Pistol": {"flags": ["Mainhand", "Offhand"]},
                    "Sword": {"flags": ["Mainhand"]},
                    "Shortbow": {"flags": ["TwoHand"]},
                    "Rifle": {"flags": ["TwoHand"], "specialization": 7},
                    "Speargun": {"flags": ["TwoHand", "Aquatic"]},
                },
                "skills": [
                    {"id": 13027, "slot": "Heal"},
                    {"id": 13002, "slot": "Utility"},
                    {"id": 13062, "slot": "Utility"},
                    {"id": 13035, "slot": "Utility"},
                    {"id": 13082, "slot": "Elite"},
                    {"id": 13999, "slot": "Utility"},
                ],
                "skills_by_palette": [
                    [1, 13027],
                    [2, 13002],
                    [3, 13062],
                    [4, 13035],
                    [5, 13082],
                ],
            },
        ),
        "specializations": specializations,
        "traits": traits,
        "skills": skills,
        "equipment": equipment,
        "upgrades": [
            _entity(3001, "upgrade", {"type": "UpgradeComponent", "details": {"type": "Rune"}}),
            _entity(3002, "upgrade", {"type": "Relic", "details": {}}),
            _entity(3003, "upgrade", {"type": "UpgradeComponent", "details": {"type": "Sigil"}}),
            _entity(3004, "upgrade", {"type": "UpgradeComponent", "details": {"type": "Infusion"}}),
        ],
        "consumables": [
            _entity(4001, "consumable", {"type": "Consumable", "details": {"type": "Food"}}),
            _entity(4002, "consumable", {"type": "Consumable", "details": {"type": "Utility"}}),
        ],
        "itemstats": [],
    }


@pytest.fixture
def dataset_index(dataset):
    return DatasetIndex.from_dataset(dataset)


def _ref(identifier, name=None, *, source="fixture", confidence="exact"):
    return {
        "id": identifier,
        "name": name or f"component-{identifier}",
        "source": source,
        "confidence": confidence,
    }


def _complete_value():
    specialization_ids = (7, 28, 44)
    trait_ids = (701, 704, 707, 2801, 2804, 2807, 4401, 4404, 4407)
    weapon_types = ("Dagger", "Pistol", "Sword", "Dagger")
    weapon_item_ids = (2201, 2202, 2203, 2201)
    return {
        "schema_version": 1,
        "build_id": "complete",
        "profession": "Thief",
        "mode": "wvw",
        "context": ["roaming"],
        "specializations": [_ref(value) for value in specialization_ids],
        "traits": [_ref(value) for value in trait_ids],
        "skills": {
            "heal": _ref(13027),
            "utilities": [_ref(13002), _ref(13062), _ref(13035)],
            "elite": _ref(13082),
        },
        "weapons": [
            {
                "slot": slot,
                "type": _ref(index + 1, weapon_type),
                "item": _ref(weapon_item_ids[index]),
                "upgrades": [_ref(3003)],
                "infusions": [],
            }
            for index, (slot, weapon_type) in enumerate(
                zip(("w11", "w12", "w21", "w22"), weapon_types, strict=True)
            )
        ],
        "armor": {
            slot: _ref(identifier)
            for identifier, slot in enumerate(ARMOR_SLOTS, 2001)
        },
        "trinkets": {
            slot: _ref(identifier)
            for identifier, slot in enumerate(TRINKET_SLOTS, 2101)
        },
        "runes": [_ref(3001) for _ in range(6)],
        "relic": _ref(3002),
        "infusions": [],
        "consumables": {"food": _ref(4001), "utility": _ref(4002)},
        "assumptions": {},
        "provenance": {
            "sources": [{"source": "fixture", "updated_at": "2026-07-27"}],
            "fields": {},
            "conflicts": [],
        },
        "version_audit": {
            "status": "unverifiable",
            "game_build_id": 101,
            "checked_at": None,
            "affected_components": [],
            "warnings": [],
        },
    }


@pytest.fixture
def complete_build():
    return BuildRecord.from_dict(_complete_value())


@pytest.fixture
def build_code_only(complete_build):
    return complete_build.with_updates(
        build_id="build-code-only",
        weapons=(),
        armor={},
        trinkets={},
        runes=(),
        relic=None,
        consumables={"food": None, "utility": None},
    )


@pytest.fixture
def publisher_claimed_build(complete_build):
    value = complete_build.to_dict()
    value["version_audit"]["game_build_id"] = 100
    value["provenance"]["sources"][0]["publisher_status"] = (
        "publisher_claimed_current"
    )
    return BuildRecord.from_dict(value)


@pytest.fixture
def unknown_component_build(complete_build):
    value = complete_build.to_dict()
    value["skills"]["utilities"][0] = _ref(999999)
    return BuildRecord.from_dict(value)


@pytest.fixture
def removed_component_build(complete_build):
    value = complete_build.to_dict()
    value["skills"]["utilities"][0] = _ref(13999)
    return BuildRecord.from_dict(value)


@pytest.fixture
def patch_events():
    return [
        PatchEvent.from_dict(item)
        for item in json.loads(FIXTURE.read_text(encoding="utf-8"))
    ]


def _audit(build, dataset_index, patch_events=()):
    return audit_build(
        build,
        index=dataset_index,
        patch_events=patch_events,
        checked_at="2026-07-29T23:00:00Z",
    )


def test_dataset_index_indexes_legality_and_version_metadata_once(dataset_index):
    assert dataset_index.entity("skill", 13002)["names"]["en"] == "skill-13002"
    assert dataset_index.specialization_trait_tiers[7][1] == frozenset(
        {701, 702, 703}
    )
    assert dataset_index.profession_weapons["Dagger"]["flags"] == (
        "Mainhand",
        "Offhand",
    )
    assert dataset_index.skill_palette[2] == 13002
    assert dataset_index.entity_metadata[("skill", 13002)].effective_patch == (
        "2026-07-01"
    )


def test_build_code_only_is_legal_but_equipment_incomplete(
    build_code_only, dataset_index
):
    audit = _audit(build_code_only, dataset_index)
    assert audit.legality == "legal"
    assert "armor.helm" in audit.missing_fields
    assert audit.status == "unverifiable"


def test_publisher_current_never_becomes_verified_without_full_resolution(
    publisher_claimed_build, dataset_index
):
    audit = _audit(publisher_claimed_build, dataset_index)
    assert audit.status == "publisher_claimed_current"


def test_patch_after_source_marks_affected_components(
    complete_build, dataset_index, patch_events
):
    audit = _audit(complete_build, dataset_index, patch_events)
    assert audit.status == "possibly_affected"
    assert audit.affected_components[0].component_id == 13002


def test_unknown_component_is_unverifiable(unknown_component_build, dataset_index):
    audit = _audit(unknown_component_build, dataset_index)
    assert audit.status == "unverifiable"
    assert audit.unknown_components[0].component_id == 999999


def test_removed_component_is_invalid(removed_component_build, dataset_index):
    audit = _audit(removed_component_build, dataset_index)
    assert audit.status == "invalid"
    assert audit.legality == "illegal"


def test_illegal_specialization_trait_pairing_is_invalid(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["traits"][0] = _ref(2802)
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "invalid"
    assert audit.legality == "illegal"


def test_duplicate_trait_tier_is_invalid(complete_build, dataset_index):
    value = complete_build.to_dict()
    value["traits"][1] = _ref(702)
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "invalid"
    assert audit.legality == "illegal"


def test_duplicate_land_utilities_are_invalid(complete_build, dataset_index):
    value = complete_build.to_dict()
    value["skills"]["utilities"][1] = value["skills"]["utilities"][0]
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "invalid"
    assert audit.legality == "illegal"


def test_chain_skill_not_selectable_from_palette_is_invalid(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["skills"]["utilities"][0] = _ref(13106, "Shadow Return")
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "invalid"
    assert audit.legality == "illegal"


def test_four_specialization_lines_are_invalid(complete_build, dataset_index):
    value = complete_build.to_dict()
    value["specializations"].append(_ref(58))
    value["traits"].extend([_ref(5801), _ref(5804), _ref(5807)])
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "invalid"


def test_multiple_elite_specialization_lines_are_invalid(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["specializations"][1] = _ref(58)
    value["traits"][3:6] = [_ref(5801), _ref(5804), _ref(5807)]
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "invalid"


def test_missing_major_trait_tier_is_legal_but_unverifiable(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["traits"].pop()
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "unverifiable"
    assert audit.legality == "legal"
    assert "traits[8]" in audit.missing_fields


def test_unavailable_weapon_type_is_invalid(complete_build, dataset_index):
    value = complete_build.to_dict()
    value["weapons"][0]["type"] = _ref(999, "Greatsword")
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "invalid"
    assert audit.legality == "illegal"


def test_unresolved_site_local_weapon_type_is_unverifiable(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["weapons"][0]["type"] = _ref(
        "gw2skills:47",
        name=None,
        source="gw2skills",
        confidence="publisher_claimed",
    )
    value["weapons"][0]["type"]["name"] = None
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "unverifiable"
    assert audit.legality == "legal"
    assert audit.unknown_components[0].field == "weapons.w11.type"


def test_resolved_nonweapon_item_is_invalid_even_when_weapon_type_is_unresolved(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["weapons"][0]["type"] = {
        "id": "gw2skills:47",
        "name": None,
        "source": "gw2skills",
        "confidence": "publisher_claimed",
    }
    value["weapons"][0]["item"] = _ref(2001)
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "invalid"
    assert audit.legality == "illegal"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["armor"].__setitem__("helm", _ref(2006)),
        lambda value: value["armor"].__setitem__("helm", _ref(2102)),
        lambda value: value["trinkets"].__setitem__("earring1", _ref(2105)),
        lambda value: value["weapons"][0].__setitem__("item", _ref(2202)),
        lambda value: value["runes"].__setitem__(0, _ref(3003)),
        lambda value: value["weapons"][0]["upgrades"].__setitem__(0, _ref(3001)),
        lambda value: value.__setitem__("relic", _ref(3001)),
        lambda value: value["consumables"].__setitem__("food", _ref(4002)),
        lambda value: value["consumables"].__setitem__("utility", _ref(4001)),
    ],
)
def test_resolved_wrong_equipment_subtypes_are_invalid(
    complete_build, dataset_index, mutation
):
    value = complete_build.to_dict()
    mutation(value)
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "invalid"
    assert audit.legality == "illegal"


def test_medium_armor_weight_is_required(complete_build, dataset):
    changed = deepcopy(dataset)
    changed["equipment"][0]["payload"]["details"]["weight_class"] = "Heavy"
    audit = _audit(complete_build, DatasetIndex.from_dataset(changed))
    assert audit.status == "invalid"


def test_missing_required_sigil_is_unverifiable(complete_build, dataset_index):
    value = complete_build.to_dict()
    value["weapons"][0]["upgrades"] = []
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "unverifiable"
    assert "weapons.w11.upgrades[0]" in audit.missing_fields


@pytest.mark.parametrize(
    ("weapon_name", "item_id"),
    [("Shortbow", 2204), ("Rifle", 2205)],
)
def test_two_handed_main_weapon_uses_two_sigils_and_no_offhand(
    complete_build, dataset_index, weapon_name, item_id
):
    value = complete_build.to_dict()
    value["weapons"] = [
        value["weapons"][0],
        value["weapons"][1],
        {
            "slot": "w21",
            "type": _ref(107, weapon_name),
            "item": _ref(item_id),
            "upgrades": [_ref(3003), _ref(3003)],
            "infusions": [],
        },
    ]
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "current_verified"
    assert "weapons.w22" not in audit.missing_fields


def test_two_handed_weapon_with_only_one_sigil_is_unverifiable(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["weapons"] = [
        value["weapons"][0],
        value["weapons"][1],
        {
            "slot": "w21",
            "type": _ref(107, "Shortbow"),
            "item": _ref(2204),
            "upgrades": [_ref(3003)],
            "infusions": [],
        },
    ]
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "unverifiable"
    assert "weapons.w21.upgrades[1]" in audit.missing_fields


def test_weapon_without_explicit_slot_is_not_assigned_by_position(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    del value["weapons"][0]["slot"]
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "unverifiable"
    assert audit.legality == "legal"
    assert "weapons[0].slot" in audit.missing_fields
    assert "weapons.w11" in audit.missing_fields


def test_missing_weapon_type_is_unverifiable_not_invalid(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["weapons"][0]["type"] = None
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "unverifiable"
    assert audit.legality == "legal"
    assert "weapons.w11.type" in audit.missing_fields


def test_actual_equipment_infusion_slots_require_explicit_refs(
    complete_build, dataset
):
    changed = deepcopy(dataset)
    changed["equipment"][0]["payload"]["details"]["infusion_slots"] = [
        {"flags": ["Infusion"]}
    ]
    index = DatasetIndex.from_dataset(changed)
    missing = _audit(complete_build, index)
    assert missing.status == "unverifiable"
    assert "infusions[0]" in missing.missing_fields

    value = complete_build.to_dict()
    value["infusions"] = [_ref(3004)]
    assert _audit(BuildRecord.from_dict(value), index).status == "current_verified"


def test_wrong_infusion_subtype_is_invalid(complete_build, dataset):
    changed = deepcopy(dataset)
    changed["equipment"][0]["payload"]["details"]["infusion_slots"] = [
        {"flags": ["Infusion"]}
    ]
    value = complete_build.to_dict()
    value["infusions"] = [_ref(3001)]
    audit = _audit(
        BuildRecord.from_dict(value), DatasetIndex.from_dataset(changed)
    )
    assert audit.status == "invalid"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda value: value["runes"].pop(), "runes[5]"),
        (lambda value: value["armor"].pop("helm"), "armor.helm"),
        (lambda value: value["trinkets"].pop("ring2"), "trinkets.ring2"),
        (lambda value: value["weapons"].pop(), "weapons.w22"),
        (lambda value: value.__setitem__("relic", None), "relic"),
        (
            lambda value: value["consumables"].__setitem__("food", None),
            "consumables.food",
        ),
        (
            lambda value: value["consumables"].__setitem__("utility", None),
            "consumables.utility",
        ),
    ],
)
def test_exact_required_equipment_slots_are_reported(
    complete_build, dataset_index, mutation, expected
):
    value = complete_build.to_dict()
    mutation(value)
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert expected in audit.missing_fields
    assert audit.status == "unverifiable"


def test_complete_current_build_passes_all_current_verified_gates(
    complete_build, dataset_index
):
    audit = _audit(complete_build, dataset_index)
    assert audit.status == "current_verified"
    assert audit.missing_fields == ()
    assert audit.unknown_components == ()
    assert audit.removed_components == ()


def test_unresolved_provenance_conflict_blocks_current_verification(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["provenance"]["conflicts"] = [
        {
            "field": "context",
            "source": "metabattle",
            "values": ["roaming", "zerg"],
        }
    ]
    audit = _audit(BuildRecord.from_dict(value), dataset_index)

    assert audit.legality == "legal"
    assert audit.missing_fields == ()
    assert audit.unknown_components == ()
    assert audit.removed_components == ()
    assert audit.status == "unverifiable"
    assert "unresolved provenance conflicts require review" in audit.warnings
    assert schema_errors(audit.to_dict(), "build-audit.schema.json") == []


def test_breaking_post_source_patch_is_stale(complete_build, dataset_index):
    event = PatchEvent(
        component_kind="skill",
        component_id=13002,
        effective_at="2026-07-29",
        change="Skill was replaced.",
        impact="stale",
    )
    audit = _audit(complete_build, dataset_index, [event])
    assert audit.status == "stale"


def test_patch_after_checked_at_is_ignored(complete_build, dataset_index):
    event = PatchEvent(
        component_kind="skill",
        component_id=13002,
        effective_at="2026-07-30",
        change="Future change.",
    )
    audit = audit_build(
        complete_build,
        index=dataset_index,
        patch_events=[event],
        checked_at="2026-07-29T23:00:00Z",
    )
    assert audit.status == "current_verified"
    assert audit.affected_components == ()


def test_patch_uses_matching_component_source_not_unrelated_newer_source(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["skills"]["utilities"][0]["source"] = "older-source"
    value["provenance"]["sources"] = [
        {"source": "fixture", "updated_at": "2026-07-27"},
        {"source": "older-source", "published_at": "2026-07-20"},
        {"source": "unrelated", "updated_at": "2026-07-28"},
    ]
    event = PatchEvent(
        component_kind="skill",
        component_id=13002,
        effective_at="2026-07-25",
        change="Changed after the matching source.",
    )
    audit = _audit(BuildRecord.from_dict(value), dataset_index, [event])
    assert audit.status == "possibly_affected"
    assert audit.affected_components[0].component_id == 13002


def test_newer_fetched_at_cannot_hide_patch_after_old_published_content(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["provenance"]["sources"] = [
        {
            "source": "fixture",
            "published_at": "2026-07-20",
            "fetched_at": "2026-07-29T22:00:00Z",
        }
    ]
    event = PatchEvent(
        component_kind="skill",
        component_id=13002,
        effective_at="2026-07-25",
        change="Changed after the content was published.",
    )
    audit = _audit(BuildRecord.from_dict(value), dataset_index, [event])
    assert audit.status == "possibly_affected"
    assert audit.affected_components[0].component_id == 13002


def test_conflicting_duplicate_source_dates_are_unverifiable(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["provenance"]["sources"] = [
        {"source": "fixture", "published_at": "2026-07-20"},
        {"source": "fixture", "updated_at": "2026-07-27"},
    ]
    event = PatchEvent(
        component_kind="skill",
        component_id=13002,
        effective_at="2026-07-25",
        change="Falls between conflicting source dates.",
    )
    audit = _audit(BuildRecord.from_dict(value), dataset_index, [event])
    assert audit.status == "unverifiable"
    assert "component source date is ambiguous" in audit.warnings


def test_duplicate_source_records_with_same_content_date_resolve(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["provenance"]["sources"] = [
        {"source": "fixture", "published_at": "2026-07-27"},
        {"source": "fixture", "effective_patch": "2026-07-27"},
    ]
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "current_verified"


def test_dated_source_record_cannot_mask_matching_record_without_date(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["provenance"]["sources"] = [
        {"source": "fixture", "published_at": "2026-07-27"},
        {"source": "fixture"},
    ]
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "unverifiable"
    assert "component source date is ambiguous" in audit.warnings


def test_dated_source_record_cannot_mask_matching_malformed_record(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["provenance"]["sources"] = [
        {"source": "fixture", "published_at": "2026-07-27"},
        {"source": "fixture", "updated_at": "not-a-date"},
    ]
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "unverifiable"
    assert "component source date is ambiguous" in audit.warnings


def test_valid_field_cannot_mask_malformed_field_in_same_source_record(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["provenance"]["sources"] = [
        {
            "source": "fixture",
            "published_at": "2026-07-27",
            "updated_at": "not-a-date",
        }
    ]
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "unverifiable"
    assert "component source date is ambiguous" in audit.warnings


@pytest.mark.parametrize(
    "content_version",
    (
        "2026-07-27garbage",
        "2026-07-27Tnot-a-time",
        "2026-07-27T99:99:99Z",
        "2026-07-27T13:45:59",
        "2026-07-27T13:45:59+05:99",
        "2026-07-27T13:45:59+24:00",
        "2026-W30-1",
        "2026-W30-1T13:45:59Z",
    ),
)
def test_malformed_source_content_version_is_unverifiable(
    complete_build, dataset_index, content_version
):
    value = complete_build.to_dict()
    value["provenance"]["sources"] = [
        {"source": "fixture", "updated_at": content_version}
    ]
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "unverifiable"
    assert "component source date is ambiguous" in audit.warnings


@pytest.mark.parametrize(
    "content_version",
    (
        "2026-07-27",
        "2026-07-27T13:45:59Z",
        "2026-07-27T13:45:59-05:00",
        "2026-07-27T13:45:59+23:59",
    ),
)
def test_valid_complete_source_date_or_datetime_resolves(
    complete_build, dataset_index, content_version
):
    value = complete_build.to_dict()
    value["provenance"]["sources"] = [
        {"source": "fixture", "updated_at": content_version}
    ]
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "current_verified"


def test_effective_patch_only_source_date_detects_newer_patch(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["provenance"]["sources"] = [
        {"source": "fixture", "effective_patch": "2026-07-27"}
    ]
    event = PatchEvent(
        component_kind="skill",
        component_id=13002,
        effective_at="2026-07-29",
        change="Changed after the effective content patch.",
    )
    audit = _audit(BuildRecord.from_dict(value), dataset_index, [event])
    assert audit.status == "possibly_affected"
    assert audit.affected_components[0].component_id == 13002


def test_source_content_date_after_checked_at_is_unverifiable(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["provenance"]["sources"] = [
        {"source": "fixture", "updated_at": "2026-07-30"}
    ]
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "unverifiable"
    assert "component source date is after checked_at" in audit.warnings


def test_component_without_explicit_source_date_is_unverifiable(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["provenance"]["sources"] = [{"source": "fixture"}]
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "unverifiable"
    assert "component source date is missing" in audit.warnings


def test_aquatic_only_two_handed_weapon_is_invalid_on_land(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["weapons"] = [
        weapon for weapon in value["weapons"] if weapon["slot"] in {"w11", "w12"}
    ]
    value["weapons"].append(
        {
            "slot": "w21",
            "type": _ref(6, "Speargun"),
            "item": _ref(2206),
            "upgrades": [_ref(3003), _ref(3003)],
            "infusions": [],
        }
    )
    audit = _audit(BuildRecord.from_dict(value), dataset_index)
    assert audit.status == "invalid"
    assert "weapon type Speargun is aquatic-only at w21" in audit.warnings


def test_status_precedence_keeps_invalid_above_patch_and_unknown(
    removed_component_build, dataset_index, patch_events
):
    value = removed_component_build.to_dict()
    value["skills"]["utilities"][1] = _ref(999999)
    audit = _audit(BuildRecord.from_dict(value), dataset_index, patch_events)
    assert audit.status == "invalid"


def test_warnings_and_component_findings_have_deterministic_order(
    complete_build, dataset_index
):
    value = complete_build.to_dict()
    value["armor"].pop("helm")
    value["trinkets"].pop("amulet")
    value["skills"]["utilities"][0] = _ref(999999)
    value["skills"]["utilities"][2] = _ref(999998)
    build = BuildRecord.from_dict(value)

    first = _audit(build, dataset_index)
    second = _audit(build, dataset_index)

    assert first.to_dict() == second.to_dict()
    assert first.missing_fields == tuple(sorted(first.missing_fields))
    assert first.warnings == tuple(sorted(first.warnings))
    assert [item.field for item in first.unknown_components] == sorted(
        item.field for item in first.unknown_components
    )


def test_audit_dict_matches_public_schema(complete_build, dataset_index):
    assert schema_errors(
        _audit(complete_build, dataset_index).to_dict(),
        "build-audit.schema.json",
    ) == []


def test_inconsistent_dataset_build_ids_block_project_verification(dataset):
    value = deepcopy(dataset)
    value["skills"][0]["game_build_id"] = 999
    index = DatasetIndex.from_dataset(value)
    audit = _audit(BuildRecord.from_dict(_complete_value()), index)
    assert audit.status == "unverifiable"
    assert "dataset game build is inconsistent" in audit.warnings
