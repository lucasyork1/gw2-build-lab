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
            "utilities": [_ref(13038), _ref(13062), _ref(13035)],
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
    assert comparison.replacements[2].path == "weapons.w11.item"
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
