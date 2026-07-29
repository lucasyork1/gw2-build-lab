import json
import threading
import time
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
        if path in {
            "/v2/specializations",
            "/v2/traits",
            "/v2/skills",
            "/v2/itemstats",
        } and "ids" not in params:
            return [1]
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
    assert sorted(len(call["ids"].split(",")) for call in item_calls) == [
        1,
        1,
        200,
        200,
        200,
        200,
    ]


def test_fetch_runs_item_batches_with_bounded_concurrency(tmp_path):
    client = FakeClient()
    active = 0
    maximum_active = 0
    lock = threading.Lock()
    original_get_json = _many_item_ids_client(client)

    def concurrent_probe(path, params=None):
        nonlocal active, maximum_active
        if path != "/v2/items" or not params or "ids" not in params:
            return original_get_json(path, params)
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.02)
        try:
            return original_get_json(path, params)
        finally:
            with lock:
                active -= 1

    client.get_json = concurrent_probe
    fetch_snapshot(client, tmp_path, fetched_at="2026-07-28T20:00:00Z")

    assert 2 <= maximum_active <= 4


def test_fetch_rejects_item_batch_with_missing_requested_id(tmp_path):
    client = FakeClient()
    original_get_json = client.get_json

    def incomplete_items(path, params=None):
        payload = original_get_json(path, params)
        if path == "/v2/items" and params and "ids" in params:
            return payload[:-1]
        return payload

    client.get_json = incomplete_items

    with pytest.raises(ValueError, match="missing or unexpected IDs"):
        fetch_snapshot(client, tmp_path, fetched_at="2026-07-28T20:00:00Z")

    assert not (tmp_path / "204132").exists()


def test_fetch_rejects_build_change_during_snapshot(tmp_path):
    client = FakeClient()
    original_get_json = client.get_json
    build_calls = 0

    def changing_build(path, params=None):
        nonlocal build_calls
        if path == "/v2/build":
            build_calls += 1
            return {"id": 204132 if build_calls == 1 else 204133}
        return original_get_json(path, params)

    client.get_json = changing_build

    with pytest.raises(RuntimeError, match="changed during snapshot"):
        fetch_snapshot(client, tmp_path, fetched_at="2026-07-28T20:00:00Z")

    assert not (tmp_path / "204132").exists()


def test_fetch_rejects_corrupt_existing_snapshot(tmp_path):
    fetch_snapshot(
        FakeClient(),
        tmp_path,
        fetched_at="2026-07-28T20:00:00Z",
    )
    (tmp_path / "204132" / "items.en.json").write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        fetch_snapshot(
            FakeClient(),
            tmp_path,
            fetched_at="2026-07-28T20:01:00Z",
        )


def test_fetch_rejects_same_truncated_subset_in_both_languages(tmp_path):
    client = FakeClient()
    original_get_json = client.get_json

    def truncated_collection(path, params=None):
        params = params or {}
        if path == "/v2/skills" and "ids" not in params:
            return [1, 2]
        if path == "/v2/skills" and params.get("ids") == "all":
            return [{"id": 1}]
        return original_get_json(path, params)

    client.get_json = truncated_collection

    with pytest.raises(ValueError, match="collection IDs do not match index"):
        fetch_snapshot(client, tmp_path, fetched_at="2026-07-28T20:00:00Z")


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
        if path in {
            "/v2/specializations",
            "/v2/traits",
            "/v2/skills",
            "/v2/itemstats",
        } and "ids" not in params:
            return [1]
        return [{"id": 1}]

    return get_json
