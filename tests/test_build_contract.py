import json
from pathlib import Path

import pytest

from gw2_wvw_data.builds.model import BuildRecord
from gw2_wvw_data.builds.store import load_build, write_build
from gw2_wvw_data.contracts import schema_errors


FIXTURE = Path(__file__).parent / "fixtures" / "builds" / "minimal-thief.json"


def test_minimal_build_fixture_matches_public_schema():
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert schema_errors(value, "build.schema.json") == []


def test_build_round_trip_is_canonical(tmp_path):
    build = BuildRecord.from_dict(json.loads(FIXTURE.read_text(encoding="utf-8")))
    output = tmp_path / "build.json"

    write_build(output, build)

    assert load_build(output) == build
    assert output.read_bytes().endswith(b"\n")


def test_build_rejects_non_thief_or_non_wvw():
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))

    with pytest.raises(ValueError, match="profession must be Thief"):
        BuildRecord.from_dict({**value, "profession": "Mesmer"})
    with pytest.raises(ValueError, match="mode must be wvw"):
        BuildRecord.from_dict({**value, "mode": "pve"})


def test_build_updates_return_a_new_immutable_record():
    build = BuildRecord.from_dict(json.loads(FIXTURE.read_text(encoding="utf-8")))

    updated = build.with_updates(build_id="updated-thief")

    assert updated.build_id == "updated-thief"
    assert build.build_id == "fixture-minimal-thief"
    with pytest.raises(AttributeError):
        build.build_id = "mutated-thief"
