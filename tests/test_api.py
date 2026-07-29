import httpx
import pytest

from gw2_wvw_data.api import ArenaNetAPIError, ArenaNetClient


def test_client_retries_rate_limit_then_returns_json():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, request=request)
        return httpx.Response(200, json={"id": 204132}, request=request)

    client = ArenaNetClient(
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
    )

    assert client.get_json("/v2/build") == {"id": 204132}
    assert calls == 2


def test_client_does_not_retry_not_found():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(404, request=request)

    client = ArenaNetClient(
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
    )

    with pytest.raises(ArenaNetAPIError, match="404"):
        client.get_json("/v2/missing")
    assert calls == 1


def test_client_rejects_non_json_response():
    def handler(request):
        return httpx.Response(
            200,
            text="<html>maintenance</html>",
            headers={"content-type": "text/html"},
            request=request,
        )

    client = ArenaNetClient(transport=httpx.MockTransport(handler))

    with pytest.raises(ArenaNetAPIError, match="JSON"):
        client.get_json("/v2/build")
