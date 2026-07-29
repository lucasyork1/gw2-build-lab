import json
from pathlib import Path

from jsonschema import Draft202012Validator

from gw2_wvw_data.normalize import normalize_snapshot


FIXTURE = Path(__file__).parent / "fixtures" / "api" / "normalized-input.json"


def _write_snapshot(tmp_path, *, missing_trait=False):
    payload = json.loads(FIXTURE.read_text("utf-8"))
    snapshot = tmp_path / "raw" / "204132"
    snapshot.mkdir(parents=True)
    (snapshot / "manifest.json").write_text(
        json.dumps({"game_build_id": 204132, "fetched_at": "2026-07-28T20:00:00Z"}),
        encoding="utf-8",
    )
    for category, localized in payload.items():
        if missing_trait and category == "traits":
            localized["en"] = []
            localized["zh"] = []
        for language, value in localized.items():
            (snapshot / f"{category}.{language}.json").write_text(
                json.dumps(value),
                encoding="utf-8",
            )
    return snapshot


def _load(path):
    return json.loads(path.read_text("utf-8"))


def test_normalize_keeps_thief_closure_and_relevant_equipment(tmp_path):
    snapshot = _write_snapshot(tmp_path)
    output = tmp_path / "normalized"

    result = normalize_snapshot(snapshot, output)

    assert result["manifest"]["game_build_id"] == 204132
    assert [record["id"] for record in result["specializations"]] == [1]
    assert [record["id"] for record in result["traits"]] == [10]
    assert [record["id"] for record in result["skills"]] == [100]
    assert [record["id"] for record in result["equipment"]] == [1000]
    assert [record["id"] for record in result["upgrades"]] == [1001]
    assert [record["id"] for record in result["consumables"]] == [1002]
    assert result["skills"][0]["names"] == {"en": "Steal", "zh": "偷窃"}
    assert result["manifest"]["unresolved_references"] == []


def test_normalize_records_missing_references_in_manifest(tmp_path):
    snapshot = _write_snapshot(tmp_path, missing_trait=True)

    result = normalize_snapshot(snapshot, tmp_path / "normalized")

    assert result["manifest"]["unresolved_references"] == [
        {"kind": "trait", "id": 10, "referenced_by": "specialization:1"}
    ]


def test_normalized_entities_conform_to_public_schema(tmp_path):
    snapshot = _write_snapshot(tmp_path)
    output = tmp_path / "normalized"

    normalize_snapshot(snapshot, output)

    schema_path = Path(__file__).parents[1] / "schemas" / "entity.schema.json"
    schema = _load(schema_path)
    validator = Draft202012Validator(schema)
    for filename in (
        "specializations.json",
        "traits.json",
        "skills.json",
        "itemstats.json",
        "equipment.json",
        "upgrades.json",
        "consumables.json",
    ):
        for entity in _load(output / filename):
            assert list(validator.iter_errors(entity)) == []


def test_normalize_output_is_byte_stable(tmp_path):
    snapshot = _write_snapshot(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"

    normalize_snapshot(snapshot, first)
    normalize_snapshot(snapshot, second)

    assert {
        path.name: path.read_bytes() for path in first.glob("*.json")
    } == {
        path.name: path.read_bytes() for path in second.glob("*.json")
    }
