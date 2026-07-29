"""Build deterministic JSON and SQLite release artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from gw2_wvw_data.contracts import schema_errors
from gw2_wvw_data.io import sha256_file, write_json
from gw2_wvw_data.overrides import load_dataset
from gw2_wvw_data.validate import validate_dataset


@dataclass(frozen=True)
class ReleaseResult:
    """Paths produced by a successful release build."""

    path: Path
    json_archive: Path
    sqlite_database: Path
    manifest: Path


def _iter_entities(dataset: dict[str, Any]) -> Iterable[dict[str, Any]]:
    profession = dataset.get("profession")
    if isinstance(profession, dict) and "kind" in profession:
        yield profession
    for value in dataset.values():
        if isinstance(value, list):
            for record in value:
                if isinstance(record, dict) and "kind" in record:
                    yield record


def _source_row(source_ref: str, fetched_at: str) -> tuple[str, str, str, str]:
    source_type = source_ref.split(":", 1)[0]
    if source_type == "wvw-override":
        url = source_ref.split(":", 1)[1]
    else:
        url = "https://api.guildwars2.com"
    return source_ref, source_type, url, fetched_at


def _build_sqlite(dataset: dict[str, Any], destination: Path) -> None:
    connection = sqlite3.connect(destination)
    try:
        connection.executescript(
            """
            PRAGMA page_size = 4096;
            PRAGMA journal_mode = DELETE;
            PRAGMA synchronous = FULL;
            PRAGMA foreign_keys = ON;
            CREATE TABLE entity (
              kind TEXT NOT NULL,
              id TEXT NOT NULL,
              name_en TEXT,
              name_zh TEXT,
              mode TEXT NOT NULL CHECK (mode = 'wvw'),
              game_build_id INTEGER NOT NULL,
              effective_patch TEXT,
              verification_status TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              PRIMARY KEY (kind, id)
            );
            CREATE TABLE source (
              source_id TEXT PRIMARY KEY,
              source_type TEXT NOT NULL,
              url TEXT NOT NULL,
              fetched_at TEXT NOT NULL
            );
            CREATE TABLE entity_source (
              kind TEXT NOT NULL,
              entity_id TEXT NOT NULL,
              source_id TEXT NOT NULL,
              PRIMARY KEY (kind, entity_id, source_id),
              FOREIGN KEY (kind, entity_id) REFERENCES entity(kind, id),
              FOREIGN KEY (source_id) REFERENCES source(source_id)
            );
            """
        )
        entities = sorted(
            _iter_entities(dataset),
            key=lambda record: (record["kind"], str(record["id"])),
        )
        sources: dict[str, tuple[str, str, str, str]] = {}
        links: list[tuple[str, str, str]] = []
        for entity in entities:
            connection.execute(
                """
                INSERT INTO entity (
                  kind, id, name_en, name_zh, mode, game_build_id,
                  effective_patch, verification_status, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity["kind"],
                    str(entity["id"]),
                    entity.get("names", {}).get("en"),
                    entity.get("names", {}).get("zh"),
                    entity["mode"],
                    entity["game_build_id"],
                    entity.get("effective_patch"),
                    entity["verification_status"],
                    json.dumps(
                        entity.get("payload", {}),
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                ),
            )
            for source_ref in sorted(entity.get("source_refs", [])):
                sources[source_ref] = _source_row(
                    source_ref,
                    entity.get("fetched_at", dataset["manifest"]["fetched_at"]),
                )
                links.append((entity["kind"], str(entity["id"]), source_ref))
        connection.executemany(
            "INSERT INTO source (source_id, source_type, url, fetched_at) VALUES (?, ?, ?, ?)",
            [sources[key] for key in sorted(sources)],
        )
        connection.executemany(
            "INSERT INTO entity_source (kind, entity_id, source_id) VALUES (?, ?, ?)",
            sorted(links),
        )
        connection.commit()
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("SQLite foreign key validation failed")
        connection.execute("VACUUM")
    finally:
        connection.close()


def _verify_sqlite_parity(dataset: dict[str, Any], database: Path) -> None:
    expected = {
        (
            entity["kind"],
            str(entity["id"]),
            json.dumps(
                entity.get("payload", {}),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
        for entity in _iter_entities(dataset)
    }
    connection = sqlite3.connect(database)
    try:
        actual = set(
            connection.execute(
                "SELECT kind, id, payload_json FROM entity"
            ).fetchall()
        )
        foreign_key_issues = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
    finally:
        connection.close()
    if actual != expected or foreign_key_issues:
        raise ValueError("JSON/SQLite parity validation failed")


def _build_zip(dataset_dir: Path, destination: Path) -> None:
    json_files = sorted(dataset_dir.glob("*.json"), key=lambda path: path.name)
    with zipfile.ZipFile(
        destination,
        mode="w",
        compression=zipfile.ZIP_STORED,
    ) as archive:
        for path in json_files:
            info = zipfile.ZipInfo(path.name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_STORED)


def build_release(
    dataset_dir: str | Path,
    output_dir: str | Path,
) -> ReleaseResult:
    """Validate a dataset, then atomically build reproducible artifacts."""

    dataset_path = Path(dataset_dir)
    output = Path(output_dir)
    dataset = load_dataset(dataset_path)
    applied_path = dataset_path / "applied-overrides.json"
    if applied_path.exists():
        dataset["applied_overrides"] = json.loads(applied_path.read_text("utf-8"))
    issues = validate_dataset(dataset)
    if issues:
        codes = ", ".join(issue.code for issue in issues)
        raise ValueError(f"dataset validation failed: {codes}")
    if output.exists():
        raise FileExistsError(f"release output already exists: {output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f".staging-release-{uuid.uuid4().hex}"
    staging.mkdir()
    build_id = dataset["manifest"]["game_build_id"]
    archive_name = f"gw2-wvw-thief-data-{build_id}.zip"
    database_name = f"gw2-wvw-thief-{build_id}.sqlite3"
    try:
        archive_path = staging / archive_name
        database_path = staging / database_name
        _build_zip(dataset_path, archive_path)
        _build_sqlite(dataset, database_path)
        _verify_sqlite_parity(dataset, database_path)
        artifact_records = [
            {"filename": path.name, "sha256": sha256_file(path)}
            for path in sorted((archive_path, database_path), key=lambda path: path.name)
        ]
        manifest_payload = {
            "schema_version": 1,
            "game_build_id": build_id,
            "mode": "wvw",
            "created_from": dataset["manifest"]["fetched_at"],
            "artifacts": artifact_records,
        }
        manifest_errors = schema_errors(
            manifest_payload,
            "release-manifest.schema.json",
        )
        if manifest_errors:
            raise ValueError(
                f"release manifest schema invalid: {manifest_errors[0]}"
            )
        manifest_path = staging / "release-manifest.json"
        write_json(manifest_path, manifest_payload)
        sums_paths = [archive_path, database_path, manifest_path]
        sums = "".join(
            f"{sha256_file(path)}  {path.name}\n"
            for path in sorted(sums_paths, key=lambda path: path.name)
        )
        (staging / "SHA256SUMS").write_text(sums, encoding="ascii", newline="\n")
        staging.replace(output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return ReleaseResult(
        path=output,
        json_archive=output / archive_name,
        sqlite_database=output / database_name,
        manifest=output / "release-manifest.json",
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for release generation."""

    parser = argparse.ArgumentParser(prog="gw2-wvw-data release")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    result = build_release(arguments.dataset, arguments.output)
    print(result.path)
    return 0
