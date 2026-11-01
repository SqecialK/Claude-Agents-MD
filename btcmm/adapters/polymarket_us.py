"""Polymarket US adapter (read-only in Phase 1).

Verified against the official ``polymarket-us`` SDK (v2.4.1) source:
* Two hosts: public gateway ``https://gateway.polymarket.us`` (unauthenticated
  reads) and ``https://api.polymarket.us`` (authenticated).
* Auth headers X-PM-Access-Key / X-PM-Timestamp / X-PM-Signature, Ed25519
  over ``timestamp_ms + METHOD + path``; secret is a base64 32- or 64-byte key.
* Websockets ``/v1/ws/markets`` and ``/v1/ws/private`` BOTH require auth
  headers - market data is not anonymous. Without keys we poll the public
  REST book.
* Each market (slug) has ONE book. Orders carry an intent:
  BUY_LONG / SELL_LONG / BUY_SHORT / SELL_SHORT. Long and short share the
  book: buying short is economically selling long. Book prices (``bids`` /
  ``offers``) are quoted on the LONG side.
* Market-data messages carry the FULL book (``marketData.bids/offers``) and
  no sequence numbers. Gap detection is therefore "each message is a
  snapshot" plus periodic REST reconciliation.
* Settlement: ``GET /v1/markets/{slug}/settlement`` -> ``{slug, settlement}``.
* No auto-retry of POSTs in the SDK (no idempotency key) - reconcile open
  orders before resending (enforced in Phase 4).

UNVERIFIED / CHANGED vs the original brief:
* The SDK exposes NO fee-schedule endpoint. Orders report
  ``commissionsBasisPoints`` / ``makerCommissionsBasisPoints`` and executions
  ``commissionNotionalCollected``. Fees must be supplied via config
  (``venues.polymarket_us.fees``) and will be reconciled against actual
  commissions on fills once write paths exist. Until a human sets
  ``verified: true`` every edge estimate is flagged.
* Whether the long side of a BTC Up/Down market is "Up" is inferred from the
  market's ``outcome`` field; if it can't be determined we mark it in
  ``Market.meta['up_side_confident'] = False``.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from datetime import timedelta
from decimal import Decimal
from typing import Any

from nacl.signing import SigningKey

from btcmm.adapters.base import BookEvent, ExchangeAdapter
from btcmm.adapters.transport import RestClient, reconnecting_ws
from btcmm.config import Venue, VenueConfig, get_secret
from btcmm.data.book import L2Book, SequenceGap
from btcmm.data.models import (
    BookSnapshot,
    FeeSchedule,
    FeedStatus,
    Market,
    SettlementKind,
    SettlementRule,
    SettlementValue,
    TickRange,
    TradePrint,
    utcnow,
)
from btcmm.data.parse import D, first, parse_ts, window_minutes

log = logging.getLogger(__name__)
ONE = Decimal(1)
_BTC_UPDOWN = re.compile(r"\b(btc|bitcoin)\b.*\bup\b.*\bdown\b", re.I)


class PolymarketUSSigner:
    def __init__(self, key_id: str, secret_b64: str) -> None:
        raw = base64.b64decode(secret_b64)
        if len(raw) == 64:  # expanded key: first 32 bytes are the seed
            raw = raw[:32]
        self.key_id = key_id
        self._key = SigningKey(raw)

    def __call__(self, method: str, path: str) -> dict[str, str]:
        ts = str(int(time.time() * 1000))
        sig = self._key.sign(f"{ts}{method.upper()}{path}".encode()).signature
        return {
            "X-PM-Access-Key": self.key_id,
            "X-PM-Timestamp": ts,
            "X-PM-Signature": base64.b64encode(sig).decode(),
        }


# ---------------------------------------------------------------------------
# Pure parsing
# ---------------------------------------------------------------------------

def parse_settlement_rule(text: str) -> SettlementRule:
    """Expected (verify per market): Up iff Chainlink BTC/USD at window end >=
    price at window start. Point-in-time, not averaged."""
    low = text.lower()
    chainlink = "chainlink" in low
    averaged = "average" in low
    return SettlementRule(
        kind=SettlementKind.AVERAGED if averaged else (SettlementKind.POINT if text else SettlementKind.UNKNOWN),
        reference_index="Chainlink BTC/USD" if chainlink else "unknown",
        comparator=">=",
        source_text=text[:2000],
        parsed_confidently=chainlink and not averaged,
    )


def up_is_long(market: dict[str, Any]) -> tuple[bool, bool]:
    """Return (up_is_long, confident). A market whose outcome is 'Down' has
    its long side = Down, so Up = short and prices must be inverted."""
    outcome = str(market.get("outcome") or "").strip().lower()
    if outcome in ("up", "yes", "higher"):
        return True, True
    if outcome in ("down", "no", "lower"):
        return False, True
    return True, False


def parse_event_markets(event: dict[str, Any], allowed_minutes: list[int]) -> list[Market]:
    title = str(event.get("title") or "")
    if not _BTC_UPDOWN.search(title):
        return []
    start, end = parse_ts(event.get("startTime")), parse_ts(event.get("endTime"))
    if not start or not end:
        return []
    mins = window_minutes(start, end)
    if mins not in allowed_minutes:
        return []
    markets = [m for m in (event.get("markets") or []) if not m.get("closed")]
    # Prefer a single "Up" market if the event lists Up and Down separately;
    # they would share economics, and recording one book per window is enough.
    ups = [m for m in markets if str(m.get("outcome") or "").lower() == "up"]
    chosen = ups[:1] or markets[:1]
    out = []
    rule = parse_settlement_rule(str(event.get("description") or ""))
    for m in chosen:
        is_long, conf = up_is_long(m)
        out.append(Market(
            venue=Venue.POLYMARKET_US,
            market_id=m["slug"],
            event_id=event.get("slug"),
            series_id=(event.get("series") or {}).get("slug"),
            title=title,
            window_start=start,
            window_end=end,
            window_minutes=mins,
            settlement=rule,
            # Tick size is not exposed by the SDK schema; 1 cent assumed (flagged).
            tick_ranges=[TickRange(start=Decimal("0.01"), end=Decimal("0.99"), step=Decimal("0.01"))],
            min_order_size=Decimal(1),
            status="closed" if m.get("closed") else ("active" if m.get("active") else ""),
            meta={"up_is_long": is_long, "up_side_confident": conf, "tick_verified": False},
        ))
    return out


def _lv(levels: Any) -> list[tuple[Decimal, Decimal]]:
    return [(D(l["px"]), D(l["qty"])) for l in (levels or [])]


def normalise_book(md: dict[str, Any], is_long_up: bool) -> tuple[list[tuple[Decimal, Decimal]], list[tuple[Decimal, Decimal]]]:
    """(up_bids, up_asks) from a long-side book. If long==Down, an offer to
    sell Down at q is a bid for Up at 1-q, and vice versa."""
    bids, asks = _lv(md.get("bids")), _lv(md.get("offers"))
    if is_long_up:
        return bids, asks
    return [(ONE - p, q) for p, q in asks], [(ONE - p, q) for p, q in bids]


def trade_aggressor(taker: dict[str, Any], is_long_up: bool) -> str | None:
    intent = str((taker or {}).get("intent") or "")
    buys_long = intent.endswith("BUY_LONG") or intent.endswith("SELL_SHORT")
    sells_long = intent.endswith("SELL_LONG") or intent.endswith("BUY_SHORT")
    if not (buys_long or sells_long):
        return None
    buys_up = buys_long if is_long_up else sells_long
    return "buy" if buys_up else "sell"


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class PolymarketUSAdapter(ExchangeAdapter):
    venue = Venue.POLYMARKET_US

    def __init__(self, cfg: VenueConfig) -> None:
        super().__init__(cfg)
        kid, sec = get_secret(cfg.key_id_env), get_secret(cfg.secret_env)
        self._signer = PolymarketUSSigner(kid, sec) if (kid and sec) else None
        self.public = RestClient(cfg.public_rest_base_url or "https://gateway.polymarket.us")
        self.private = RestClient(cfg.rest_base_url, signer=self._signer)
        self._markets: dict[str, Market] = {}

    @property
    def has_credentials(self) -> bool:
        return self._signer is not None

    async def aclose(self) -> None:
        await self.public.aclose()
        await self.private.aclose()

    async def discover_markets(self) -> list[Market]:
        out: list[Market] = []
        offset, limit = 0, 100
        now = utcnow()
        for _ in range(int(self.cfg.extra.get("max_discovery_pages", 20))):
            data = await self.public.get("/v1/events", params={
                "active": "true", "closed": "false", "limit": limit, "offset": offset,
                "endDateMin": now.isoformat().replace("+00:00", "Z"),
                "endDateMax": (now + timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            })
            events = data.get("events") or []
            for ev in events:
                out.extend(parse_event_markets(ev, self.cfg.window_lengths_min))
            if len(events) < limit:
                break
            offset += limit
        for m in out:
            self._markets[m.market_id] = m
        return out

    def _is_long_up(self, slug: str) -> bool:
        m = self._markets.get(slug)
        return bool(m.meta.get("up_is_long", True)) if m else True

    async def get_book(self, market_id: str) -> BookSnapshot:
        data = await self.public.get(f"/v1/markets/{market_id}/book")
        md = data.get("marketData") or {}
        bids, asks = normalise_book(md, self._is_long_up(market_id))
        book = L2Book(self.venue, market_id)
        book.apply_snapshot(bids, asks, seq=None, exchange_ts=parse_ts(md.get("transactTime")), recv_ts=utcnow())
        return book.snapshot(source="rest_resnapshot")

    def handle_ws_message(self, msg: dict[str, Any]) -> BookEvent | None:
        recv = utcnow()
        if "marketData" in msg:
            md = msg["marketData"]
            slug = md["marketSlug"]
            bids, asks = normalise_book(md, self._is_long_up(slug))
            # Every message is a full book => apply as snapshot (no deltas, no seq).
            book = L2Book(self.venue, slug)
            book.apply_snapshot(bids, asks, seq=None, exchange_ts=parse_ts(md.get("transactTime")), recv_ts=recv)
            return book.snapshot()
        if "trade" in msg:
            t = msg["trade"]
            slug = t["marketSlug"]
            is_long_up = self._is_long_up(slug)
            px = D(t["price"])
            return TradePrint(
                venue=self.venue, market_id=slug,
                price=px if is_long_up else ONE - px,
                size=D(t["quantity"]),
                aggressor=trade_aggressor(t.get("taker") or {}, is_long_up),
                exchange_ts=parse_ts(t.get("tradeTime")), recv_ts=recv,
            )
        if msg.get("error"):
            return FeedStatus(source=self.venue.value, event="error", detail=str(msg["error"]))
        return None

    async def stream_book(self, market_ids: list[str], stop: asyncio.Event) -> AsyncIterator[BookEvent]:
        if not self.has_credentials:
            self._emit_status("degraded", "no credentials: REST polling instead of websocket")
            while not stop.is_set():
                for mid in market_ids:
                    try:
                        yield (await self.get_book(mid)).model_copy(update={"source": "rest_poll"})
                    except Exception as e:  # noqa: BLE001
                        yield FeedStatus(source=self.venue.value, event="error", detail=f"{mid}: {e}")
                try:
                    await asyncio.wait_for(stop.wait(), timeout=self.cfg.rest_poll_interval_s)
                except asyncio.TimeoutError:
                    pass
            return

        # Respect subscription limits: one subscription request per chunk.
        chunk = max(1, self.cfg.max_ws_subscriptions)

        async def on_open(ws: Any) -> None:
            for i in range(0, len(market_ids), chunk):
                slugs = market_ids[i:i + chunk]
                for kind in ("SUBSCRIPTION_TYPE_MARKET_DATA", "SUBSCRIPTION_TYPE_TRADE"):
                    await ws.send(json.dumps({"subscribe": {
                        "requestId": f"{kind}-{i}", "subscriptionType": kind, "marketSlugs": slugs}}))

        assert self._signer is not None
        signer = self._signer
        path = "/v1/ws/markets"
        async for msg in reconnecting_ws(
            self.cfg.ws_url.rstrip("/") + path, name="polymarket_us", on_open=on_open,
            headers_fn=lambda: signer("GET", path),
            on_status=self._emit_status,
            stop=stop,
        ):
            try:
                ev = self.handle_ws_message(msg)
            except SequenceGap as e:  # crossed book
                yield FeedStatus(source=self.venue.value, event="gap", detail=str(e))
                continue
            if ev is not None:
                yield ev

    async def get_fee_schedule(self, market: Market) -> FeeSchedule:
        fo = self.cfg.fees
        if fo is None:
            raise ValueError(
                "polymarket_us: no machine-readable fee schedule in the API; set venues.polymarket_us.fees"
            )
        return FeeSchedule(
            venue=self.venue, scope_id="*", fee_type="coef_x_C_x_P(1-P)",
            taker_coef=fo.taker_coef, maker_coef=fo.maker_coef, maker_rebate_coef=fo.maker_rebate_coef,
            rounding_increment=fo.rounding_increment, rounding_scope=fo.rounding_scope,
            source="config", verified=fo.verified, fetched_at=utcnow(),
            discretionary=list(fo.discretionary_notes),
        )

    def get_settlement_rule(self, market: Market) -> SettlementRule:
        return market.settlement

    async def get_settlement_values(self, market_ids: list[str]) -> list[SettlementValue]:
        out = []
        for slug in market_ids:
            try:
                data = await self.public.get(f"/v1/markets/{slug}/settlement")
            except Exception as e:  # noqa: BLE001 - unsettled markets may 404
                log.debug("pm settlement %s: %s", slug, e)
                continue
            val = first(data, "settlement")
            if val is None:
                continue
            v = D(val)
            out.append(SettlementValue(
                venue=self.venue, market_id=slug,
                value=v if self._is_long_up(slug) else ONE - v,
                recv_ts=utcnow(), raw=data,
            ))
        return out
