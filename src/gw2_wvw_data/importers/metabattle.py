"""Data-only metadata extraction for allowlisted MetaBattle pages."""

from __future__ import annotations

from html.parser import HTMLParser
from types import MappingProxyType
from urllib.parse import urlsplit

from gw2_wvw_data.importers import ImportError
from gw2_wvw_data.importers.community import CommunityCandidate
from gw2_wvw_data.importers.http import HttpDocument


_EDITOR_HOST = "en.gw2skills.net"
_METADATA_ATTRIBUTE_ELEMENTS = frozenset({"dd", "div", "span", "td"})
_VOID_ELEMENTS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)


class MetaBattleAdapter:
    """Extract explicit, minimal metadata without retaining editorial content."""

    source_name = "MetaBattle"

    def extract(self, document: HttpDocument) -> CommunityCandidate:
        """Return only labeled build metadata from one fetched MetaBattle page."""

        collector = _MetadataCollector()
        try:
            collector.feed(document.text)
            collector.close()
            collector.ensure_complete()
        except (ImportError, ValueError) as error:
            raise ImportError("MetaBattle HTML is malformed") from error

        fields = collector.fields
        conflicts: dict[str, tuple[str, ...]] = {}
        title = _single(fields.get("title", ()), "title", conflicts)
        mode = _single(
            (_normalize_mode(value) for value in fields.get("mode", ())),
            "mode",
            conflicts,
        )
        profession = _single(
            (_normalize_profession(value) for value in fields.get("profession", ())),
            "profession",
            conflicts,
        )
        context = _context(fields.get("context", ()), conflicts)
        published_at = _single(fields.get("published", ()), "published", conflicts)
        updated_at = _single(fields.get("updated", ()), "updated", conflicts)
        if (
            title is None
            and "title" not in conflicts
        ):
            raise ImportError("MetaBattle page title is missing")
        if (
            published_at is None
            and updated_at is None
            and "published" not in conflicts
            and "updated" not in conflicts
        ):
            raise ImportError("MetaBattle page date is missing")

        status_label = _single(fields.get("status", ()), "status", conflicts)
        publisher_status = (
            "publisher_claimed_current"
            if status_label is not None and _is_current_claim(status_label)
            else "unverifiable"
        )
        build_code = _single(fields.get("build_code", ()), "Build Code", conflicts)
        editor_urls = _editor_urls(collector.hrefs)
        if len(editor_urls) > 1:
            raise ImportError("MetaBattle page has conflicting editor links")
        if (
            build_code is None
            and not editor_urls
            and "Build Code" not in conflicts
        ):
            raise ImportError("MetaBattle page has no editor or Build Code")

        if mode is None and "mode" not in conflicts:
            raise ImportError("MetaBattle page mode is missing")
        if mode is not None and mode != "wvw":
            raise ImportError("MetaBattle page mode must be wvw")
        if profession is None and "profession" not in conflicts:
            raise ImportError("MetaBattle page profession is missing")
        if profession is not None and profession != "Thief":
            raise ImportError("MetaBattle page profession must be Thief")

        return CommunityCandidate(
            source_name=self.source_name,
            source_url=document.url,
            title=title,
            mode=mode,
            context=context,
            profession=profession,
            published_at=published_at,
            updated_at=updated_at,
            publisher_status=publisher_status,
            publisher_status_label=status_label,
            build_code=build_code,
            editor_urls=editor_urls,
            conflicts=MappingProxyType(conflicts),
        )


