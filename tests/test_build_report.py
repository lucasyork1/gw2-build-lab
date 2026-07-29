import json
from dataclasses import replace
from pathlib import Path

import httpx

from gw2_wvw_data.analysis import (
    AnalysisConclusion,
    BuildAnalysis,
    BuildComparison,
    DimensionAnalysis,
    EvidenceReference,
    StructuralChange,
)
from gw2_wvw_data.audit import BuildAudit
from gw2_wvw_data.builds import BuildRecord
from gw2_wvw_data.builds import report as build_report
from gw2_wvw_data.builds.report import (
    render_comparison_markdown,
    render_markdown,
)
from gw2_wvw_data.builds.service import analyze_input
from gw2_wvw_data.importers.http import SafeHttpClient


FIXTURE = Path(__file__).parent / "fixtures" / "builds" / "minimal-thief.json"
ROOT = Path(__file__).parents[1]
CURRENT = ROOT / "data" / "normalized" / "current"
RULES = ROOT / "data" / "analysis-rules" / "thief-wvw-v1.json"
GW2SKILLS_FIXTURE = (
    ROOT / "tests" / "fixtures" / "importers" / "gw2skills-thief.html"
)
GW2SKILLS_URL = "https://en.gw2skills.net/editor/?fixture"
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
        assert dimension.replace("_", "\\_") in markdown


def test_markdown_renders_missing_equipment_as_unknown_without_guessing():
    markdown = render_markdown(*_report_inputs())

    assert "| Armor: helm | Unknown |" in markdown
    assert "| Weapon: w11 | Unknown |" in markdown
    assert "| Weapon: w11 type | Unknown |" in markdown
    assert "| Weapon: w11 item | Unknown |" in markdown
    assert "| Weapon: w11 quality | Unknown |" in markdown
    assert "| Weapon: w11 upgrade/sigil 1 | Unknown |" in markdown
    assert "| Weapon: w11 infusion 1 | Unknown |" in markdown
    assert "| Relic | Unknown |" in markdown
    assert "Berserker" not in markdown
    assert markdown.endswith("\n")
    assert render_markdown(*_report_inputs()) == markdown


def test_markdown_renders_every_gw2skills_weapon_subfield_offline():
    html = GW2SKILLS_FIXTURE.read_text("utf-8")
    client = SafeHttpClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                content=html.encode("utf-8"),
                request=request,
            )
        )
    )
    bundle = analyze_input(
        build_code=None,
        gw2skills_url=GW2SKILLS_URL,
        dataset_path=CURRENT,
        rules_path=RULES,
        client=client,
    )

    markdown = render_markdown(
        bundle.build,
        bundle.audit,
        bundle.analysis,
    )

    expected_rows = (
        "| Weapon: w11 type | gw2skills:13 |",
        "| Weapon: w11 item | gw2skills:290 |",
        "| Weapon: w11 quality | 6 |",
        "| Weapon: w11 upgrade/sigil 1 | gw2skills:121 |",
        "| Weapon: w11 upgrade/sigil 2 | gw2skills:122 |",
        "| Weapon: w11 infusion 1 | gw2skills:901 |",
        "| Weapon: w12 type | gw2skills:9 |",
        "| Weapon: w12 item | gw2skills:291 |",
        "| Weapon: w12 quality | 6 |",
        "| Weapon: w12 upgrade/sigil 1 | gw2skills:123 |",
        "| Weapon: w12 infusion 1 | gw2skills:902 |",
    )
    for row in expected_rows:
        assert row in markdown
    positions = [markdown.index(row) for row in expected_rows]
    assert positions == sorted(positions)


def test_markdown_sanitizes_adversarial_identity_names_and_sources():
    build, audit, analysis = _report_inputs()
    value = build.to_dict()
    adversarial_id = (
        "build <script>alert(1)</script> | [link](target)\n"
        "# injected `tick`"
    )
    value["build_id"] = adversarial_id
    value["armor"]["helm"] = {
        "id": 42,
        "name": "Helm <img src=x> | [slot]\n# row `escape`",
        "source": "fixture",
        "confidence": "exact",
    }
    value["provenance"]["sources"] = [
        {
            "source": "source <b> | [name]\n# list `tick`",
            "url": "https://example.test/<tag>|[path]`",
        }
    ]
    build = BuildRecord.from_dict(value)
    audit = replace(audit, build_id=adversarial_id)
    analysis = replace(analysis, build_id=adversarial_id)

    markdown = render_markdown(build, audit, analysis)

    assert "<script>" not in markdown
    assert "<img" not in markdown
    assert "<b>" not in markdown
    assert "\n# injected" not in markdown
    assert "\n# row" not in markdown
    assert "\n# list" not in markdown
    assert "&lt;script&gt;" in markdown
    assert "&lt;img src=x&gt;" in markdown
    assert "\\| \\[link\\]\\(target\\)" in markdown
    assert "\\# injected \\`tick\\`" in markdown
    assert "\\| \\[slot\\] \\# row \\`escape\\`" in markdown


def test_code_span_uses_a_longer_fence_and_commonmark_padding():
    assert build_report._code_span("`edge`") == "`` `edge` ``"
    assert build_report._code_span("a ``` run") == "````a ``` run````"


def test_comparison_markdown_uses_safe_code_spans_for_adversarial_values():
    comparison = BuildComparison(
        left_build_id="left",
        right_build_id="right",
        additions=(
            StructuralChange(
                "armor",
                "armor.helm",
                "<script>alert(1)</script> ``` | [x]\n# heading",
            ),
        ),
        removals=(),
        replacements=(),
    )

    markdown = render_comparison_markdown(comparison)
    change_line = next(
        line for line in markdown.splitlines() if line.startswith("- ````")
    )

    assert "<script>" not in markdown
    assert "&lt;script&gt;" in change_line
    assert "```" in change_line
    assert change_line.endswith("}````")
