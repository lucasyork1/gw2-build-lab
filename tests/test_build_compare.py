import json
from copy import deepcopy

from gw2_wvw_data.analysis import compare_builds
from gw2_wvw_data.builds.model import BuildRecord


def _ref(identifier):
    return {
        "id": identifier,
        "name": f"component-{identifier}",
        "source": "fixture",
        "confidence": "exact",
    }


def _build_value():
    return {
        "schema_version": 1,
        "build_id": "left",
        "profession": "Thief",
        "mode": "wvw",
        "context": ["roaming"],
        "specializations": [_ref(7), _ref(28)],
        "traits": [_ref(701), _ref(2801)],
        "skills": {
            "heal": _ref(13027),
            "utilities": [_ref(13002), _ref(13062), _ref(13035)],
            "elite": _ref(13082),
        },
        "weapons": [
            {
                "slot": "w11",
                "type": _ref(1),
                "item": _ref(2201),
                "upgrades": [_ref(3003)],
                "infusions": [],
            }
        ],
        "armor": {"helm": _ref(2001)},
        "trinkets": {"amulet": _ref(2101)},
        "runes": [_ref(3001)],
        "relic": _ref(3002),
        "infusions": [],
        "consumables": {"food": _ref(4001), "utility": _ref(4002)},
        "assumptions": {},
        "provenance": {"sources": [], "fields": {}, "conflicts": []},
        "version_audit": {
            "status": "unverifiable",
            "game_build_id": None,
            "checked_at": None,
            "affected_components": [],
            "warnings": [],
        },
    }


def test_compare_builds_reports_ordered_structural_changes_without_claims():
    left_value = _build_value()
    right_value = deepcopy(left_value)
    right_value["build_id"] = "right"
    right_value["specializations"][1] = _ref(44)
    right_value["traits"].append(_ref(4401))
    right_value["skills"]["utilities"][0] = _ref(13106)
    right_value["weapons"][0]["item"] = _ref(2202)
    right_value["armor"]["gloves"] = _ref(2004)
    right_value["trinkets"].pop("amulet")
    right_value["runes"] = []
    right_value["relic"] = _ref(3005)
    right_value["infusions"] = [_ref(3004)]
    right_value["consumables"]["food"] = None

    comparison = compare_builds(
        BuildRecord.from_dict(left_value),
        BuildRecord.from_dict(right_value),
    )
    value = comparison.to_dict()

    assert comparison.left_build_id == "left"
    assert comparison.right_build_id == "right"
    assert [item.category for item in comparison.additions] == [
        "traits",
        "armor",
        "infusions",
    ]
    assert [item.category for item in comparison.removals] == [
        "trinkets",
        "runes",
        "consumables",
    ]
    assert [item.category for item in comparison.replacements] == [
        "specializations",
        "skills",
        "weapons",
        "relic",
    ]
    assert comparison.replacements[2].path == "weapons[0].item"
    assert "benefit" not in str(value).lower()
    assert "cost" not in str(value).lower()


def test_compare_builds_ignores_names_sources_and_confidence_when_ids_match():
    left_value = _build_value()
    right_value = deepcopy(left_value)
    right_value["build_id"] = "right"
    right_value["skills"]["heal"].update(
        name="renamed snapshot",
        source="other-source",
        confidence="publisher_claimed",
    )

    comparison = compare_builds(
        BuildRecord.from_dict(left_value),
        BuildRecord.from_dict(right_value),
    )

    assert comparison.additions == ()
    assert comparison.removals == ()
    assert comparison.replacements == ()


def test_compare_builds_treats_null_and_omitted_slots_as_the_same_absence():
    left_value = _build_value()
    right_value = deepcopy(left_value)
    right_value["build_id"] = "right"
    left_value["armor"]["gloves"] = None
    right_value["armor"].pop("gloves", None)

    comparison = compare_builds(
        BuildRecord.from_dict(left_value),
        BuildRecord.from_dict(right_value),
    )

    assert comparison.additions == ()
    assert comparison.removals == ()
    assert comparison.replacements == ()


