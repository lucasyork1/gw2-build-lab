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


def _fetch_language_files(client: ArenaNetClient, staging: Path, language: str) -> None:
    profession = client.get_json(
        "/v2/professions/Thief",
        params={"lang": language},
    )
    write_json(staging / f"profession.{language}.json", profession)
    for filename, endpoint in COLLECTION_ENDPOINTS.items():
        payload = client.get_json(
            endpoint,
            params={"ids": "all", "lang": language},
        )
        write_json(staging / f"{filename}.{language}.json", payload)


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
    staging = root / f".staging-{game_build_id}-{uuid.uuid4().hex}"
    staging.mkdir()

    try:
        write_json(staging / "build.json", build_payload)
        for language in ("en", "zh"):
            _fetch_language_files(client, staging, language)
        _fetch_items(client, staging)
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
        if destination.exists():
            shutil.rmtree(staging)
        else:
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
