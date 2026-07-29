"""CLI orchestration for deterministic build import, analysis, and comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import tomllib
from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

from gw2_wvw_data.analysis import (
    BuildAnalysis,
    analyze_build,
    compare_builds,
    load_rules,
)
from gw2_wvw_data.audit import (
    BuildAudit,
    DatasetIndex,
    PatchEvent,
    audit_build,
)
from gw2_wvw_data.builds.model import BuildRecord
from gw2_wvw_data.builds.report import (
    render_comparison_markdown,
    render_markdown,
)
from gw2_wvw_data.builds.store import load_build
from gw2_wvw_data.contracts import schema_errors
from gw2_wvw_data.decoders import decode_build_code
from gw2_wvw_data.importers.community import (
    CommunityCandidate,
    import_source,
)
from gw2_wvw_data.importers.gw2skills import import_gw2skills
from gw2_wvw_data.importers.http import SafeHttpClient
from gw2_wvw_data.io import canonical_json_bytes, write_json
from gw2_wvw_data.overrides import load_dataset


_DEFAULT_RULES = (
    files("gw2_wvw_data")
    .joinpath("data")
    .joinpath("analysis-rules")
    .joinpath("thief-wvw-v1.json")
)
_RFC3339_DATETIME = re.compile(
    r"\d{4}-\d{2}-\d{2}T"
    r"\d{2}:\d{2}:\d{2}(?:\.\d+)?"
    r"(?:Z|[+-]\d{2}:\d{2})\Z"
)
_PROJECT_NAME = "gw2-wvw-thief-data"


@dataclass(frozen=True)
class AnalysisBundle:
    """Canonical input and its deterministic audit and analysis outputs."""

    build: BuildRecord
    audit: BuildAudit
    analysis: BuildAnalysis

    def to_dict(self) -> dict[str, Any]:
        return {
            "build": self.build.to_dict(),
            "audit": self.audit.to_dict(),
            "analysis": self.analysis.to_dict(),
        }


def analyze_input(
    *,
    build_code: str | None,
    gw2skills_url: str | None,
    dataset_path: Path,
    rules_path: Path,
    client: SafeHttpClient | None = None,
) -> AnalysisBundle:
    """Canonicalize one supported input, then audit and analyze it."""

    if (build_code is None) == (gw2skills_url is None):
        raise ValueError(
            "exactly one of build_code and gw2skills_url is required"
        )
    dataset = load_dataset(dataset_path)
    if build_code is not None:
        build = decode_build_code(build_code, dataset=dataset)
    else:
        build = import_gw2skills(
            gw2skills_url,
            dataset=dataset,
            client=client or SafeHttpClient(),
        )
    index = DatasetIndex.from_dataset(dataset)
    audit = audit_build(
        build,
        index=index,
        patch_events=_load_patch_events(dataset_path),
        checked_at=_checked_at(dataset),
    )
    _require_public_schema(
        audit.to_dict(),
        "build-audit.schema.json",
        "build audit",
    )
    analysis = analyze_build(
        build,
        audit,
        index=index,
        rules=load_rules(rules_path),
    )
    _require_public_schema(
        analysis.to_dict(),
        "build-analysis.schema.json",
        "build analysis",
    )
    return AnalysisBundle(build=build, audit=audit, analysis=analysis)


def build_parser() -> argparse.ArgumentParser:
    """Build the shared parser whose first argument is the operation."""

    parser = argparse.ArgumentParser(prog="gw2-wvw-data")
    subparsers = parser.add_subparsers(dest="operation", required=True)

    analyze = subparsers.add_parser("analyze")
    inputs = analyze.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--build-code")
    inputs.add_argument("--gw2skills-url")
    analyze.add_argument("--dataset", type=Path, required=True)
    analyze.add_argument("--rules", type=Path)
    analyze.add_argument("--json", type=Path, required=True)
    analyze.add_argument("--markdown", type=Path, required=True)

    source = subparsers.add_parser("import-source")
    source.add_argument("url")
    source.add_argument("--dataset", type=Path, required=True)
    source.add_argument("--candidate-dir", type=Path, required=True)

    compare = subparsers.add_parser("compare")
    compare.add_argument("left", type=Path)
    compare.add_argument("right", type=Path)
    compare.add_argument("--json", type=Path, required=True)
    compare.add_argument("--markdown", type=Path, required=True)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    client: SafeHttpClient | None = None,
) -> int:
    """Run the operation named by the first argument."""

    arguments = build_parser().parse_args(argv)
    if arguments.operation == "analyze":
        rules_context = (
            nullcontext(arguments.rules)
            if arguments.rules is not None
            else as_file(_DEFAULT_RULES)
        )
        with rules_context as rules_path:
            bundle = analyze_input(
                build_code=arguments.build_code,
                gw2skills_url=arguments.gw2skills_url,
                dataset_path=arguments.dataset,
                rules_path=rules_path,
                client=client,
            )
        json_bytes = canonical_json_bytes(bundle.to_dict())
        markdown_bytes = render_markdown(
            bundle.build, bundle.audit, bundle.analysis
        ).encode("utf-8")
        _write_output_pair(
            arguments.json,
            json_bytes,
            arguments.markdown,
            markdown_bytes,
        )
        return 0
    if arguments.operation == "import-source":
        candidate_dir = _candidate_import_directory(
            arguments.candidate_dir,
            dataset_path=arguments.dataset,
        )
        dataset = load_dataset(arguments.dataset)
        candidate = import_source(
            arguments.url,
            dataset=dataset,
            client=client or SafeHttpClient(),
        )
        identifier = hashlib.sha256(
            candidate.source_url.encode("utf-8")
        ).hexdigest()
        write_json(
            candidate_dir / f"candidate-{identifier}.json",
            _candidate_dict(candidate),
        )
        return 0
    if arguments.operation == "compare":
        comparison = compare_builds(
            load_build(arguments.left), load_build(arguments.right)
        )
        _write_output_pair(
            arguments.json,
            canonical_json_bytes(comparison.to_dict()),
            arguments.markdown,
            render_comparison_markdown(comparison).encode("utf-8"),
        )
        return 0
    raise AssertionError(f"unhandled operation: {arguments.operation}")


def _checked_at(dataset: Mapping[str, Any]) -> str:
    manifest = dataset.get("manifest")
    checked_at = (
        manifest.get("fetched_at") if isinstance(manifest, Mapping) else None
    )
    if not isinstance(checked_at, str) or not _RFC3339_DATETIME.fullmatch(
        checked_at
    ):
        raise ValueError(
            "dataset manifest fetched_at must be a timezone-aware RFC 3339 "
            "date-time"
        )
    try:
        parsed = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            "dataset manifest fetched_at must be a timezone-aware RFC 3339 "
            "date-time"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            "dataset manifest fetched_at must be a timezone-aware RFC 3339 "
            "date-time"
        )
    return checked_at


def _require_public_schema(
    value: Mapping[str, Any],
    schema_name: str,
    label: str,
) -> None:
    errors = schema_errors(value, schema_name)
    if errors:
        raise ValueError(f"{label} schema invalid: {errors[0]}")


def _load_patch_events(dataset_path: Path) -> tuple[PatchEvent, ...]:
    source = dataset_path / "patch-events.json"
    if not source.exists():
        return ()
    try:
        value = json.loads(source.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"patch events are unreadable: {error}") from error
    if not isinstance(value, list):
        raise ValueError("patch events must be a JSON array")
    return tuple(PatchEvent.from_dict(item) for item in value)


def _candidate_dict(candidate: CommunityCandidate) -> dict[str, Any]:
    return {
        "source_name": candidate.source_name,
        "source_url": candidate.source_url,
        "title": candidate.title,
        "mode": candidate.mode,
        "context": list(candidate.context),
        "profession": candidate.profession,
        "published_at": candidate.published_at,
        "updated_at": candidate.updated_at,
        "publisher_status": candidate.publisher_status,
        "publisher_status_label": candidate.publisher_status_label,
        "build_code": candidate.build_code,
        "editor_urls": list(candidate.editor_urls),
        "conflicts": {
            key: list(value)
            for key, value in sorted(candidate.conflicts.items())
        },
        "guide_text": candidate.guide_text,
        "comments": list(candidate.comments),
        "build": (
            candidate.build.to_dict()
            if candidate.build is not None
            else None
        ),
    }


def _candidate_import_directory(
    path: Path,
    *,
    dataset_path: Path,
) -> Path:
    """Resolve an import target without crossing the review boundary."""

    candidate = path.resolve(strict=False)
    candidate_key = os.path.normcase(os.fspath(candidate))
    for root in _gw2_repository_roots(dataset_path):
        protected = root / "data" / "community-builds" / "verified"
        protected_key = os.path.normcase(
            os.fspath(protected.resolve(strict=False))
        )
        try:
            within_verified = (
                os.path.commonpath((candidate_key, protected_key))
                == protected_key
            )
        except ValueError:
            within_verified = False
        if within_verified:
            raise ValueError(
                "candidate directory cannot be verified data or its "
                "descendants"
            )
    return candidate


def _gw2_repository_roots(dataset_path: Path) -> tuple[Path, ...]:
    roots: dict[str, Path] = {}
    for start in (
        Path(__file__).resolve(),
        dataset_path.resolve(strict=False),
    ):
        for root in (start, *start.parents):
            pyproject = root / "pyproject.toml"
            if not pyproject.is_file():
                continue
            try:
                value = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError):
                continue
            project = value.get("project")
            if (
                isinstance(project, Mapping)
                and project.get("name") == _PROJECT_NAME
            ):
                resolved = root.resolve(strict=True)
                roots[os.path.normcase(os.fspath(resolved))] = resolved
                break
    return tuple(roots[key] for key in sorted(roots))


def _write_output_pair(
    json_path: Path,
    json_bytes: bytes,
    markdown_path: Path,
    markdown_bytes: bytes,
) -> None:
    _preflight_output_pair(json_path, markdown_path)
    staged: list[tuple[Path, Path]] = []
    backups: list[tuple[Path, Path | None]] = []
    retained_backups: set[Path] = set()
    replacement_started = False
    try:
        staged.append((_stage_bytes(json_path, json_bytes), json_path))
        staged.append(
            (_stage_bytes(markdown_path, markdown_bytes), markdown_path)
        )
        for _, destination in staged:
            backups.append(
                (destination, _backup_destination(destination))
            )
        replacement_started = True
        for temporary, destination in staged:
            temporary.replace(destination)
    except BaseException as error:
        if replacement_started:
            rollback_errors, retained_backups = _restore_destinations(
                backups
            )
            if rollback_errors:
                evidence = (
                    " Recovery backups retained: "
                    + ", ".join(
                        str(path) for path in sorted(retained_backups)
                    )
                    if retained_backups
                    else ""
                )
                raise RuntimeError(
                    "output replacement failed and rollback was incomplete: "
                    + "; ".join(rollback_errors)
                    + evidence
                ) from error
        raise
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
        for _, backup in backups:
            if backup is not None and backup not in retained_backups:
                backup.unlink(missing_ok=True)


def _preflight_output_pair(json_path: Path, markdown_path: Path) -> None:
    resolved = (json_path.resolve(), markdown_path.resolve())
    if (
        resolved[0] == resolved[1]
        or resolved[0] in resolved[1].parents
        or resolved[1] in resolved[0].parents
        or (
            json_path.exists()
            and markdown_path.exists()
            and json_path.samefile(markdown_path)
        )
    ):
        raise ValueError("JSON and Markdown outputs must use different paths")
    for destination in (json_path, markdown_path):
        if destination.exists() and not destination.is_file():
            raise ValueError(
                f"output destination is a directory: {destination}"
            )
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ValueError(
                f"output parent directory is invalid: {destination.parent}"
            ) from error
        if not destination.parent.is_dir():
            raise ValueError(
                f"output parent directory is invalid: {destination.parent}"
            )


def _backup_destination(destination: Path) -> Path | None:
    if not destination.exists():
        return None
    return _stage_bytes(
        destination,
        destination.read_bytes(),
        purpose="backup",
    )


def _restore_destinations(
    backups: list[tuple[Path, Path | None]],
) -> tuple[list[str], set[Path]]:
    errors = []
    retained_backups: set[Path] = set()
    for destination, backup in backups:
        try:
            if backup is None:
                destination.unlink(missing_ok=True)
            else:
                backup.replace(destination)
        except OSError as error:
            if backup is not None and backup.exists():
                retained_backups.add(backup)
                errors.append(
                    f"{destination}: {error}; old content remains at {backup}"
                )
            else:
                errors.append(f"{destination}: {error}")
    return errors, retained_backups


def _stage_bytes(
    destination: Path,
    value: bytes,
    *,
    purpose: str | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    marker = f"{purpose}." if purpose else ""
    descriptor, name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.{marker}",
        suffix=".tmp",
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


if __name__ == "__main__":
    raise SystemExit(main())
