import json
from pathlib import Path

from gw2_wvw_data.analysis import (
    AnalysisConclusion,
    BuildAnalysis,
    DimensionAnalysis,
    EvidenceReference,
)
from gw2_wvw_data.audit import BuildAudit
from gw2_wvw_data.builds import BuildRecord
from gw2_wvw_data.builds.report import render_markdown


FIXTURE = Path(__file__).parent / "fixtures" / "builds" / "minimal-thief.json"
DIMENSIONS = (
    "burst_damage",
    "sustained_damage",
    "survival_recovery",
    "condition_cleanse",
    "control_interrupt",
    "mobility_disengage",
    "stealth_reset",
    "operation_difficulty",
)


def _report_inputs():
    build = BuildRecord.from_dict(json.loads(FIXTURE.read_text("utf-8")))
    audit = BuildAudit(
        schema_version=1,
        build_id=build.build_id,
        status="unverifiable",
        legality="legal",
        game_build_id=204489,
        checked_at="2026-07-29T02:05:07Z",
        missing_fields=(
            "armor.helm",
            "relic",
            "weapons.w11",
        ),
        unknown_components=(),
        removed_components=(),
        affected_components=(),
        warnings=("missing required field: armor.helm",),
    )
    evidence = (EvidenceReference("skill", 13002, "payload"),)
    dimensions = {
        name: DimensionAnalysis(
            band=4 if name == "mobility_disengage" else 3,
            label="high" if name == "mobility_disengage" else "medium",
            confidence="low",
            confidence_reasons=("missing equipment limits confidence",),
            evidence=evidence if name == "mobility_disengage" else (),
        )
        for name in DIMENSIONS
    }
    conclusion = AnalysisConclusion(
        rule_id="shadowstep-mobility",
        claim="Shadowstep contributes mobility.",
        evidence=evidence,
    )
    analysis = BuildAnalysis(
        schema_version=1,
        build_id=build.build_id,
        ruleset_id="fixture-rules",
        dimensions=dimensions,
        strengths=(conclusion,),
        weaknesses=(),
        improvements=(),
        improvement_reasons=(),
    )
    return build, audit, analysis


def test_markdown_contains_every_required_report_section_and_dimension():
    markdown = render_markdown(*_report_inputs())

    for heading in (
        "## Identity",
        "## Completeness",
        "## Version Status",
        "## Legality",
        "## Equipment",
        "## Capability Dimensions",
        "## Strengths",
        "## Weaknesses",
        "## Risks",
        "## Improvements",
        "## Evidence",
        "## Sources",
    ):
        assert heading in markdown
    for dimension in DIMENSIONS:
        assert dimension in markdown


def test_markdown_renders_missing_equipment_as_unknown_without_guessing():
    markdown = render_markdown(*_report_inputs())

    assert "| Armor: helm | Unknown |" in markdown
    assert "| Weapon: w11 | Unknown |" in markdown
    assert "| Relic | Unknown |" in markdown
    assert "Berserker" not in markdown
    assert markdown.endswith("\n")
    assert render_markdown(*_report_inputs()) == markdown