def test_compare_builds_reports_weapon_quality_change():
    left_value = _build_value()
    right_value = deepcopy(left_value)
    right_value["build_id"] = "right"
    left_value["weapons"][0]["quality"] = "ascended"
    right_value["weapons"][0]["quality"] = "exotic"

    comparison = compare_builds(
        BuildRecord.from_dict(left_value),
        BuildRecord.from_dict(right_value),
    )

    assert [item.path for item in comparison.replacements] == [
        "weapons[0].quality"
    ]


def test_compare_builds_preserves_duplicate_weapon_slot_removal():
    left_value = _build_value()
    duplicate = deepcopy(left_value["weapons"][0])
    duplicate["item"] = _ref(2299)
    left_value["weapons"].append(duplicate)
    right_value = deepcopy(left_value)
    right_value["build_id"] = "right"
    right_value["weapons"].pop()

    comparison = compare_builds(
        BuildRecord.from_dict(left_value),
        BuildRecord.from_dict(right_value),
    )

    removal_paths = [item.path for item in comparison.removals]
    assert "weapons[1].slot" in removal_paths
    assert "weapons[1].item" in removal_paths


def test_compare_builds_preserves_unkeyed_weapon_entry_removal():
    left_value = _build_value()
    left_value["weapons"].append(
        {
            "type": _ref(2),
            "item": _ref(2298),
            "quality": "ascended",
            "upgrades": [],
            "infusions": [],
        }
    )
    right_value = deepcopy(left_value)
    right_value["build_id"] = "right"
    right_value["weapons"].pop()

    comparison = compare_builds(
        BuildRecord.from_dict(left_value),
        BuildRecord.from_dict(right_value),
    )

    removal_paths = [item.path for item in comparison.removals]
    assert "weapons[1].slot" in removal_paths
    assert "weapons[1].quality" in removal_paths
    assert "weapons[1].item" in removal_paths


def test_compare_builds_uses_indices_when_slot_text_collides_with_old_paths():
    left_value = _build_value()
    duplicate = deepcopy(left_value["weapons"][0])
    duplicate["item"] = _ref(2299)
    literal_collision = deepcopy(left_value["weapons"][0])
    literal_collision["slot"] = "w11[1]"
    literal_collision["item"] = _ref(2298)
    left_value["weapons"].extend([duplicate, literal_collision])
    right_value = deepcopy(left_value)
    right_value["build_id"] = "right"
    right_value["weapons"].pop()
    left = BuildRecord.from_dict(left_value)
    right = BuildRecord.from_dict(right_value)

    first = compare_builds(left, right)
    second = compare_builds(left, right)

    assert first.to_dict() == second.to_dict()
    assert first.removals
    assert "weapons[2].slot" in [
        item.path for item in first.removals
    ]


def test_compare_builds_distinguishes_absent_slot_from_literal_missing():
    missing_value = _build_value()
    missing_value["weapons"][0].pop("slot")
    literal_value = deepcopy(missing_value)
    literal_value["build_id"] = "literal"
    literal_value["weapons"][0]["slot"] = "<missing>"
    missing = BuildRecord.from_dict(missing_value)
    literal = BuildRecord.from_dict(literal_value)

    first = compare_builds(missing, literal)
    second = compare_builds(missing, literal)

    assert first.to_dict() == second.to_dict()
    assert first.additions == ()
    assert first.removals == ()
    assert first.to_dict()["replacements"] == [
        {
            "category": "weapons",
            "path": "weapons[0].slot",
            "before": {"missing": True},
            "after": "<missing>",
        }
    ]
    json.dumps(first.to_dict(), sort_keys=True)


def test_compare_builds_distinguishes_literal_missing_from_absent_slot():
    literal_value = _build_value()
    literal_value["weapons"][0]["slot"] = "<missing>"
    missing_value = deepcopy(literal_value)
    missing_value["build_id"] = "missing"
    missing_value["weapons"][0].pop("slot")
    literal = BuildRecord.from_dict(literal_value)
    missing = BuildRecord.from_dict(missing_value)

    first = compare_builds(literal, missing)
    second = compare_builds(literal, missing)

    assert first.to_dict() == second.to_dict()
    assert first.additions == ()
    assert first.removals == ()
    assert first.to_dict()["replacements"] == [
        {
            "category": "weapons",
            "path": "weapons[0].slot",
            "before": "<missing>",
            "after": {"missing": True},
        }
    ]
    json.dumps(first.to_dict(), sort_keys=True)
