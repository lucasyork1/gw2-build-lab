"""Bounded HTTP access for allowlisted build-source pages."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from gw2_wvw_data.importers import ImportError


_MAX_URL_LENGTH = 2_048
_MAX_BODY_BYTES = 2 * 1024 * 1024
_MAX_REDIRECTS = 3


@dataclass(frozen=True)
class HttpDocument:
    """One successfully fetched HTML document."""

    url: str
    text: str


class SafeHttpClient:
    """Fetch HTML without following requests outside an explicit host boundary."""

    def __init__(self, *, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(
            follow_redirects=False,
            timeout=10.0,
            transport=transport,
        )

    def get_text(
        self,
        url: str,
        *,
        allowed_hosts: frozenset[str],
    ) -> HttpDocument:
        """Fetch an allowlisted HTTPS page with bounded redirects and body size."""

        original_host = self._validate_url(url, allowed_hosts=allowed_hosts)
        current_url = url
        redirects = 0
        self._client.cookies.clear()
        try:
            while True:
                with self._client.stream(
                    "GET",
                    current_url,
                    headers={"accept": "text/html"},
                ) as response:
                    if response.is_redirect:
                        if redirects >= _MAX_REDIRECTS:
                            raise ImportError("HTTP redirect limit exceeded")
                        location = response.headers.get("location")
                        if not location:
                            raise ImportError("HTTP redirect is missing a location")
                        next_url = urljoin(str(response.url), location)
                        try:
                            redirect_host = self._validate_url(
                                next_url, allowed_hosts=allowed_hosts
                            )
                        except ImportError as error:
                            try:
                                candidate_host = (
                                    urlsplit(next_url).hostname or ""
                                ).rstrip(".").lower()
                            except ValueError:
                                candidate_host = ""
                            if candidate_host != original_host:
                                raise ImportError(
                                    "HTTP redirect host changed"
                                ) from error
                            raise
                        if redirect_host != original_host:
                            raise ImportError("HTTP redirect host changed")
                        redirects += 1
                        current_url = next_url
                        self._client.cookies.clear()
                        continue

                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as error:
                        raise ImportError(
                            f"HTTP request failed with status {response.status_code}"
                        ) from error
                    content_type = response.headers.get("content-type", "")
                    media_type = content_type.partition(";")[0].strip().lower()
                    if media_type != "text/html":
                        raise ImportError("HTTP response must use text/html")
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > _MAX_BODY_BYTES:
                            raise ImportError("HTTP response exceeds 2 MiB")
                    try:
                        text = bytes(content).decode(response.encoding or "utf-8")
                    except (LookupError, UnicodeError) as error:
                        raise ImportError("HTTP response has invalid text encoding") from error
                    return HttpDocument(url=str(response.url), text=text)
        except httpx.HTTPError as error:
            raise ImportError("HTTP request failed") from error
        finally:
            self._client.cookies.clear()

    @staticmethod
    def _validate_url(url: str, *, allowed_hosts: frozenset[str]) -> str:
        if not isinstance(url, str) or not url:
            raise ImportError("URL must be a non-empty string")
        if len(url) > _MAX_URL_LENGTH:
            raise ImportError("URL exceeds 2,048 characters")
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError as error:
            raise ImportError("URL is malformed") from error
        if parsed.scheme.lower() != "https":
            raise ImportError("URL must use HTTPS")
        if parsed.username is not None or parsed.password is not None:
            raise ImportError("URL credentials are not allowed")
        if port not in (None, 443):
            raise ImportError("URL must use the default HTTPS port")
        host = (parsed.hostname or "").rstrip(".").lower()
        normalized_hosts = {value.rstrip(".").lower() for value in allowed_hosts}
        if not host or host not in normalized_hosts:
            raise ImportError("URL host is not allowlisted")
        return host
