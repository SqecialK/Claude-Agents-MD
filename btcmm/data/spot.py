"""Spot BTC/USD feeds used for pricing, basis measurement and quote pulling.

Each feed is a (url, subscribe-message, parser) triple run through the shared
reconnecting websocket. Parsers are pure functions so they are unit-tested.

Settlement-index proxies:
* Kalshi settles on CF Benchmarks BRTI, which is built from constituent
  exchanges (Coinbase, Kraken, Bitstamp, Gemini, ...). BRTI itself is a
  licensed feed; we record the constituents and build a proxy later, then
  measure basis vs official settlements.
* Polymarket US settles on Chainlink BTC/USD Data Streams, which require
  credentials. If not configured we record its absence explicitly so the
  basis report knows the proxy is a composite, not Chainlink itself.
* Gemini's rule (if point-price on Gemini spot) makes Gemini BTCUSD the
  primary input for Gemini fair value.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from btcmm.adapters.transport import reconnecting_ws
from btcmm.data.models import FeedStatus, SpotTick, utcnow
from btcmm.data.parse import D, D_or_none, parse_ts


def parse_coinbase(m: dict[str, Any]) -> SpotTick | None:
    if m.get("type") != "ticker":
        return None
    return SpotTick(source="coinbase", symbol=m.get("product_id", "BTC-USD"), price=D(m["price"]),
                    bid=D_or_none(m.get("best_bid")), ask=D_or_none(m.get("best_ask")),
                    exchange_ts=parse_ts(m.get("time")), recv_ts=utcnow())


def parse_kraken(m: dict[str, Any]) -> list[SpotTick]:
    if m.get("channel") != "ticker" or m.get("type") not in ("snapshot", "update"):
        return []
    out = []
    for d in m.get("data") or []:
        out.append(SpotTick(source="kraken", symbol=d.get("symbol", "BTC/USD"), price=D(d["last"]),
                            bid=D_or_none(d.get("bid")), ask=D_or_none(d.get("ask")),
                            exchange_ts=parse_ts(d.get("timestamp")), recv_ts=utcnow()))
    return out


def parse_bitstamp(m: dict[str, Any]) -> SpotTick | None:
    if m.get("event") != "trade":
        return None
    d = m.get("data") or {}
    ts = d.get("microtimestamp") or d.get("timestamp")
    return SpotTick(source="bitstamp", symbol="BTCUSD", price=D(d["price"]),
                    exchange_ts=parse_ts(ts), recv_ts=utcnow())


class GeminiSpotParser:
    """Gemini v2 l2 for BTCUSD: maintain top of book, emit mid ticks.
    Stateful because l2_updates are incremental after the first snapshot."""

    def __init__(self) -> None:
        self.bids: dict[Decimal, Decimal] = {}
        self.asks: dict[Decimal, Decimal] = {}

    def reset(self) -> None:
        self.bids.clear()
        self.asks.clear()

    def __call__(self, m: dict[str, Any]) -> list[SpotTick]:
        out: list[SpotTick] = []
        if m.get("type") == "l2_updates":
            for side, p, q in m.get("changes") or []:
                book = self.bids if str(side).lower() == "buy" else self.asks
                pd, qd = D(p), D(q)
                if qd == 0:
                    book.pop(pd, None)
                else:
                    book[pd] = qd
            if self.bids and self.asks:
                b, a = max(self.bids), min(self.asks)
                out.append(SpotTick(source="gemini", symbol="BTCUSD", price=(b + a) / 2, bid=b, ask=a,
                                    exchange_ts=None, recv_ts=utcnow()))
            for t in m.get("trades") or []:
                out.append(SpotTick(source="gemini_trade", symbol="BTCUSD", price=D(t["price"]),
                                    exchange_ts=parse_ts(t.get("timestamp")), recv_ts=utcnow()))
        elif m.get("type") == "trade":
            out.append(SpotTick(source="gemini_trade", symbol="BTCUSD", price=D(m["price"]),
                                exchange_ts=parse_ts(m.get("timestamp")), recv_ts=utcnow()))
        return out


@dataclass
class SpotFeedSpec:
    name: str
    url: str
    subscribe: list[dict[str, Any]]
    parser: Callable[[dict[str, Any]], Any]
    on_reconnect: Callable[[], None] | None = None


def feed_spec(name: str, gemini_ws_url: str = "wss://api.gemini.com/v2/marketdata") -> SpotFeedSpec:
    if name == "coinbase":
        return SpotFeedSpec(name, "wss://ws-feed.exchange.coinbase.com",
                            [{"type": "subscribe", "product_ids": ["BTC-USD"], "channels": ["ticker"]}],
                            parse_coinbase)
    if name == "kraken":
        return SpotFeedSpec(name, "wss://ws.kraken.com/v2",
                            [{"method": "subscribe", "params": {"channel": "ticker", "symbol": ["BTC/USD"]}}],
                            parse_kraken)
    if name == "bitstamp":
        return SpotFeedSpec(name, "wss://ws.bitstamp.net",
                            [{"event": "bts:subscribe", "data": {"channel": "live_trades_btcusd"}}],
                            parse_bitstamp)
    if name == "gemini":
        p = GeminiSpotParser()
        return SpotFeedSpec(name, gemini_ws_url,
                            [{"type": "subscribe", "subscriptions": [{"name": "l2", "symbols": ["BTCUSD"]}]}],
                            p, on_reconnect=p.reset)
    raise ValueError(f"unknown spot feed {name!r}")


async def stream_spot(
    spec: SpotFeedSpec, stop: asyncio.Event, on_status: Callable[[FeedStatus], None] | None = None
) -> AsyncIterator[SpotTick | FeedStatus]:
    def _status(e: str, d: str) -> None:
        if on_status:
            on_status(FeedStatus(source=f"spot:{spec.name}", event=e, detail=d))

    async def on_open(ws: Any) -> None:
        if spec.on_reconnect:
            spec.on_reconnect()
        for sub in spec.subscribe:
            await ws.send(json.dumps(sub))

    async for msg in reconnecting_ws(
        spec.url, name=f"spot:{spec.name}", on_open=on_open, stop=stop,
        on_status=_status,
    ):
        try:
            res = spec.parser(msg)
        except (KeyError, ValueError) as e:
            yield FeedStatus(source=f"spot:{spec.name}", event="error", detail=f"parse: {e}")
            continue
        if res is None:
            continue
        for t in res if isinstance(res, list) else [res]:
            yield t
