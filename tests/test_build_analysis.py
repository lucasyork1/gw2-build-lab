import json
from copy import deepcopy

import pytest

from gw2_wvw_data.analysis import analyze_build, load_rules
from gw2_wvw_data.audit import BuildAudit, DatasetIndex
from gw2_wvw_data.builds.model import BuildRecord
from gw2_wvw_data.contracts import schema_errors


DIMENSIONS = [
    "burst_damage",
    "sustained_damage",
    "survival_recovery",
    "condition_cleanse",
    "control_interrupt",
    "mobility_disengage",
    "stealth_reset",
    "operation_difficulty",
]


def _ref(identifier):
    return {
        "id": identifier,
        "name": f"component-{identifier}",
        "source": "fixture",
        "confidence": "exact",
    }


def _build(*, utility_ids=(13038, 13062, 13035)):
    return BuildRecord.from_dict(
        {
            "schema_version": 1,
            "build_id": "analysis-fixture",
            "profession": "Thief",
            "mode": "wvw",
            "context": ["roaming"],
            "specializations": [],
            "traits": [],
            "skills": {
                "heal": None,
                "utilities": [_ref(value) for value in utility_ids],
                "elite": None,
            },
            "weapons": [],
            "armor": {},
            "trinkets": {},
            "runes": [],
            "relic": None,
            "infusions": [],
            "consumables": {"food": None, "utility": None},
            "assumptions": {},
            "provenance": {
                "sources": [
                    {
                        "source": "fixture",
                        "title": "Shadowstep mobility prose is not input evidence",
                    }
                ],
                "fields": {},
                "conflicts": [],
            },
            "version_audit": {
                "status": "unverifiable",
                "game_build_id": None,
                "checked_at": None,
                "affected_components": [],
                "warnings": [],
            },
        }
    )


def _entity(identifier, *, payload=True):
    value = {
        "id": identifier,
        "kind": "skill",
        "names": {"en": f"skill-{identifier}", "zh": f"skill-{identifier}"},
        "mode": "wvw",
        "game_build_id": 101,
        "effective_patch": "2026-07-01",
        "fetched_at": "2026-07-28T20:00:00Z",
        "source_refs": [f"fixture:skill:{identifier}"],
        "verification_status": "automated",
    }
    if payload:
        value["payload"] = {"description": f"facts for {identifier}"}
    return value


@pytest.fixture
def index():
    profession = {
        **_entity("Thief"),
        "kind": "profession",
        "payload": {"weapons": {}, "skills_by_palette": []},
    }
    return DatasetIndex.from_dataset(
        {
            "manifest": {
                "game_build_id": 101,
                "fetched_at": "2026-07-28T20:00:00Z",
            },
            "profession": profession,
            "specializations": [],
            "traits": [],
            "skills": [_entity(value) for value in (13035, 13038, 13062)],
            "equipment": [],
            "upgrades": [],
            "consumables": [],
            "itemstats": [],
        }
    )


def _rules_value():
    return {
        "schema_version": 1,
        "ruleset_id": "test-thief-wvw-v1",
        "dimensions": DIMENSIONS,
        "rules": [
            {
                "rule_id": "z-shadowstep-reset",
                "when": {"component_kind": "skill", "component_id": 13038},
                "effects": [{"dimension": "stealth_reset", "delta": 1}],
                "evidence": [
                    {
                        "component_kind": "skill",
                        "component_id": 13038,
                        "field": "payload",
                    }
                ],
                "claim": "The selected skill contributes a reset option.",
            },
            {
                "rule_id": "a-shadowstep-mobility",
                "when": {"component_kind": "skill", "component_id": 13038},
                "effects": [
                    {"dimension": "mobility_disengage", "delta": 2}
                ],
                "evidence": [
                    {
                        "component_kind": "skill",
                        "component_id": 13038,
                        "field": "payload",
                    }
                ],
                "claim": "The selected skill contributes mobility.",
            },
        ],
        "improvements": [
            {
                "improvement_id": "swap-signet-for-roll",
                "replace": {
                    "component_kind": "skill",
                    "component_id": 13062,
                },
                "with": {
                    "component_kind": "skill",
                    "component_id": 13035,
                },
                "benefit": "Adds the project-authored alternative utility.",
                "cost": "Removes the selected signet utility.",
                "applies_when": {
                    "component_kind": "skill",
                    "component_id": 13062,
                },
                "evidence": [
                    {
                        "component_kind": "skill",
                        "component_id": 13035,
                        "field": "payload",
                    },
                    {
                        "component_kind": "skill",
                        "component_id": 13062,
                        "field": "payload",
                    },
                ],
            }
        ],
    }


