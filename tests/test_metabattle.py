import json
from pathlib import Path

import httpx
import pytest

from gw2_wvw_data.importers import ImportError
from gw2_wvw_data.importers.community import import_source
from gw2_wvw_data.importers.http import HttpDocument, SafeHttpClient
from gw2_wvw_data.importers.metabattle import MetaBattleAdapter


FIXTURE = Path(__file__).parent / "fixtures" / "importers" / "metabattle-thief.html"
GW2SKILLS_FIXTURE = (
    Path(__file__).parent / "fixtures" / "importers" / "gw2skills-thief.html"
)
CURRENT = Path(__file__).parents[1] / "data" / "normalized" / "current"
URL = "https://metabattle.com/wiki/Build:Thief_-_Deadeye_Roamer"


@pytest.fixture
def dataset():
    return {
        filename: json.loads((CURRENT / f"{filename}.json").read_text("utf-8"))
        for filename in ("profession", "specializations", "traits", "skills")
    }


def _document(html: str | None = None) -> HttpDocument:
    return HttpDocument(url=URL, text=html or FIXTURE.read_text("utf-8"))


def _client(html: str) -> SafeHttpClient:
    return SafeHttpClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                content=html.encode("utf-8"),
                request=request,
            )
        )
    )


def _source_client(metabattle_html: str, gw2skills_html: str) -> SafeHttpClient:
    def respond(request: httpx.Request) -> httpx.Response:
        content = (
            metabattle_html
            if request.url.host in {"metabattle.com", "www.metabattle.com"}
            else gw2skills_html
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=content.encode("utf-8"),
            request=request,
        )

    return SafeHttpClient(transport=httpx.MockTransport(respond))


def test_extracts_only_allowed_metabattle_metadata():
    candidate = MetaBattleAdapter().extract(_document())

    assert candidate.source_name == "MetaBattle"
    assert candidate.mode == "wvw"
    assert candidate.context == ("roaming",)
    assert candidate.profession == "Thief"
    assert candidate.publisher_status == "publisher_claimed_current"
    assert candidate.editor_urls == (
        "https://en.gw2skills.net/editor/"
        "?PaABwihrlNw6YXsNGJm2XnNVA-DyYYhoHLCRoGaXhEYCkZE0bJY7VBaGwyGoC-e",
    )
    assert candidate.guide_text is None
    assert candidate.comments == ()


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("<dt>Updated</dt><dd>2026-07-18</dd>", "", "date"),
        ("<dt>Mode</dt><dd>WvW</dd>", "<dt>Mode</dt><dd>PvE</dd>", "mode"),
        (
            "<dt>Profession</dt><dd>Thief</dd>",
            "<dt>Profession</dt><dd>Mesmer</dd>",
            "profession",
        ),
    ],
)
def test_rejects_required_missing_or_incompatible_metadata(old, new, message):
    html = FIXTURE.read_text("utf-8").replace(old, new)

    with pytest.raises(ImportError, match=message):
        MetaBattleAdapter().extract(_document(html))


def test_rejects_page_without_editor_or_build_code():
    html = (
        FIXTURE.read_text("utf-8")
        .replace(
            "[&DQU2OywnByoKAQAAGQEAAFcBAABYAAAAnwEAAAAAAAAAAAAAAAAAAAAAAAA=]",
            "",
        )
        .replace(
            '<a href="https://en.gw2skills.net/editor/?PaABwihrlNw6YXsNGJm2XnNVA-DyYYhoHLCRoGaXhEYCkZE0bJY7VBaGwyGoC-e">Open editor</a>',
            "",
        )
    )

    with pytest.raises(ImportError, match="editor or Build Code"):
        MetaBattleAdapter().extract(_document(html))


def test_rejects_multiple_conflicting_editor_links():
    html = FIXTURE.read_text("utf-8").replace(
        "</main>",
        (
            '<a href="https://en.gw2skills.net/editor/?different">'
            "Other editor</a></main>"
        ),
    )

    with pytest.raises(ImportError, match="editor"):
        MetaBattleAdapter().extract(_document(html))


def test_records_conflicting_labeled_metadata_without_selecting_a_value():
    html = FIXTURE.read_text("utf-8").replace(
        "</dl>", "<dt>Mode</dt><dd>PvE</dd></dl>"
    )

    candidate = MetaBattleAdapter().extract(_document(html))

    assert candidate.mode is None
    assert candidate.conflicts["mode"] == ("wvw", "pve")


def test_ignores_attribute_labeled_guide_prose_and_keeps_nested_metadata_text():
    html = (
        FIXTURE.read_text("utf-8")
        .replace(
            "<dt>Context</dt><dd>Roaming</dd>",
            (
                '<dt>Context</dt><dd><div data-field="context">'
                "<span>Roaming</span> and dueling</div></dd>"
            ),
        )
        .replace(
            "</main>",
            '<p data-label="Profession">Mesmer guide prose</p></main>',
        )
        .replace(
            "</dl>",
            '<p data-label="Profession">More Mesmer guide prose</p></dl>',
        )
    )

    candidate = MetaBattleAdapter().extract(_document(html))

    assert candidate.profession == "Thief"
    assert candidate.context == ("roaming and dueling",)


