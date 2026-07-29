import httpx
import pytest

from gw2_wvw_data.importers import ImportError
from gw2_wvw_data.importers.http import SafeHttpClient


ALLOWED_HOSTS = frozenset({"en.gw2skills.net"})
EDITOR_URL = "https://en.gw2skills.net/editor/?abc"


class _ExplodingStream(httpx.SyncByteStream):
    def __iter__(self):
        raise AssertionError("encoded response body must not be iterated")


def _html_response(request, *, body=b"<html>ok</html>"):
    return httpx.Response(
        200,
        headers={"content-type": "text/html; charset=utf-8"},
        content=body,
        request=request,
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://en.gw2skills.net/editor/?abc",
        "https://example.com/editor/?abc",
        "https://user:pass@en.gw2skills.net/editor/?abc",
    ],
)
def test_safe_client_rejects_disallowed_urls(url):
    client = SafeHttpClient(
        transport=httpx.MockTransport(lambda request: _html_response(request))
    )

    with pytest.raises(ImportError):
        client.get_text(url, allowed_hosts=ALLOWED_HOSTS)


def test_safe_client_rejects_cross_host_redirect():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            302,
            headers={"location": "https://evil.example/payload"},
            request=request,
        )
    )
    client = SafeHttpClient(transport=transport)

    with pytest.raises(ImportError, match="redirect host"):
        client.get_text(EDITOR_URL, allowed_hosts=ALLOWED_HOSTS)


def test_safe_client_follows_at_most_three_same_host_redirects():
    redirects = {
        "/editor/": "/one",
        "/one": "/two",
        "/two": "/final",
    }

    def handler(request):
        if request.url.path in redirects:
            return httpx.Response(
                302,
                headers={"location": redirects[request.url.path]},
                request=request,
            )
        return _html_response(request)

    document = SafeHttpClient(
        transport=httpx.MockTransport(handler)
    ).get_text(EDITOR_URL, allowed_hosts=ALLOWED_HOSTS)

    assert document.url == "https://en.gw2skills.net/final"
    assert document.text == "<html>ok</html>"


def test_safe_client_rejects_a_fourth_redirect():
    redirects = {
        "/editor/": "/one",
        "/one": "/two",
        "/two": "/three",
        "/three": "/four",
    }

    def handler(request):
        return httpx.Response(
            302,
            headers={"location": redirects[request.url.path]},
            request=request,
        )

    client = SafeHttpClient(transport=httpx.MockTransport(handler))

    with pytest.raises(ImportError, match="redirect limit"):
        client.get_text(EDITOR_URL, allowed_hosts=ALLOWED_HOSTS)


def test_safe_client_requires_html_and_limits_streamed_body():
    wrong_type = SafeHttpClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "application/javascript"},
                content=b"alert(1)",
                request=request,
            )
        )
    )
    too_large = SafeHttpClient(
        transport=httpx.MockTransport(
            lambda request: _html_response(
                request, body=b"x" * (2 * 1024 * 1024 + 1)
            )
        )
    )

    with pytest.raises(ImportError, match="text/html"):
        wrong_type.get_text(EDITOR_URL, allowed_hosts=ALLOWED_HOSTS)
    with pytest.raises(ImportError, match="2 MiB"):
        too_large.get_text(EDITOR_URL, allowed_hosts=ALLOWED_HOSTS)


def test_safe_client_rejects_oversized_urls_before_request():
    calls = []
    client = SafeHttpClient(
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or _html_response(request)
        )
    )

    with pytest.raises(ImportError, match="2,048"):
        client.get_text(
            "https://en.gw2skills.net/editor/?" + "x" * 2_100,
            allowed_hosts=ALLOWED_HOSTS,
        )

    assert calls == []


def test_safe_client_rejects_encoded_body_before_decoding_or_iteration():
    accept_encoding = []

    def handler(request):
        accept_encoding.append(request.headers["accept-encoding"])
        return httpx.Response(
            200,
            headers={
                "content-type": "text/html",
                "content-encoding": "gzip",
            },
            stream=_ExplodingStream(),
            request=request,
        )

    client = SafeHttpClient(transport=httpx.MockTransport(handler))

    with pytest.raises(ImportError, match="Content-Encoding"):
        client.get_text(EDITOR_URL, allowed_hosts=ALLOWED_HOSTS)

    assert accept_encoding == ["identity"]


@pytest.mark.parametrize(
    "url",
    [
        "https://en.gw2skills.net:444/editor/?abc",
        "https://en.gw2skills.net./editor/?abc",
    ],
)
def test_safe_client_rejects_nondefault_port_or_unallowlisted_trailing_dot(url):
    client = SafeHttpClient(
        transport=httpx.MockTransport(lambda request: _html_response(request))
    )

    with pytest.raises(ImportError):
        client.get_text(url, allowed_hosts=ALLOWED_HOSTS)


def test_safe_client_compares_host_case_insensitively():
    client = SafeHttpClient(
        transport=httpx.MockTransport(lambda request: _html_response(request))
    )

    document = client.get_text(
        "https://EN.GW2SKILLS.NET/editor/?abc",
        allowed_hosts=ALLOWED_HOSTS,
    )

    assert document.text == "<html>ok</html>"


def test_safe_client_accepts_trailing_dot_only_when_explicitly_allowlisted():
    client = SafeHttpClient(
        transport=httpx.MockTransport(lambda request: _html_response(request))
    )

    document = client.get_text(
        "https://en.gw2skills.net./editor/?abc",
        allowed_hosts=frozenset({"en.gw2skills.net."}),
    )

    assert document.text == "<html>ok</html>"