def _write_rules(tmp_path, value):
    path = tmp_path / "rules.json"
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def test_load_rules_accepts_the_brief_rule_shape_without_improvements(
    tmp_path,
):
    value = _rules_value()
    value.pop("improvements")

    rules = load_rules(_write_rules(tmp_path, value))

    assert rules.ruleset_id == "test-thief-wvw-v1"
    assert rules.improvements == ()


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda value: value["rules"][0]["effects"][0].update(
                dimension="invented_score"
            ),
            "analysis rules schema invalid",
        ),
        (
            lambda value: value["rules"][0].pop("evidence"),
            "analysis rules schema invalid",
        ),
        (
            lambda value: value["rules"][0]["effects"][0].update(delta=3),
            "analysis rules schema invalid",
        ),
        (
            lambda value: value["rules"][1].update(
                rule_id=value["rules"][0]["rule_id"]
            ),
            "duplicate rule_id",
        ),
    ],
)
def test_load_rules_rejects_invalid_or_ambiguous_rules(
    tmp_path, mutation, expected
):
    value = _rules_value()
    mutation(value)

    with pytest.raises(ValueError, match=expected):
        load_rules(_write_rules(tmp_path, value))


def test_analysis_is_deterministic_evidence_backed_and_has_no_overall_score(
    tmp_path, index
):
    build = _build()
    audit = BuildAudit(
        schema_version=1,
        build_id=build.build_id,
        status="current_verified",
        legality="legal",
        game_build_id=101,
        checked_at="2026-07-29T00:00:00Z",
        missing_fields=(),
        unknown_components=(),
        removed_components=(),
        affected_components=(),
        warnings=(),
    )
    rules = load_rules(_write_rules(tmp_path, _rules_value()))

    first = analyze_build(build, audit, index=index, rules=rules)
    second = analyze_build(build, audit, index=index, rules=rules)
    value = first.to_dict()

    assert value == second.to_dict()
    assert first.dimensions["mobility_disengage"].band == 5
    assert first.dimensions["mobility_disengage"].label == "very_high"
    assert [item.rule_id for item in first.strengths] == [
        "a-shadowstep-mobility",
        "z-shadowstep-reset",
    ]
    assert all(item.evidence for item in first.strengths)
    assert all(item.evidence for item in first.weaknesses)
    assert all(item.evidence for item in first.improvements)
    assert "overall_score" not in value
    assert schema_errors(value, "build-analysis.schema.json") == []


def test_missing_equipment_only_lowers_affected_dimension_confidence(
    tmp_path, index
):
    build = _build()
    audit = BuildAudit(
        schema_version=1,
        build_id=build.build_id,
        status="unverifiable",
        legality="legal",
        game_build_id=101,
        checked_at="2026-07-29T00:00:00Z",
        missing_fields=("armor.helm",),
        unknown_components=(),
        removed_components=(),
        affected_components=(),
        warnings=(),
    )

    analysis = analyze_build(
        build,
        audit,
        index=index,
        rules=load_rules(_write_rules(tmp_path, _rules_value())),
    )

    assert analysis.dimensions["survival_recovery"].confidence == "low"
    assert analysis.dimensions["burst_damage"].confidence == "low"
    assert analysis.dimensions["mobility_disengage"].confidence == "high"
    assert any(
        "armor.helm" in reason
        for reason in analysis.dimensions[
            "survival_recovery"
        ].confidence_reasons
    )


def test_missing_rule_evidence_skips_delta_and_records_confidence_reason(
    tmp_path, index
):
    value = _rules_value()
    value["rules"] = [value["rules"][0]]
    value["rules"][0]["evidence"][0]["field"] = "payload.missing_fact"
    build = _build()
    audit = BuildAudit(
        schema_version=1,
        build_id=build.build_id,
        status="current_verified",
        legality="legal",
        game_build_id=101,
        checked_at="2026-07-29T00:00:00Z",
        missing_fields=(),
        unknown_components=(),
        removed_components=(),
        affected_components=(),
        warnings=(),
    )

    analysis = analyze_build(
        build,
        audit,
        index=index,
        rules=load_rules(_write_rules(tmp_path, value)),
    )

    dimension = analysis.dimensions["stealth_reset"]
    assert dimension.band == 3
    assert dimension.label == "medium"
    assert dimension.confidence == "low"
    assert "z-shadowstep-reset" in dimension.confidence_reasons[0]
    assert analysis.strengths == ()


