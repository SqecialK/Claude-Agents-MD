"""Reusable transport utilities shared by every adapter and spot feed.

Kept in one place so retry/backoff behaviour is fixed once for all venues
(AGENTS.md: "If a fix applies to more than one workflow, it MUST be a tool").
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx
import websockets

log = logging.getLogger(__name__)


def backoff_delay(attempt: int, base: float = 0.5, cap: float = 30.0) -> float:
    """Exponential backoff with full jitter (AWS-style). ``attempt`` is 0-based."""
    return random.uniform(0, min(cap, base * (2**attempt)))


class RestClient:
    """Thin async REST wrapper.

    * GETs are retried with backoff on transport errors / 429 / 5xx.
    * Non-idempotent methods are NEVER auto-retried: an ambiguous order POST
      must be reconciled against open orders before resending (spec, PM US).
    * ``signer`` (optional) returns auth headers for (method, path).
    """

    def __init__(
        self,
        base_url: str,
        *,
        signer: Callable[[str, str], dict[str, str]] | None = None,
        timeout_s: float = 10.0,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.signer = signer
        self.max_retries = max_retries
        self._http = httpx.AsyncClient(timeout=timeout_s)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get(self, path: str, params: dict[str, Any] | None = None, *, auth: bool = False) -> Any:
        url = self.base_url + path
        sign_path = httpx.URL(url).path  # venues sign the path without query string
        attempt = 0
        while True:
            headers = self.signer("GET", sign_path) if (auth and self.signer) else {}
            try:
                r = await self._http.get(url, params=params, headers=headers)
            except httpx.TransportError as e:
                if attempt >= self.max_retries:
                    raise
                log.warning("GET %s transport error %s; retry %d", path, e, attempt + 1)
                await asyncio.sleep(backoff_delay(attempt))
                attempt += 1
                continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                log.warning("GET %s -> %d; retry %d", path, r.status_code, attempt + 1)
                await asyncio.sleep(backoff_delay(attempt, base=1.0))
                attempt += 1
                continue
            r.raise_for_status()
            return r.json() if r.content else {}


async def reconnecting_ws(
    url: str,
    *,
    name: str,
    on_open: Callable[[Any], Awaitable[None]],
    headers_fn: Callable[[], dict[str, str]] | None = None,
    on_status: Callable[[str, str], None] | None = None,
    stop: asyncio.Event | None = None,
    ping_interval: float = 15.0,
) -> AsyncIterator[dict[str, Any]]:
    """Yield decoded JSON messages forever, reconnecting with backoff + jitter.

    ``on_open(ws)`` sends subscriptions after each (re)connect. Consumers MUST
    treat a reconnect as a gap and resnapshot all books - ``on_status`` is
    called with ("connected"|"disconnected", detail) so they can.
    """
    attempt = 0
    stop = stop or asyncio.Event()
    while not stop.is_set():
        try:
            hdrs = headers_fn() if headers_fn else None
            async with websockets.connect(
                url, additional_headers=hdrs, ping_interval=ping_interval, max_size=2**23
            ) as ws:
                attempt = 0
                if on_status:
                    on_status("connected", url)
                await on_open(ws)
                async for raw in ws:
                    if stop.is_set():
                        return
                    try:
                        msg = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        log.warning("%s: undecodable frame dropped", name)
                        continue
                    # Some venues batch several messages in one JSON array.
                    if isinstance(msg, list):
                        for m in msg:
                            if isinstance(m, dict):
                                yield m
                    elif isinstance(msg, dict):
                        yield msg
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - any failure => reconnect
            if on_status:
                on_status("disconnected", f"{type(e).__name__}: {e}")
            delay = backoff_delay(attempt)
            log.warning("%s ws error %r; reconnecting in %.2fs", name, e, delay)
            attempt += 1
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass
        else:
            if on_status:
                on_status("disconnected", "closed by server")
