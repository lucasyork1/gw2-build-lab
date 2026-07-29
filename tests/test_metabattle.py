import json
from pathlib import Path

import httpx
import pytest

from gw2_wvw_data.importers import ImportError
from gw2_wvw_data.importers.community import import_source
from gw2_wvw_data.importers.http import HttpDocument, SafeHttpClient
from gw2_wvw_data.importers.metabattle import MetaBattleAdapter


FIXTURE = Path(__file__).parent / "fixtures" / "importers" / "metabattle-thief.html"
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
        client=_client(FIXTURE.read_text("utf-8")),
    )

    assert candidate.source_url == URL
    assert candidate.build_code == "[&DQU2OywnByoKAQAAGQEAAFcBAABYAAAAnwEAAAAAAAAAAAAAAAAAAAAAAAA=]"