def test_improvement_creates_derived_build_without_mutating_original(
    tmp_path, index
):
    build = _build()
    original = deepcopy(build.to_dict())
    audit = BuildAudit(
        schema_version=1,
        build_id=build.build_id,
        status="current_verified",
        legality="legal",
        game_build_id=101,
        checked_at="2026-07-29T00:00:00Z",
        missing_fields=(),
        unknown_components=(),
        removed_components=(),
        affected_components=(),
        warnings=(),
    )

    analysis = analyze_build(
        build,
        audit,
        index=index,
        rules=load_rules(_write_rules(tmp_path, _rules_value())),
    )
    improvement = analysis.improvements[0]

    assert build.to_dict() == original
    assert (
        improvement.derived_build.build_id
        == "analysis-fixture--swap-signet-for-roll"
    )
    assert [
        item.id
        for item in improvement.derived_build.skills["utilities"]
    ] == [13038, 13035, 13035]
    assert improvement.benefit == (
        "Adds the project-authored alternative utility."
    )
    assert improvement.cost == "Removes the selected signet utility."


def test_source_prose_never_matches_a_component_rule(tmp_path, index):
    value = _rules_value()
    value["improvements"] = []
    build = _build(utility_ids=(13062, 13035, 13062))
    audit = BuildAudit(
        schema_version=1,
        build_id=build.build_id,
        status="unverifiable",
        legality="legal",
        game_build_id=101,
        checked_at="2026-07-29T00:00:00Z",
        missing_fields=(),
        unknown_components=(),
        removed_components=(),
        affected_components=(),
        warnings=(),
    )

    analysis = analyze_build(
        build,
        audit,
        index=index,
        rules=load_rules(_write_rules(tmp_path, value)),
    )

    assert analysis.dimensions["mobility_disengage"].band == 3
    assert analysis.strengths == ()


def test_rule_evidence_must_identify_a_component_selected_in_the_build(
    tmp_path, index
):
    value = _rules_value()
    value["improvements"] = []
    value["rules"] = [value["rules"][0]]
    value["rules"][0]["evidence"] = [
        {
            "component_kind": "skill",
            "component_id": 13035,
            "field": "payload",
        }
    ]
    build = _build(utility_ids=(13038, 13062, 13062))
    audit = BuildAudit(
        schema_version=1,
        build_id=build.build_id,
        status="current_verified",
        legality="legal",
        game_build_id=101,
        checked_at="2026-07-29T00:00:00Z",
        missing_fields=(),
        unknown_components=(),
        removed_components=(),
        affected_components=(),
        warnings=(),
    )

    analysis = analyze_build(
        build,
        audit,
        index=index,
        rules=load_rules(_write_rules(tmp_path, value)),
    )

    assert analysis.dimensions["stealth_reset"].band == 3
    assert analysis.strengths == ()
    assert "not selected" in analysis.dimensions[
        "stealth_reset"
    ].confidence_reasons[0]


def test_higher_operation_difficulty_is_a_weakness_not_a_strength(
    tmp_path, index
):
    value = _rules_value()
    value["improvements"] = []
    value["rules"] = [value["rules"][0]]
    value["rules"][0]["effects"] = [
        {"dimension": "operation_difficulty", "delta": 1}
    ]
    build = _build()
    audit = BuildAudit(
        schema_version=1,
        build_id=build.build_id,
        status="current_verified",
        legality="legal",
        game_build_id=101,
        checked_at="2026-07-29T00:00:00Z",
        missing_fields=(),
        unknown_components=(),
        removed_components=(),
        affected_components=(),
        warnings=(),
    )

    analysis = analyze_build(
        build,
        audit,
        index=index,
        rules=load_rules(_write_rules(tmp_path, value)),
    )

    assert analysis.strengths == ()
    assert [item.rule_id for item in analysis.weaknesses] == [
        "z-shadowstep-reset"
    ]


def test_dimension_deltas_are_summed_before_the_final_band_clamp(
    tmp_path, index
):
    value = _rules_value()
    value["improvements"] = []
    template = value["rules"][0]
    value["rules"] = []
    for rule_id, delta in (("a-plus", 2), ("b-plus", 2), ("z-minus", -2)):
        rule = deepcopy(template)
        rule["rule_id"] = rule_id
        rule["effects"] = [
            {"dimension": "mobility_disengage", "delta": delta}
        ]
        value["rules"].append(rule)
    build = _build()
    audit = BuildAudit(
        schema_version=1,
        build_id=build.build_id,
        status="current_verified",
        legality="legal",
        game_build_id=101,
        checked_at="2026-07-29T00:00:00Z",
        missing_fields=(),
        unknown_components=(),
        removed_components=(),
        affected_components=(),
        warnings=(),
    )

    analysis = analyze_build(
        build,
        audit,
        index=index,
        rules=load_rules(_write_rules(tmp_path, value)),
    )

    assert analysis.dimensions["mobility_disengage"].band == 5
