import json
from copy import deepcopy
from pathlib import Path

import pytest

from gw2_wvw_data.overrides import OverrideConflictError, apply_overrides


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "overrides"


@pytest.fixture
def valid_dataset():
    return {
        "profession": {},
        "skills": [
            {
                "id": 123,
                "kind": "skill",
                "mode": "wvw",
                "effective_patch": None,
                "source_refs": ["arenanet-api:skills:123"],
                "verification_status": "automated",
                "payload": {"coefficient": 1.25},
            }
        ],
        "manifest": {"game_build_id": 204132},
    }


@pytest.fixture
def valid_override():
    return json.loads((FIXTURE_ROOT / "valid.json").read_text("utf-8"))[0]


def test_override_changes_effective_view_without_mutating_input(
    valid_dataset, valid_override
):
    original = deepcopy(valid_dataset)

    result = apply_overrides(valid_dataset, [valid_override])

    skill = result["skills"][0]
    assert skill["payload"]["coefficient"] == 0.8
    assert skill["effective_patch"] == "2026-07-14"
    assert skill["verification_status"] == "human_verified"
    assert valid_dataset == original


def test_two_values_for_same_target_and_patch_are_conflict(valid_dataset):
    overrides = json.loads((FIXTURE_ROOT / "conflict.json").read_text("utf-8"))

    with pytest.raises(OverrideConflictError, match="entity_id=123"):
        apply_overrides(valid_dataset, overrides)


@pytest.mark.parametrize("missing_field", ["effective_patch", "source_url"])
def test_override_requires_patch_and_source(valid_dataset, valid_override, missing_field):
    invalid = {key: value for key, value in valid_override.items() if key != missing_field}

    with pytest.raises(ValueError, match=missing_field):
        apply_overrides(valid_dataset, [invalid])


def test_override_rejects_unknown_target(valid_dataset, valid_override):
    invalid = {**valid_override, "entity_id": 999}

    with pytest.raises(OverrideConflictError, match="target does not exist"):
        apply_overrides(valid_dataset, [invalid])


def test_override_rejects_stale_previous_value(valid_dataset, valid_override):
    invalid = {**valid_override, "previous_value": 9.9}

    with pytest.raises(OverrideConflictError, match="expected 9.9"):
        apply_overrides(valid_dataset, [invalid])


def test_override_requires_https_source(valid_dataset, valid_override):
    invalid = {**valid_override, "source_url": "http://example.com/patch"}

    with pytest.raises(ValueError, match="HTTPS"):
        apply_overrides(valid_dataset, [invalid])


def test_override_rejects_schema_forbidden_extra_field(valid_dataset, valid_override):
    invalid = {**valid_override, "trust_me": True}

    with pytest.raises(ValueError, match="override schema invalid"):
        apply_overrides(valid_dataset, [invalid])
