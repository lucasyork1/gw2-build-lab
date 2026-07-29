"""Controlled import dispatch for community build pages."""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import urlsplit

from gw2_wvw_data.builds.model import BuildRecord
from gw2_wvw_data.decoders.build_code import BuildCodeError, decode_build_code
from gw2_wvw_data.importers import ImportError
from gw2_wvw_data.importers.gw2skills import import_gw2skills
from gw2_wvw_data.importers.http import SafeHttpClient


@dataclass(frozen=True)
class CommunityCandidate:
    """Minimal, non-prose metadata extracted from an allowlisted source page."""

    source_name: str
    source_url: str
    title: str | None
    mode: str | None
    context: tuple[str, ...]
    profession: str | None
    published_at: str | None
    updated_at: str | None
    publisher_status: str | None
    publisher_status_label: str | None
    build_code: str | None
    editor_urls: tuple[str, ...]
    conflicts: Mapping[str, tuple[str, ...]]
    guide_text: None = None
    comments: tuple[()] = ()
    build: BuildRecord | None = None

    def with_build(self, build: BuildRecord) -> CommunityCandidate:
        """Return this candidate with an independently decoded configuration."""

        return replace(self, build=build)

    def with_conflict(
        self, field: str, values: tuple[str, ...]
    ) -> CommunityCandidate:
        """Return this candidate with an unresolved source disagreement."""

        return replace(
            self,
            conflicts=MappingProxyType({**self.conflicts, field: values}),
        )


_METABATTLE_HOSTS = frozenset({"metabattle.com", "www.metabattle.com"})


def import_source(
    url: str,
    *,
    dataset: Mapping[str, Any],
    client: SafeHttpClient,
) -> CommunityCandidate:
    """Fetch only a supported source and decode its explicit configuration."""

    try:
        host = (urlsplit(url).hostname or "").lower()
    except (TypeError, ValueError):
        host = ""
    if host not in _METABATTLE_HOSTS:
        raise ImportError("unsupported source adapter")

    from gw2_wvw_data.importers.metabattle import MetaBattleAdapter

    document = client.get_text(url, allowed_hosts=_METABATTLE_HOSTS)
    candidate = MetaBattleAdapter().extract(document)
    decoded_build: BuildRecord | None = None
    editor_build: BuildRecord | None = None
    if candidate.build_code is not None:
        try:
            decoded_build = decode_build_code(candidate.build_code, dataset=dataset)
        except (BuildCodeError, ValueError) as error:
            raise ImportError("MetaBattle Build Code is invalid") from error
    if candidate.editor_urls:
        editor_build = (
            import_gw2skills(candidate.editor_urls[0], dataset=dataset, client=client)
        )
    if decoded_build is not None and editor_build is not None:
        differences = _overlapping_configuration_differences(
            decoded_build, editor_build
        )
        if differences:
            return candidate.with_conflict("configuration", differences)
        return candidate.with_build(
            _with_candidate_metadata(editor_build, candidate)
        )
    if editor_build is not None:
        return candidate.with_build(
            _with_candidate_metadata(editor_build, candidate)
        )
    if decoded_build is not None:
        return candidate.with_build(
            _with_candidate_metadata(decoded_build, candidate)
        )
    return candidate


def _with_candidate_metadata(
    build: BuildRecord,
    candidate: CommunityCandidate,
) -> BuildRecord:
    """Derive a canonical record that retains source-page metadata."""

    value = build.to_dict()
    source_id = candidate.source_name.lower()
    source = {
        "source": source_id,
        "source_name": candidate.source_name,
        "url": candidate.source_url,
    }
    for field, field_value in (
        ("title", candidate.title),
        ("mode", candidate.mode),
        ("profession", candidate.profession),
        ("published_at", candidate.published_at),
        ("updated_at", candidate.updated_at),
        ("publisher_status", candidate.publisher_status),
        ("publisher_status_label", candidate.publisher_status_label),
    ):
        if field_value is not None:
            source[field] = field_value

    provenance = value["provenance"]
    provenance["sources"].append(source)
    fields = provenance["fields"]
    if candidate.context:
        if build.context and build.context != candidate.context:
            provenance["conflicts"].append(
                {
                    "field": "context",
                    "source": source_id,
                    "values": [
                        list(build.context),
                        list(candidate.context),
                    ],
                }
            )
        else:
            value["context"] = list(candidate.context)
            fields["context"] = {"source": source_id}
    for field in sorted(candidate.conflicts):
        provenance["conflicts"].append(
            {
                "field": field,
                "source": source_id,
                "values": list(candidate.conflicts[field]),
            }
        )

    if candidate.publisher_status == "publisher_claimed_current":
        value["version_audit"]["status"] = "publisher_claimed_current"
        fields["version_audit.status"] = {"source": source_id}
    return BuildRecord.from_dict(value)


def _overlapping_configuration_differences(
    build_code: BuildRecord, editor: BuildRecord
) -> tuple[str, ...]:
    differences = []
    if tuple(item.id for item in build_code.specializations) != tuple(
        item.id for item in editor.specializations
    ):
        differences.append("specializations")
    if tuple(item.id for item in build_code.traits) != tuple(
        item.id for item in editor.traits
    ):
        differences.append("traits")
    if _skill_ids(build_code) != _skill_ids(editor):
        differences.append("skills")
    return tuple(differences)


def _skill_ids(build: BuildRecord) -> tuple[int | str | None, ...]:
    skills = build.skills
    heal = skills["heal"]
    utilities = skills["utilities"]
    elite = skills["elite"]
    return (
        heal.id if heal is not None else None,
        *(item.id if item is not None else None for item in utilities),
        elite.id if elite is not None else None,
    )
