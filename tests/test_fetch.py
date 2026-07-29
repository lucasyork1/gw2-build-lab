import json
from pathlib import Path

import pytest

from gw2_wvw_data.fetch import fetch_snapshot


class FakeClient:
    def __init__(self, *, fail_path=None):
        self.fail_path = fail_path
        self.calls = []

    def get_json(self, path, params=None):
        params = params or {}
        self.calls.append((path, params))
        if path == self.fail_path:
            raise RuntimeError("simulated endpoint failure")
        if path == "/v2/build":
            return {"id": 204132}
        if path == "/v2/items" and "ids" not in params:
            return [101, 102]
        if path == "/v2/items":
            return [{"id": item_id} for item_id in map(int, params["ids"].split(","))]
        if path == "/v2/professions/Thief":
            return {"id": "Thief", "name": "Thief"}
        return [{"id": 1, "name": path.rsplit("/", 1)[-1]}]


def test_fetch_writes_manifest_only_after_every_endpoint_succeeds(tmp_path):
    result = fetch_snapshot(
        FakeClient(),
        tmp_path,
        fetched_at="2026-07-28T20:00:00Z",
    )

    snapshot_dir = tmp_path / "204132"
    manifest = json.loads((snapshot_dir / "manifest.json").read_text("utf-8"))
    assert result.path == snapshot_dir
    assert result.game_build_id == 204132
    assert manifest["game_build_id"] == 204132
    assert manifest["fetched_at"] == "2026-07-28T20:00:00Z"
    assert {entry["path"] for entry in manifest["files"]} >= {
        "profession.en.json",
        "skills.zh.json",
        "items.en.json",
        "items.zh.json",
    }
    assert not list(tmp_path.glob(".staging-*"))
    for entry in manifest["files"]:
        assert len(entry["sha256"]) == 64


def test_fetch_removes_staging_directory_after_partial_failure(tmp_path):
    with pytest.raises(RuntimeError, match="simulated endpoint failure"):
        fetch_snapshot(
            FakeClient(fail_path="/v2/skills"),
            tmp_path,
            fetched_at="2026-07-28T20:00:00Z",
        )

    assert not (tmp_path / "204132").exists()
    assert not list(tmp_path.glob(".staging-*"))


def test_fetch_batches_item_details_at_two_hundred_ids(tmp_path):
    client = FakeClient()
    client.get_json = _many_item_ids_client(client)

    fetch_snapshot(client, tmp_path, fetched_at="2026-07-28T20:00:00Z")

    item_calls = [
        params
        for path, params in client.calls
        if path == "/v2/items" and "ids" in params
    ]
    assert [len(call["ids"].split(",")) for call in item_calls] == [200, 200, 1] * 2


def _many_item_ids_client(client):
    def get_json(path, params=None):
        params = params or {}
        client.calls.append((path, params))
        if path == "/v2/build":
            return {"id": 204132}
        if path == "/v2/items" and "ids" not in params:
            return list(range(1, 402))
        if path == "/v2/items":
            return [{"id": int(value)} for value in params["ids"].split(",")]
        if path == "/v2/professions/Thief":
            return {"id": "Thief", "name": "Thief"}
        return [{"id": 1}]

    return get_json