def test_ignores_labeled_elements_inside_ordinary_guide_structures():
    html = FIXTURE.read_text("utf-8").replace(
        "</main>",
        (
            '<dl><dt>Profession</dt><dd>Mesmer guide prose</dd>'
            '<div data-field="profession"><span>Mesmer</span></div></dl>'
            '<table><tr><td data-label="context">zerg guide prose</td></tr></table>'
            "</main>"
        ),
    )

    candidate = MetaBattleAdapter().extract(_document(html))

    assert candidate.profession == "Thief"
    assert candidate.context == ("roaming",)


def test_with_conflict_keeps_conflicts_read_only():
    candidate = MetaBattleAdapter().extract(_document()).with_conflict(
        "configuration", ("traits",)
    )

    with pytest.raises(TypeError):
        candidate.conflicts["configuration"] = ("skills",)


@pytest.mark.parametrize(
    ("old", "new", "field", "attribute"),
    [
        (
            "<title>WvW Deadeye Roamer - MetaBattle</title>",
            (
                "<title>WvW Deadeye Roamer - MetaBattle</title>"
                "<title>Other title</title>"
            ),
            "title",
            "title",
        ),
        (
            "</dl>",
            "<dt>Updated</dt><dd>2026-07-19</dd></dl>",
            "updated",
            "updated_at",
        ),
        (
            "</dl>",
            (
                "<dt>Build Code</dt>"
                "<dd>[&DQU2KywnBzkKAQAAGQEAAFgAAABXAQAAnwEAAAAAAAAAAAAAAAAAAAAAAAAEBQA2AFoALwAA]</dd></dl>"
            ),
            "Build Code",
            "build_code",
        ),
    ],
)
def test_preserves_conflicting_required_metadata_without_selecting_a_value(
    old, new, field, attribute
):
    html = FIXTURE.read_text("utf-8").replace(old, new)

    candidate = MetaBattleAdapter().extract(_document(html))

    assert getattr(candidate, attribute) is None
    assert candidate.conflicts[field]


def test_dispatcher_uses_editor_configuration_when_dual_sources_agree(dataset):
    candidate = import_source(
        URL,
        dataset=dataset,
        client=_source_client(
            FIXTURE.read_text("utf-8"), GW2SKILLS_FIXTURE.read_text("utf-8")
        ),
    )

    assert candidate.build is not None
    assert candidate.build.armor["helm"].id == "gw2skills:300"
    assert [source["source"] for source in candidate.build.provenance["sources"]] == [
        "build-code",
        "gw2skills",
    ]


def test_dispatcher_records_dual_source_configuration_disagreement(dataset):
    conflicting_editor = GW2SKILLS_FIXTURE.read_text("utf-8").replace(
        "DQU2OywnByoKAQAAGQEAAFcBAABYAAAAnwEAAAAAAAAAAAAAAAAAAAAAAAA=",
        "DQU2KywnBzkKAQAAGQEAAFgAAABXAQAAnwEAAAAAAAAAAAAAAAAAAAAAAAAEBQA2AFoALwAA",
    )

    candidate = import_source(
        URL,
        dataset=dataset,
        client=_source_client(FIXTURE.read_text("utf-8"), conflicting_editor),
    )

    assert candidate.build is None
    assert candidate.conflicts["configuration"] == ("traits", "skills")


def test_rejects_malformed_html():
    with pytest.raises(ImportError, match="malformed"):
        MetaBattleAdapter().extract(_document("<main><dt>Mode</dt><dd>WvW"))


@pytest.mark.parametrize(
    "url",
    [
        "https://snowcrows.com/builds/thief/",
        "https://gw2mists.com/builds/thief/",
    ],
)
def test_dispatcher_rejects_unsupported_sources_before_network_access(url, dataset):
    def fail_if_called(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dispatcher attempted an unsupported request")

    client = SafeHttpClient(transport=httpx.MockTransport(fail_if_called))

    with pytest.raises(ImportError, match="^unsupported source adapter$"):
        import_source(url, dataset=dataset, client=client)


def test_dispatcher_fetches_and_extracts_supported_source(dataset):
    candidate = import_source(
        URL,
        dataset=dataset,
        client=_source_client(
            FIXTURE.read_text("utf-8"), GW2SKILLS_FIXTURE.read_text("utf-8")
        ),
    )

    assert candidate.source_url == URL
    assert candidate.build_code == "[&DQU2OywnByoKAQAAGQEAAFcBAABYAAAAnwEAAAAAAAAAAAAAAAAAAAAAAAA=]"
