"""Shared HTTP session with connection pooling and retry logic.

All model adapters use this instead of creating their own httpx clients.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# HTTP status codes that should trigger a retry
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# Default retry configuration
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BASE_DELAY = 1.0  # seconds
_DEFAULT_MAX_DELAY = 30.0  # seconds


class HttpSession:
    """Reusable HTTP client with connection pooling and automatic retry.

    Usage::

        session = HttpSession(timeout=120.0)
        data = await session.post_json(url, payload, headers)
        await session.close()

    Or as an async context manager::

        async with HttpSession() as session:
            data = await session.post_json(url, payload, headers)
    """

    def __init__(
        self,
        timeout: float = 120.0,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        base_delay: float = _DEFAULT_BASE_DELAY,
        max_delay: float = _DEFAULT_MAX_DELAY,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> HttpSession:
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def post_json(
        self,
        url: str,
        json_data: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """POST JSON with automatic retry on transient errors.

        Returns the parsed JSON response body.

        Raises:
            httpx.HTTPStatusError: If the request fails after all retries.
            RuntimeError: If retry-after header indicates too long a wait.
        """
        client = self._get_client()
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = await client.post(url, json=json_data, headers=headers)

                if response.status_code in _RETRYABLE_STATUS:
                    delay = self._calculate_delay(attempt, response)
                    logger.warning(
                        "HTTP %d from %s (attempt %d/%d), retrying in %.1fs",
                        response.status_code,
                        url,
                        attempt + 1,
                        self._max_retries + 1,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                response.raise_for_status()
                return response.json()

            except httpx.TimeoutException as e:
                last_error = e
                delay = self._calculate_delay(attempt)
                logger.warning(
                    "Timeout on %s (attempt %d/%d), retrying in %.1fs",
                    url,
                    attempt + 1,
                    self._max_retries + 1,
                    delay,
                )
                await asyncio.sleep(delay)

            except httpx.ConnectError as e:
                last_error = e
                delay = self._calculate_delay(attempt)
                logger.warning(
                    "Connection error on %s (attempt %d/%d), retrying in %.1fs",
                    url,
                    attempt + 1,
                    self._max_retries + 1,
                    delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Request to {url} failed after {self._max_retries + 1} attempts: {last_error}"
        )

    def _calculate_delay(self, attempt: int, response: httpx.Response | None = None) -> float:
        """Calculate retry delay with exponential backoff.

        Respects Retry-After header from 429 responses.
        """
        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    return min(float(retry_after), self._max_delay)
                except ValueError:
                    pass

        delay = self._base_delay * (2**attempt)
        return min(delay, self._max_delay)
