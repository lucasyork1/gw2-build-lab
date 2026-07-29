from gw2_wvw_data.diff import diff_datasets


def _dataset(coefficient, *, fetched_at):
    return {
        "skills": [
            {
                "id": 123,
                "kind": "skill",
                "fetched_at": fetched_at,
                "payload": {"facts": [{"type": "Damage", "value": coefficient}]},
            }
        ],
        "manifest": {"game_build_id": 204132},
    }


def test_diff_reports_field_level_semantic_change():
    old = _dataset(1.25, fetched_at="2026-07-14T00:00:00Z")
    new = _dataset(0.8, fetched_at="2026-07-28T00:00:00Z")

    report = diff_datasets(old, new)

    assert report == {
        "old_game_build_id": 204132,
        "new_game_build_id": 204132,
        "added": [],
        "removed": [],
        "changed": [
            {
                "entity_kind": "skill",
                "entity_id": 123,
                "paths": ["/payload/facts/0/value"],
                "old": 1.25,
                "new": 0.8,
            }
        ],
    }


def test_diff_ignores_fetch_timestamp_only_change():
    old = _dataset(1.25, fetched_at="2026-07-14T00:00:00Z")
    new = _dataset(1.25, fetched_at="2026-07-28T00:00:00Z")

    report = diff_datasets(old, new)

    assert report["changed"] == []


def test_diff_reports_added_and_removed_entities():
    old = _dataset(1.25, fetched_at="2026-07-14T00:00:00Z")
    new = {"skills": [], "traits": [{"id": 77, "kind": "trait"}], "manifest": {"game_build_id": 204133}}

    report = diff_datasets(old, new)

    assert report["removed"] == [{"entity_kind": "skill", "entity_id": 123}]
    assert report["added"] == [{"entity_kind": "trait", "entity_id": 77}]
