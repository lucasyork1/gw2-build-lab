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
    title: str
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
    if candidate.build_code is not None:
        try:
            return candidate.with_build(
                decode_build_code(candidate.build_code, dataset=dataset)
            )
        except (BuildCodeError, ValueError) as error:
            raise ImportError("MetaBattle Build Code is invalid") from error
    if candidate.editor_urls:
        return candidate.with_build(
            import_gw2skills(candidate.editor_urls[0], dataset=dataset, client=client)
        )
    raise ImportError("MetaBattle page has no editor or Build Code")

