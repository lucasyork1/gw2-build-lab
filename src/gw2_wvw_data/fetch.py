"""Acquire complete, immutable public API snapshots."""

from __future__ import annotations

import argparse
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gw2_wvw_data.api import ArenaNetClient
from gw2_wvw_data.contracts import verify_raw_snapshot
from gw2_wvw_data.io import sha256_file, write_json


@dataclass(frozen=True)
class SnapshotManifest:
    """Result of a completed snapshot acquisition."""

    game_build_id: int
    path: Path
    files: tuple[dict[str, str], ...]


COLLECTION_ENDPOINTS = {
    "specializations": "/v2/specializations",
    "traits": "/v2/traits",
    "skills": "/v2/skills",
    "itemstats": "/v2/itemstats",
}


def _record_ids(payload: Any, endpoint: str) -> set[int | str]:
    if not isinstance(payload, list):
        raise ValueError(f"{endpoint} did not return a list")
    identifiers: set[int | str] = set()
    for record in payload:
        if not isinstance(record, dict) or not isinstance(record.get("id"), (int, str)):
            raise ValueError(f"{endpoint} returned a record without a valid id")
        if record["id"] in identifiers:
            raise ValueError(f"{endpoint} returned duplicate id {record['id']}")
        identifiers.add(record["id"])
    return identifiers


def _fetch_language_files(
    client: ArenaNetClient,
    staging: Path,
    language: str,
    expected_ids: dict[str, set[int]],
) -> dict[str, set[int | str]]:
    profession = client.get_json(
        "/v2/professions/Thief",
        params={"lang": language, "v": "latest"},
    )
    if not isinstance(profession, dict) or profession.get("id") != "Thief":
        raise ValueError("/v2/professions/Thief returned an invalid profession")
    write_json(staging / f"profession.{language}.json", profession)
    identifiers: dict[str, set[int | str]] = {}
    for filename, endpoint in COLLECTION_ENDPOINTS.items():
        payload = client.get_json(
            endpoint,
            params={"ids": "all", "lang": language},
        )
        identifiers[filename] = _record_ids(payload, endpoint)
        if identifiers[filename] != expected_ids[filename]:
            raise ValueError(
                f"{endpoint} collection IDs do not match index"
            )
        write_json(staging / f"{filename}.{language}.json", payload)
    return identifiers


def _fetch_items(client: ArenaNetClient, staging: Path) -> None:
    item_ids = client.get_json("/v2/items")
    if not isinstance(item_ids, list) or any(not isinstance(item_id, int) for item_id in item_ids):
        raise ValueError("/v2/items did not return a list of integer IDs")
    batches = [
        item_ids[offset : offset + 200]
        for offset in range(0, len(item_ids), 200)
    ]

    def fetch_batch(batch: list[int], language: str) -> list[Any]:
        payload = client.get_json(
            "/v2/items",
            params={
                "ids": ",".join(str(item_id) for item_id in batch),
                "lang": language,
            },
        )
        if not isinstance(payload, list):
            raise ValueError("/v2/items detail request did not return a list")
        returned_ids = _record_ids(payload, "/v2/items")
        if returned_ids != set(batch):
            raise ValueError("/v2/items batch returned missing or unexpected IDs")
        return payload

    for language in ("en", "zh"):
        items: list[Any] = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            payloads = executor.map(
                lambda batch: fetch_batch(batch, language),
                batches,
            )
            for payload in payloads:
                items.extend(payload)
        write_json(staging / f"items.{language}.json", items)


def fetch_snapshot(
    client: ArenaNetClient,
    output_root: str | Path,
    *,
    fetched_at: str,
) -> SnapshotManifest:
    """Fetch all required endpoints and atomically publish one raw snapshot."""

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    build_payload = client.get_json("/v2/build")
    if not isinstance(build_payload, dict) or not isinstance(build_payload.get("id"), int):
        raise ValueError("/v2/build did not return an integer id")
    game_build_id = build_payload["id"]
    destination = root / str(game_build_id)
    if destination.exists():
        existing_manifest = verify_raw_snapshot(destination)
        return SnapshotManifest(
            game_build_id,
            destination,
            tuple(existing_manifest["files"]),
        )
    staging = root / f".staging-{game_build_id}-{uuid.uuid4().hex}"
    staging.mkdir()

    try:
        write_json(staging / "build.json", build_payload)
        expected_ids: dict[str, set[int]] = {}
        for filename, endpoint in COLLECTION_ENDPOINTS.items():
            index = client.get_json(endpoint)
            if (
                not isinstance(index, list)
                or any(not isinstance(identifier, int) for identifier in index)
                or len(index) != len(set(index))
            ):
                raise ValueError(f"{endpoint} did not return a unique integer ID index")
            expected_ids[filename] = set(index)
        english_ids = _fetch_language_files(
            client,
            staging,
            "en",
            expected_ids,
        )
        chinese_ids = _fetch_language_files(
            client,
            staging,
            "zh",
            expected_ids,
        )
        if english_ids != chinese_ids:
            raise ValueError("localized collection ID sets do not match")
        _fetch_items(client, staging)
        final_build = client.get_json("/v2/build")
        if (
            not isinstance(final_build, dict)
            or final_build.get("id") != game_build_id
        ):
            raise RuntimeError(
                f"game build changed during snapshot from {game_build_id}"
            )
        files = tuple(
            {
                "path": path.name,
                "sha256": sha256_file(path),
            }
            for path in sorted(staging.glob("*.json"), key=lambda value: value.name)
        )
        manifest = {
            "schema_version": 1,
            "game_build_id": game_build_id,
            "fetched_at": fetched_at,
            "api_base_url": ArenaNetClient.BASE_URL,
            "files": list(files),
        }
        write_json(staging / "manifest.json", manifest)
        staging.replace(destination)
        return SnapshotManifest(game_build_id, destination, files)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for fetching one snapshot."""

    parser = argparse.ArgumentParser(prog="gw2-wvw-data fetch")
    parser.add_argument("--output", type=Path, default=Path("data/raw"))
    arguments = parser.parse_args(argv)
    fetched_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with ArenaNetClient() as client:
        result = fetch_snapshot(client, arguments.output, fetched_at=fetched_at)
    print(result.path)
    return 0
