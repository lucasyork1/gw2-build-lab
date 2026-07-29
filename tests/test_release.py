import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from gw2_wvw_data.io import sha256_file
import gw2_wvw_data.release as release_module
from gw2_wvw_data.release import build_release


def _entity(entity_id, kind, payload=None):
    return {
        "id": entity_id,
        "kind": kind,
        "names": {"en": str(entity_id), "zh": str(entity_id)},
        "mode": "wvw",
        "game_build_id": 204132,
        "effective_patch": None,
        "fetched_at": "2026-07-28T20:00:00Z",
        "source_refs": [f"arenanet-api:{kind}s:{entity_id}"],
        "verification_status": "automated",
        "payload": payload or {},
    }


def _write_dataset(root, *, valid=True):
    root.mkdir()
    files = {
        "profession.json": _entity("Thief", "profession"),
        "specializations.json": [],
        "traits.json": [],
        "skills.json": [_entity(123, "skill", {"coefficient": 0.8})],
        "itemstats.json": [_entity(584, "itemstat")],
        "equipment.json": [
            _entity(
                1000,
                "equipment",
                {"details": {"infix_upgrade": {"id": 584}}},
            )
        ],
        "upgrades.json": [],
        "consumables.json": [],
        "applied-overrides.json": [],
    }
    for filename, value in files.items():
        (root / filename).write_text(json.dumps(value), encoding="utf-8")
    (root / "dataset-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "game_build_id": 204132,
                "fetched_at": "2026-07-28T20:00:00Z",
                "mode": "wvw" if valid else "pvp",
                "files": [name for name in files if name != "applied-overrides.json"],
                "unresolved_references": [],
            }
        ),
        encoding="utf-8",
    )
    return root


def test_release_is_byte_reproducible(tmp_path):
    dataset = _write_dataset(tmp_path / "dataset")

    first = build_release(dataset, tmp_path / "first")
    second = build_release(dataset, tmp_path / "second")

    first_hashes = {path.name: sha256_file(path) for path in first.path.iterdir()}
    second_hashes = {path.name: sha256_file(path) for path in second.path.iterdir()}
    assert first_hashes == second_hashes


def test_zip_uses_fixed_member_timestamps(tmp_path):
    dataset = _write_dataset(tmp_path / "dataset")

    result = build_release(dataset, tmp_path / "release")

    with zipfile.ZipFile(result.json_archive) as archive:
        assert {member.date_time for member in archive.infolist()} == {
            (1980, 1, 1, 0, 0, 0)
        }
        assert {member.compress_type for member in archive.infolist()} == {
            zipfile.ZIP_STORED
        }


def test_sqlite_matches_json_entities_and_foreign_keys(tmp_path):
    dataset = _write_dataset(tmp_path / "dataset")

    result = build_release(dataset, tmp_path / "release")

    with sqlite3.connect(result.sqlite_database) as connection:
        entity_count = connection.execute("SELECT COUNT(*) FROM entity").fetchone()[0]
        foreign_key_issues = connection.execute("PRAGMA foreign_key_check").fetchall()
    assert entity_count == 4
    assert foreign_key_issues == []


def test_invalid_dataset_produces_no_release_directory(tmp_path):
    dataset = _write_dataset(tmp_path / "dataset", valid=False)
    output = tmp_path / "release"

    with pytest.raises(ValueError, match="invalid_mode"):
        build_release(dataset, output)

    assert not output.exists()


def test_release_rejects_json_sqlite_parity_failure(tmp_path, monkeypatch):
    dataset = _write_dataset(tmp_path / "dataset")
    original_build_sqlite = release_module._build_sqlite

    def corrupt_database(source, destination):
        original_build_sqlite(source, destination)
        connection = sqlite3.connect(destination)
        try:
            connection.execute(
                "DELETE FROM entity WHERE rowid = (SELECT MIN(rowid) FROM entity)"
            )
            connection.commit()
        finally:
            connection.close()

    monkeypatch.setattr(release_module, "_build_sqlite", corrupt_database)
    output = tmp_path / "release"

    with pytest.raises(ValueError, match="JSON/SQLite parity"):
        build_release(dataset, output)

    assert not output.exists()
