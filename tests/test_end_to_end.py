import json
import sqlite3
from pathlib import Path

from gw2_wvw_data.diff import diff_datasets
from gw2_wvw_data.io import sha256_file
from gw2_wvw_data.normalize import normalize_snapshot
from gw2_wvw_data.overrides import apply_overrides, load_dataset, write_dataset
from gw2_wvw_data.release import build_release
from gw2_wvw_data.validate import main as validate_main


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "api" / "normalized-input.json"


def _write_snapshot(root: Path) -> Path:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for language in ("en", "zh"):
        payload["profession"][language]["weapons"] = {"Dagger": {}}
        for record in payload["items"][language]:
            record["game_types"] = ["Wvw"]
        item = next(
            item for item in payload["items"][language] if item["id"] == 1000
        )
        item["rarity"] = "Exotic"
        item["details"]["weight_class"] = "Medium"
    snapshot = root / "raw" / "204132"
    snapshot.mkdir(parents=True)
    for category, localized in payload.items():
        for language, value in localized.items():
            (snapshot / f"{category}.{language}.json").write_text(
                json.dumps(value),
                encoding="utf-8",
            )
    files = [
        {"path": path.name, "sha256": sha256_file(path)}
        for path in sorted(snapshot.glob("*.json"))
    ]
    (snapshot / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "game_build_id": 204132,
                "fetched_at": "2026-07-28T20:00:00Z",
                "api_base_url": "https://api.guildwars2.com",
                "files": files,
            }
        ),
        encoding="utf-8",
    )
    return snapshot


def _hashes(path: Path) -> dict[str, str]:
    return {
        artifact.name: sha256_file(artifact)
        for artifact in path.iterdir()
    }


def test_offline_pipeline_is_valid_and_reproducible(tmp_path):
    snapshot = _write_snapshot(tmp_path)
    normalized_path = tmp_path / "normalized"
    applied_path = tmp_path / "applied"
    normalize_snapshot(snapshot, normalized_path)
    original = load_dataset(normalized_path)
    override = {
        "entity_kind": "skill",
        "entity_id": 100,
        "json_pointer": "/names/en",
        "mode": "wvw",
        "value": "Steal (WvW)",
        "previous_value": "Steal",
        "effective_patch": "2026-07-14",
        "source_url": (
            "https://en-forum.guildwars2.com/topic/"
            "174766-game-update-notes-july-14-2026/"
        ),
        "verification_status": "human_verified",
        "notes": "End-to-end fixture correction",
    }
    write_dataset(applied_path, apply_overrides(original, [override]))

    assert validate_main(
        [
            "--dataset",
            str(applied_path),
            "--sources",
            str(ROOT / "data" / "provenance" / "sources.json"),
        ]
    ) == 0
    report = diff_datasets(original, load_dataset(applied_path))
    assert report["added"] == []
    assert report["removed"] == []
    assert len(report["changed"]) == 1
    assert "/names/en" in report["changed"][0]["paths"]

    first = build_release(applied_path, tmp_path / "release-one")
    second = build_release(applied_path, tmp_path / "release-two")
    assert _hashes(first.path) == _hashes(second.path)

    expected_entities = 1 + sum(
        len(load_dataset(applied_path)[name])
        for name in (
            "specializations",
            "traits",
            "skills",
            "itemstats",
            "equipment",
            "upgrades",
            "consumables",
        )
    )
    with sqlite3.connect(first.sqlite_database) as connection:
        sqlite_entities = connection.execute(
            "SELECT COUNT(*) FROM entity"
        ).fetchone()[0]
    assert sqlite_entities == expected_entities
