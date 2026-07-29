"""Small, defensive client for the public ArenaNet API."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx


class ArenaNetAPIError(RuntimeError):
    """Raised when the ArenaNet API cannot produce a safe JSON result."""


class ArenaNetClient:
    """HTTP client with bounded retries and response validation."""

    BASE_URL = "https://api.guildwars2.com"
    RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_response_bytes: int = 100 * 1024 * 1024,
    ) -> None:
        self._sleep = sleep
        self._max_response_bytes = max_response_bytes
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            timeout=httpx.Timeout(connect=10, read=60, write=60, pool=10),
            headers={
                "accept": "application/json",
                "user-agent": (
                    "gw2-wvw-thief-data/0.1 "
                    "(+https://github.com/lucasyork1/gw2-build-lab)"
                ),
            },
            transport=transport,
        )

    def get_json(
        self,
        path: str,
        params: Mapping[str, str] | None = None,
    ) -> Any:
        """Fetch one JSON resource, retrying transient failures three times."""

        response: httpx.Response | None = None
        for attempt in range(4):
            try:
                response = self._client.get(path, params=params)
            except httpx.RequestError as error:
                if attempt == 3:
                    raise ArenaNetAPIError(f"request failed for {path}: {error}") from error
                self._sleep(2**attempt)
                continue
            if response.status_code not in self.RETRY_STATUSES:
                break
            if attempt == 3:
                break
            self._sleep(2**attempt)

        if response is None:
            raise ArenaNetAPIError(f"request produced no response for {path}")
        if response.status_code >= 400:
            raise ArenaNetAPIError(
                f"ArenaNet API returned HTTP {response.status_code} for {path}"
            )
        if len(response.content) > self._max_response_bytes:
            raise ArenaNetAPIError(f"response exceeds size limit for {path}")
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type.lower():
            raise ArenaNetAPIError(f"ArenaNet API did not return JSON for {path}")
        try:
            return response.json()
        except ValueError as error:
            raise ArenaNetAPIError(f"ArenaNet API returned invalid JSON for {path}") from error

    def close(self) -> None:
        """Close the underlying connection pool."""

        self._client.close()

    def __enter__(self) -> ArenaNetClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