class _MetadataCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fields: dict[str, list[str]] = {}
        self.hrefs: list[str] = []
        self._open: list[str] = []
        self._metadata_depths: list[int] = []
        self._label_parts: list[str] | None = None
        self._label_owner_depth: int | None = None
        self._pending_label: str | None = None
        self._value_parts: list[str] | None = None
        self._value_owner_depth: int | None = None
        self._value_field: str | None = None
        self._title_parts: list[str] | None = None
        self._attribute_fields: list[tuple[int, str, list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in _VOID_ELEMENTS:
            self._open.append(tag)
        depth = len(self._open)
        attributes = {name.lower(): value for name, value in attrs}
        if tag == "a" and attributes.get("href"):
            self.hrefs.append(attributes["href"] or "")
        if tag == "title":
            self._title_parts = []
        if tag in {"dl", "table"}:
            self._metadata_depths.append(depth)
        if tag == "dt" and self._metadata_depths:
            self._label_parts = []
            self._label_owner_depth = depth
        elif tag == "dd" and self._metadata_depths:
            self._value_field = _field_name(self._pending_label or "")
            self._value_parts = []
            self._value_owner_depth = depth
            self._pending_label = None
        field = _field_name(attributes.get("data-field") or attributes.get("data-label") or "")
        if (
            field is not None
            and tag in _METADATA_ATTRIBUTE_ELEMENTS
            and self._metadata_depths
        ):
            self._attribute_fields.append((depth, field, []))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            for name, value in attrs:
                if name.lower() == "href" and value:
                    self.hrefs.append(value)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        depth = len(self._open)
        if tag not in _VOID_ELEMENTS:
            if not self._open or self._open[-1] != tag:
                raise ImportError("unbalanced element")
        if tag == "title" and self._title_parts is not None:
            self._add("title", "".join(self._title_parts))
            self._title_parts = None
        elif tag == "dt" and self._label_owner_depth == depth:
            self._pending_label = "".join(self._label_parts)
            self._label_parts = None
            self._label_owner_depth = None
        elif tag == "dd" and self._value_owner_depth == depth:
            if self._value_field is not None:
                self._add(self._value_field, "".join(self._value_parts))
            self._value_parts = None
            self._value_owner_depth = None
            self._value_field = None
        if self._attribute_fields and self._attribute_fields[-1][0] == depth:
            _, field, parts = self._attribute_fields.pop()
            self._add(field, "".join(parts))
        if self._metadata_depths and self._metadata_depths[-1] == depth:
            self._metadata_depths.pop()
        if tag not in _VOID_ELEMENTS:
            self._open.pop()

    def handle_data(self, data: str) -> None:
        if self._title_parts is not None:
            self._title_parts.append(data)
        if self._label_parts is not None:
            self._label_parts.append(data)
        if self._value_parts is not None:
            self._value_parts.append(data)
        for _, _, parts in self._attribute_fields:
            parts.append(data)

    def ensure_complete(self) -> None:
        if (
            self._open
            or self._label_parts is not None
            or self._value_parts is not None
            or self._attribute_fields
        ):
            raise ImportError("unclosed element")

    def _add(self, field: str, value: str) -> None:
        normalized = " ".join(value.split())
        if normalized:
            self.fields.setdefault(field, []).append(normalized)


def _field_name(label: str) -> str | None:
    value = " ".join(label.lower().split())
    if value in {"mode", "game mode"}:
        return "mode"
    if value in {"profession", "class"}:
        return "profession"
    if value in {"context", "role", "wvw context"}:
        return "context"
    if value in {"published", "publication date", "date"}:
        return "published"
    if value in {"updated", "last updated", "last modified"}:
        return "updated"
    if value in {"status", "publisher status", "update status"}:
        return "status"
    if value in {"build code", "build template code"}:
        return "build_code"
    if value == "title":
        return "title"
    return None


def _single(values, field: str, conflicts: dict[str, tuple[str, ...]]) -> str | None:
    unique = tuple(dict.fromkeys(value for value in values if value))
    if len(unique) > 1:
        conflicts[field] = unique
        return None
    return unique[0] if unique else None


def _normalize_mode(value: str) -> str:
    normalized = " ".join(value.lower().split())
    return "wvw" if normalized in {"wvw", "world vs world", "world versus world"} else normalized


def _normalize_profession(value: str) -> str:
    normalized = " ".join(value.split())
    return "Thief" if normalized.lower() == "thief" else normalized


def _context(values: list[str], conflicts: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    unique = tuple(dict.fromkeys(" ".join(value.lower().split()) for value in values if value))
    if len(unique) > 1:
        conflicts["context"] = unique
        return ()
    return (unique[0],) if unique else ()


def _is_current_claim(value: str) -> bool:
    normalized = " ".join(value.lower().split())
    return normalized in {"up to date", "current", "current build"}


def _editor_urls(hrefs: list[str]) -> tuple[str, ...]:
    result = []
    for href in hrefs:
        try:
            parsed = urlsplit(href)
        except ValueError:
            continue
        if (
            parsed.scheme == "https"
            and (parsed.hostname or "").lower() == _EDITOR_HOST
            and parsed.path.rstrip("/") == "/editor"
        ):
            result.append(href)
    return tuple(dict.fromkeys(result))
