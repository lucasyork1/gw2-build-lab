import json
from copy import deepcopy
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from gw2_wvw_data.builds.model import BuildRecord


ROOT = Path(__file__).parents[1]
RUNTIME_SCHEMAS = (
    "manifest.schema.json",
    "dataset.schema.json",
    "entity.schema.json",
    "override.schema.json",
    "release-manifest.schema.json",
    "build.schema.json",
    "build-audit.schema.json",
    "analysis-rules.schema.json",
    "build-analysis.schema.json",
)


def test_packaged_schemas_match_public_contracts():
    packaged = files("gw2_wvw_data").joinpath("schemas")

    for name in RUNTIME_SCHEMAS:
        assert packaged.joinpath(name).read_bytes() == (
            ROOT / "schemas" / name
        ).read_bytes()


def test_public_analysis_schema_resolves_adjacent_build_contract():
    build_schema = json.loads(
        (ROOT / "schemas" / "build.schema.json").read_text(encoding="utf-8")
    )
    analysis_path = ROOT / "schemas" / "build-analysis.schema.json"
    analysis_text = analysis_path.read_text(encoding="utf-8")
    analysis_schema = json.loads(analysis_text)
    build_id = (
        "https://lucasyork1.github.io/gw2-build-lab/"
        "schemas/build.schema.json"
    )
    analysis_id = (
        "https://lucasyork1.github.io/gw2-build-lab/"
        "schemas/build-analysis.schema.json"
    )

    assert build_schema.get("$id") == build_id
    assert analysis_schema.get("$id") == analysis_id
    assert "urn:gw2-wvw-data" not in analysis_text

    registry = Registry().with_resources(
        [
            (build_id, Resource.from_contents(build_schema)),
            (analysis_id, Resource.from_contents(analysis_schema)),
        ]
    )
    validator = Draft202012Validator(
        analysis_schema,
        registry=registry,
    )
    derived_build = BuildRecord.from_dict(
        json.loads(
            (
                ROOT
                / "tests"
                / "fixtures"
                / "builds"
                / "minimal-thief.json"
            ).read_text(encoding="utf-8")
        )
    ).with_updates(
        build_id="fixture-minimal-thief--fixture-improvement"
    ).to_dict()
    result = {
        "schema_version": 1,
        "build_id": "fixture-analysis",
        "ruleset_id": "fixture-rules",
        "dimensions": {
            name: {
                "band": 3,
                "label": "medium",
                "confidence": "high",
                "confidence_reasons": [],
                "evidence": [],
            }
            for name in (
                "burst_damage",
                "sustained_damage",
                "survival_recovery",
                "condition_cleanse",
                "control_interrupt",
                "mobility_disengage",
                "stealth_reset",
                "operation_difficulty",
            )
        },
        "strengths": [],
        "weaknesses": [],
        "improvements": [
            {
                "improvement_id": "fixture-improvement",
                "replace": {
                    "component_kind": "skill",
                    "component_id": 1,
                    "field": "skills.utilities[0]",
                },
                "with": {
                    "component_kind": "skill",
                    "component_id": 2,
                    "field": "skills.utilities[0]",
                },
                "benefit": "Fixture benefit.",
                "cost": "Fixture cost.",
                "applies_when": [
                    {
                        "component_kind": "skill",
                        "component_id": 1,
                        "field": None,
                    }
                ],
                "evidence": [
                    {
                        "component_kind": "skill",
                        "component_id": 1,
                        "field": "payload",
                    }
                ],
                "derived_build": derived_build,
            }
        ],
        "improvement_reasons": [],
    }

    assert list(validator.iter_errors(result)) == []
    invalid = deepcopy(result)
    invalid["improvements"][0]["derived_build"] = {}
    assert list(validator.iter_errors(invalid))
