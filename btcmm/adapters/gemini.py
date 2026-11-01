"""Gemini Predictions adapter (read-only in Phase 1).

Confirmed (Gemini developer docs, via search summaries):
* ``GET /v1/prediction-markets/events`` is public, paginated, filterable by
  status/category; returns ``{"data": [...], "pagination": {...}}``.
* Contract symbols MUST be taken from each contract's ``instrumentSymbol``
  field - never constructed.
* Sandbox: ``api.sandbox.gemini.com`` (separate account). Trading requires
  ``POST /v1/prediction-markets/terms/accept`` (Phase 4).
* Related: ``/events/{ticker}``, ``/events/recently-settled``.

UNVERIFIED (developer.gemini.com blocked from the build sandbox; parsing is
deliberately tolerant and every assumption is listed in the README):
* event/contract field names beyond ``instrumentSymbol`` (we accept several
  spellings for start/end times, status and resolution);
* order books use the standard Gemini ``GET /v1/book/{symbol}`` and the v2
  market-data websocket ``l2`` subscription, with prices on the YES (= Up)
  side. v2 ``l2_updates`` carry NO sequence numbers, so integrity relies on
  the initial full snapshot per (re)connect plus periodic REST reconciliation;
* settlement rule text location and wording;
* fees are not fetched from an endpoint; config supplies taker 0.07 / maker
  0.0175. The maker waiver (to 2026-12-31) and maker rebate program are
  DISCRETIONARY and never counted in edge.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

from btcmm.adapters.base import BookEvent, ExchangeAdapter
from btcmm.adapters.transport import RestClient, reconnecting_ws
from btcmm.config import Venue, VenueConfig
from btcmm.data.book import L2Book, SequenceGap
from btcmm.data.models import (
    BookSnapshot,
    FeeSchedule,
    FeedStatus,
    Market,
    SettlementKind,
    SettlementRule,
    SettlementValue,
    TradePrint,
    utcnow,
)
from btcmm.data.parse import D, first, parse_ts, window_minutes

log = logging.getLogger(__name__)
_BTC = re.compile(r"\b(btc|bitcoin)\b", re.I)
_UPDOWN = re.compile(r"\bup\b.*\bdown\b|\bhigher\b|\bup or down\b", re.I)


# ---------------------------------------------------------------------------
# Pure parsing
# ---------------------------------------------------------------------------

def parse_settlement_rule(text: str) -> SettlementRule:
    """If the reference is Gemini's own spot book, fair value must use Gemini
    BTCUSD as its primary spot input (spec). Averaged vs point is detected
    from the wording and flagged if unclear."""
    low = text.lower()
    averaged = "average" in low or "twap" in low
    gemini_ref = "gemini" in low and ("btcusd" in low or "btc/usd" in low or "exchange" in low or "price" in low)
    return SettlementRule(
        kind=SettlementKind.AVERAGED if averaged else (SettlementKind.POINT if text else SettlementKind.UNKNOWN),
        reference_index="Gemini BTCUSD" if gemini_ref else "unknown",
        comparator=">=",
        source_text=text[:2000],
        parsed_confidently=bool(text) and gemini_ref,
    )


def _contract_is_up(c: dict[str, Any]) -> bool:
    label = str(first(c, "label", "abbreviatedName", "name", "title", default="")).lower()
    return "up" in label.split() or "higher" in label or label in ("yes", "up")


def parse_events(data: dict[str, Any], allowed_minutes: list[int]) -> list[Market]:
    out: list[Market] = []
    for ev in data.get("data") or data.get("events") or []:
        title = str(first(ev, "title", "name", default=""))
        if not (_BTC.search(title) and _UPDOWN.search(title + " " + str(ev.get("description") or ""))):
            continue
        contracts = ev.get("contracts") or []
        ups = [c for c in contracts if _contract_is_up(c)]
        # Single-contract events: YES == Up (assumption, flagged in meta).
        chosen = ups[:1] or (contracts[:1] if len(contracts) == 1 else [])
        for c in chosen:
            sym = c.get("instrumentSymbol")
            if not sym:
                continue  # never construct symbols
            start = parse_ts(first(c, "effectiveDate", "startTime", "openTime", default=None)
                             or first(ev, "effectiveDate", "startTime", "openTime", default=None))
            end = parse_ts(first(c, "expiryDate", "endTime", "closeTime", default=None)
                           or first(ev, "expiryDate", "endTime", "closeTime", default=None))
            if not start or not end:
                continue
            mins = window_minutes(start, end)
            if mins not in allowed_minutes:
                continue
            rule_text = " ".join(str(x or "") for x in (
                c.get("description"), c.get("rules"), ev.get("description"), ev.get("rules"),
                c.get("resolutionSource"), ev.get("resolutionSource")))
            out.append(Market(
                venue=Venue.GEMINI, market_id=sym, event_id=first(ev, "ticker", "slug", "id"),
                title=title, window_start=start, window_end=end, window_minutes=mins,
                settlement=parse_settlement_rule(rule_text.strip()),
                status=str(first(c, "status", "marketState", default="")),
                meta={"up_is_yes": True, "up_side_confident": bool(ups), "tick_verified": False,
                      "terms_url": c.get("termsAndConditionsUrl")},
            ))
    return out


def _lvls(xs: Any) -> list[tuple[Decimal, Decimal]]:
    out = []
    for x in xs or []:
        if isinstance(x, dict):
            out.append((D(x["price"]), D(first(x, "amount", "quantity", "size"))))
        else:
            out.append((D(x[0]), D(x[1])))
    return out


def parse_rest_book(data: dict[str, Any]) -> tuple[list[tuple[Decimal, Decimal]], list[tuple[Decimal, Decimal]]]:
    return _lvls(data.get("bids")), _lvls(data.get("asks"))


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class GeminiAdapter(ExchangeAdapter):
    venue = Venue.GEMINI

    def __init__(self, cfg: VenueConfig) -> None:
        super().__init__(cfg)
        self.rest = RestClient(cfg.rest_base_url)

    async def aclose(self) -> None:
        await self.rest.aclose()

    async def discover_markets(self) -> list[Market]:
        out: list[Market] = []
        offset, limit = 0, 100
        for _ in range(int(self.cfg.extra.get("max_discovery_pages", 20))):
            data = await self.rest.get("/v1/prediction-markets/events", params={
                "status": "active", "category": "crypto", "limit": limit, "offset": offset})
            out.extend(parse_events(data, self.cfg.window_lengths_min))
            n = len(data.get("data") or [])
            if n < limit:
                break
            offset += limit
        return out

    async def get_book(self, market_id: str) -> BookSnapshot:
        data = await self.rest.get(f"/v1/book/{market_id}")
        bids, asks = parse_rest_book(data)
        book = L2Book(self.venue, market_id)
        book.apply_snapshot(bids, asks, seq=None, exchange_ts=None, recv_ts=utcnow())
        return book.snapshot(source="rest_resnapshot")

    def handle_ws_message(self, msg: dict[str, Any], books: dict[str, L2Book]) -> list[BookEvent]:
        """v2 market data: first ``l2_updates`` per symbol after subscribe is a
        full snapshot; subsequent ones carry absolute level sizes."""
        recv = utcnow()
        typ = msg.get("type")
        out: list[BookEvent] = []
        if typ == "l2_updates":
            sym = msg["symbol"]
            changes = [(str(c[0]).lower(), D(c[1]), D(c[2])) for c in msg.get("changes") or []]
            book = books.get(sym)
            if book is None or not book.initialized:
                bids = [(p, q) for s, p, q in changes if s == "buy"]
                asks = [(p, q) for s, p, q in changes if s == "sell"]
                book = books.setdefault(sym, L2Book(self.venue, sym))
                book.apply_snapshot(bids, asks, seq=None, exchange_ts=None, recv_ts=recv)
            else:
                for s, p, q in changes:
                    book.apply_delta("bid" if s == "buy" else "ask", p, size=q, seq=None,
                                     exchange_ts=None, recv_ts=recv)
            out.append(book.snapshot())
            for t in msg.get("trades") or []:
                out.append(self._trade(t, recv))
        elif typ == "trade":
            out.append(self._trade(msg, recv))
        elif typ == "error" or msg.get("result") == "error":
            out.append(FeedStatus(source=self.venue.value, event="error", detail=json.dumps(msg)[:500]))
        return out

    def _trade(self, t: dict[str, Any], recv: Any) -> TradePrint:
        side = str(t.get("side") or "").lower()
        return TradePrint(
            venue=self.venue, market_id=t["symbol"], price=D(t["price"]), size=D(t["quantity"]),
            aggressor="buy" if side == "buy" else ("sell" if side == "sell" else None),
            exchange_ts=parse_ts(t.get("timestamp")), recv_ts=recv,
            trade_id=str(t.get("event_id") or t.get("tid") or "") or None,
        )

    async def stream_book(self, market_ids: list[str], stop: asyncio.Event) -> AsyncIterator[BookEvent]:
        books: dict[str, L2Book] = {}
        chunk = max(1, self.cfg.max_ws_subscriptions)

        async def on_open(ws: Any) -> None:
            books.clear()  # reconnect == gap: wait for fresh snapshots
            for i in range(0, len(market_ids), chunk):
                await ws.send(json.dumps({"type": "subscribe", "subscriptions": [
                    {"name": "l2", "symbols": market_ids[i:i + chunk]}]}))

        async for msg in reconnecting_ws(
            self.cfg.ws_url, name="gemini", on_open=on_open, stop=stop,
            on_status=self._emit_status,
        ):
            try:
                for ev in self.handle_ws_message(msg, books):
                    yield ev
            except SequenceGap as e:
                yield FeedStatus(source=self.venue.value, event="gap", detail=str(e))
                sym = msg.get("symbol")
                if sym:
                    # No seq numbers: resnapshot this symbol from REST.
                    try:
                        snap = await self.get_book(sym)
                        b = books.setdefault(sym, L2Book(self.venue, sym))
                        b.apply_snapshot([(l.price, l.size) for l in snap.bids], [(l.price, l.size) for l in snap.asks],
                                         seq=None, exchange_ts=None, recv_ts=snap.recv_ts)
                        yield snap
                    except Exception as e2:  # noqa: BLE001
                        books.pop(sym, None)
                        yield FeedStatus(source=self.venue.value, event="error", detail=f"resnapshot {sym}: {e2}")

    async def get_fee_schedule(self, market: Market) -> FeeSchedule:
        fo = self.cfg.fees
        if fo is None:
            raise ValueError("gemini: set venues.gemini.fees (no fee endpoint wired)")
        return FeeSchedule(
            venue=self.venue, scope_id="*", fee_type="coef_x_C_x_P(1-P)",
            taker_coef=fo.taker_coef, maker_coef=fo.maker_coef,
            maker_rebate_coef=fo.maker_rebate_coef,  # deterministic only; programs are discretionary
            rounding_increment=fo.rounding_increment, rounding_scope=fo.rounding_scope,
            source="config", verified=fo.verified, fetched_at=utcnow(),
            discretionary=list(fo.discretionary_notes),
        )

    def get_settlement_rule(self, market: Market) -> SettlementRule:
        return market.settlement

    async def get_settlement_values(self, market_ids: list[str]) -> list[SettlementValue]:
        wanted = set(market_ids)
        data = await self.rest.get("/v1/prediction-markets/events/recently-settled", params={"limit": 100})
        return parse_settlements(data, wanted)


def parse_settlements(data: dict[str, Any], wanted: set[str]) -> list[SettlementValue]:
    out = []
    for ev in data.get("data") or data.get("events") or []:
        for c in ev.get("contracts") or []:
            sym = c.get("instrumentSymbol")
            if sym not in wanted:
                continue
            res = str(first(c, "resolutionSide", "resolution", "result", "settlementSide", default="")).lower()
            if res not in ("yes", "no", "up", "down"):
                continue
            out.append(SettlementValue(
                venue=Venue.GEMINI, market_id=sym,
                value=Decimal(1) if res in ("yes", "up") else Decimal(0),
                settled_ts=parse_ts(first(c, "settledAt", "resolvedAt", "expiryDate", default=None)),
                recv_ts=utcnow(), raw={k: c.get(k) for k in c if k != "prices"},
            ))
    return out
