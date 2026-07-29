import json
from pathlib import Path

from gw2_wvw_data.builds.service import analyze_input
from gw2_wvw_data.contracts import schema_errors


ROOT = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "community-builds"
MANIFEST = FIXTURES / "seed-manifest.json"
CURRENT = ROOT / "data" / "normalized" / "current"
RULES = ROOT / "data" / "analysis-rules" / "thief-wvw-v1.json"
ARCHITECTURE_IDS = [
    "daredevil-power-sd",
    "daredevil-celestial-sa-axe-pistol",
    "daredevil-power-scepter",
    "daredevil-sa-dagger-pistol",
    "deadeye-sa-rifle",
    "specter-celestial-scepter",
    "core-pistol-dagger-condition",
]
ELITE_SPECIALIZATIONS = {"Daredevil", "Deadeye", "Specter", "Antiquary"}


def test_seed_corpus_imports_audits_and_analyzes_all_roaming_architectures():
    assert MANIFEST.is_file(), "the seven-build seed manifest must be checked in"
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert [entry["architecture_id"] for entry in manifest] == ARCHITECTURE_IDS
    assert all(entry["context"] == "roaming" for entry in manifest)
    assert all(entry["source_type"] == "build_code" for entry in manifest)

    for entry in manifest:
        fixture = FIXTURES / entry["fixture"]
        assert fixture.parent == FIXTURES
        build_code = fixture.read_text(encoding="utf-8").strip()
        bundle = analyze_input(
            build_code=build_code,
            gw2skills_url=None,
            dataset_path=CURRENT,
            rules_path=RULES,
        )

        assert bundle.build.profession == "Thief"
        assert bundle.build.mode == "wvw"
        specialization_names = {
            component.name
            for component in bundle.build.specializations
            if component.name is not None
        }
        assert "expected_specializations" in entry
        assert specialization_names == set(entry["expected_specializations"])
        if entry["expected_specialization"] == "Core":
            assert specialization_names.isdisjoint(ELITE_SPECIALIZATIONS)
        else:
            assert entry["expected_specialization"] in specialization_names
        assert [
            weapon["type"].name for weapon in bundle.build.weapons
        ] == entry["expected_weapons"]

        assert bundle.audit.legality == "legal"
        assert bundle.audit.status == entry["expected_status"]
        assert bundle.audit.missing_fields
        assert not schema_errors(bundle.build.to_dict(), "build.schema.json")
        assert not schema_errors(
            bundle.audit.to_dict(), "build-audit.schema.json"
        )
        assert not schema_errors(
            bundle.analysis.to_dict(), "build-analysis.schema.json"
        )
        for dimension in bundle.analysis.dimensions.values():
            if dimension.evidence:
                continue
            assert dimension.confidence == "low"
            assert (
                "zero evidence: no matching evidence rules contributed to "
                "this dimension"
                in dimension.confidence_reasons
            )
