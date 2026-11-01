"""Kalshi adapter (read-only in Phase 1).

Verified against the official ``kalshi_python_async`` SDK (v3.35.0) models:
* Auth: KALSHI-ACCESS-KEY / -SIGNATURE / -TIMESTAMP headers; signature over
  ``timestamp_ms + METHOD + path`` (no query), RSA-PSS(SHA-256, salt=digest
  length) - Ed25519 keys are now also accepted.
* Prices are fixed-point dollar strings (``*_dollars``), contract counts are
  fixed-point strings (``*_fp``) with 0.01-contract granularity. The legacy
  integer-cent fields are not in the current schema; we still parse them as a
  fallback.
* Orderbook REST returns only YES bids and NO bids. Normalisation: an Up ask
  at price p exists wherever someone bids NO at 1-p.
* Series carry ``fee_type`` in {quadratic, quadratic_with_maker_fees,
  quadratic_with_combo_maker_fees, flat} and a ``fee_multiplier``.
* Markets carry ``price_ranges`` (variable tick sizes), ``rules_primary``,
  ``fee_waiver_expiration_time``, ``settlement_value_dollars``,
  ``expiration_value``.

UNVERIFIED (docs host blocked from the build sandbox; see README "Assumptions"):
* websocket message shapes for ``orderbook_snapshot`` / ``orderbook_delta``
  / ``trade`` (we accept both the dollar/fp and legacy cent spellings);
* exact fee rounding rule (default: ceil to $0.01 per order, configurable).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

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
from btcmm.data.parse import D, D_or_none, first, parse_ts, window_minutes

log = logging.getLogger(__name__)
ONE = Decimal(1)

# Kalshi general trading fee coefficient (fee schedule "General Trading Fees
# Table"). The series fee_multiplier scales it.
KALSHI_TAKER_COEF = Decimal("0.07")
# Maker fee as a fraction of the taker coefficient per fee_type (SDK FeeType docs:
# maker multiplier 0.25 for quadratic_with_maker_fees, 0.5 for the combo variant).
KALSHI_MAKER_RATIO = {
    "quadratic": Decimal("0"),
    "quadratic_with_maker_fees": Decimal("0.25"),
    "quadratic_with_combo_maker_fees": Decimal("0.5"),
}

# A series is a BTC short-window candidate if its ticker looks like KXBTC<N>M.
# This is a discovery FILTER on series returned by the API, not a hardcoded ticker.
_BTC_MINUTE_SERIES = re.compile(r"^KXBTC(\d+)M$")


class KalshiSigner:
    def __init__(self, key_id: str, pem: bytes) -> None:
        self.key_id = key_id
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, (RSAPrivateKey, Ed25519PrivateKey)):
            raise ValueError("Kalshi key must be RSA or Ed25519")
        self._key = key

    def __call__(self, method: str, path: str) -> dict[str, str]:
        ts = str(int(time.time() * 1000))
        msg = (ts + method.upper() + path.split("?")[0]).encode()
        if isinstance(self._key, Ed25519PrivateKey):
            sig = self._key.sign(msg)
        else:
            sig = self._key.sign(
                msg,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                hashes.SHA256(),
            )
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
            "KALSHI-ACCESS-TIMESTAMP": ts,
        }


# ---------------------------------------------------------------------------
# Pure parsing functions (unit-tested against fixtures)
# ---------------------------------------------------------------------------

def parse_settlement_rule(market: dict[str, Any]) -> SettlementRule:
    """Expected rule (verify per market): YES iff the BRTI 60s average at window
    end >= the 60s average before window open. We only mark the parse confident
    when the rule text mentions both averaging and CF Benchmarks/BRTI."""
    text = " ".join(str(market.get(k) or "") for k in ("rules_primary", "rules_secondary")).strip()
    low = text.lower()
    averaged = "average" in low
    m = re.search(r"(\d+)\s*(?:-|\s)?\s*seconds?", low)
    avg_s = int(m.group(1)) if (averaged and m) else (60 if averaged else None)
    brti = "brti" in low or "cf benchmarks" in low or "real time index" in low
    kind = SettlementKind.AVERAGED if averaged else (SettlementKind.POINT if text else SettlementKind.UNKNOWN)
    strike = D_or_none(market.get("floor_strike"))
    return SettlementRule(
        kind=kind,
        reference_index="CF Benchmarks BRTI" if brti else "unknown",
        averaging_seconds=avg_s,
        comparator=">=",
        strike=strike,
        source_text=text[:2000],
        parsed_confidently=bool(averaged and brti),
    )


def parse_market(m: dict[str, Any], series_ticker: str) -> Market | None:
    start = parse_ts(m.get("open_time"))
    end = parse_ts(first(m, "close_time", "expected_expiration_time"))
    if not start or not end:
        return None
    ticks = [
        TickRange(start=D(r["start"]), end=D(r["end"]), step=D(r["step"]))
        for r in (m.get("price_ranges") or [])
    ]
    return Market(
        venue=Venue.KALSHI,
        market_id=m["ticker"],
        event_id=m.get("event_ticker"),
        series_id=series_ticker,
        title=str(m.get("title") or ""),
        window_start=start,
        window_end=end,
        window_minutes=window_minutes(start, end),
        settlement=parse_settlement_rule(m),
        tick_ranges=ticks,
        min_order_size=Decimal("0.01"),  # fp granularity; strategy picks a larger size
        status=str(m.get("status") or ""),
        meta={
            "fee_waiver_expiration_time": m.get("fee_waiver_expiration_time"),
            "price_level_structure": m.get("price_level_structure"),
            "strike_type": m.get("strike_type"),
        },
    )


def _levels(raw: Any, cents: bool) -> list[tuple[Decimal, Decimal]]:
    out = []
    for lvl in raw or []:
        p, q = D(lvl[0]), D(lvl[1])
        if cents:
            p = p / 100
        out.append((p, q))
    return out


def parse_book_sides(ob: dict[str, Any]) -> tuple[list[tuple[Decimal, Decimal]], list[tuple[Decimal, Decimal]]]:
    """Return (up_bids, up_asks) from a Kalshi YES/NO bid book.

    Kalshi has a single YES/NO book where every resting order is a bid:
    * YES bid at p  -> Up bid at p
    * NO  bid at q  -> Up ask at 1-q   (buying NO at q == selling YES at 1-q)
    """
    if "yes_dollars" in ob or "no_dollars" in ob or "yes_dollars_fp" in ob:
        yes = _levels(first(ob, "yes_dollars_fp", "yes_dollars", default=[]), cents=False)
        no = _levels(first(ob, "no_dollars_fp", "no_dollars", default=[]), cents=False)
    else:  # legacy integer cents
        yes = _levels(ob.get("yes"), cents=True)
        no = _levels(ob.get("no"), cents=True)
    bids = [(p, q) for p, q in yes]
    asks = [(ONE - p, q) for p, q in no]
    return bids, asks


def fee_schedule_from_series(series: dict[str, Any], cfg: VenueConfig) -> FeeSchedule:
    """Fee rule: taker = round_up(0.07*mult * C * P(1-P)) per order; maker is 0
    unless fee_type includes maker fees. Rounding increment/scope come from
    config (unverified - docs blocked at build time)."""
    fee_type = str(series.get("fee_type") or "")
    mult = D(series.get("fee_multiplier", 1))
    if fee_type not in KALSHI_MAKER_RATIO:
        # 'flat' or unknown: refuse to guess.
        raise ValueError(f"Kalshi fee_type {fee_type!r} not modelled; refusing to guess fees")
    taker = KALSHI_TAKER_COEF * mult
    override = cfg.fees
    return FeeSchedule(
        venue=Venue.KALSHI,
        scope_id=str(series.get("ticker", "*")),
        fee_type=fee_type,
        taker_coef=taker,
        maker_coef=taker * KALSHI_MAKER_RATIO[fee_type],
        maker_rebate_coef=Decimal(0),  # Kalshi has no deterministic per-fill maker rebate
        rounding_increment=override.rounding_increment if override else Decimal("0.01"),
        rounding_scope=override.rounding_scope if override else "order",
        source="api",
        # Coefficients come from the API; rounding is verified only if a human said so.
        verified=bool(override and override.verified),
        fetched_at=utcnow(),
        discretionary=list(override.discretionary_notes) if override else [],
    )


def parse_settlement(m: dict[str, Any]) -> SettlementValue | None:
    status = str(m.get("status") or "").lower()
    result = str(m.get("result") or "").lower()
    if status not in ("settled", "finalized", "determined") and result not in ("yes", "no"):
        return None
    if result in ("yes", "no"):
        value = Decimal(1) if result == "yes" else Decimal(0)
    elif m.get("settlement_value_dollars") is not None:
        value = D(m["settlement_value_dollars"])
    else:
        return None
    return SettlementValue(
        venue=Venue.KALSHI,
        market_id=m["ticker"],
        value=value,
        reference_start=D_or_none(m.get("floor_strike")),
        reference_end=D_or_none(m.get("expiration_value")),
        settled_ts=parse_ts(m.get("settlement_ts")),
        recv_ts=utcnow(),
        raw={k: m.get(k) for k in ("result", "settlement_value_dollars", "expiration_value", "floor_strike", "settlement_ts")},
    )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class KalshiAdapter(ExchangeAdapter):
    venue = Venue.KALSHI

    def __init__(self, cfg: VenueConfig) -> None:
        super().__init__(cfg)
        key_id = get_secret(cfg.key_id_env)
        pem: bytes | None = None
        if cfg.secret_path_env and (p := get_secret(cfg.secret_path_env)):
            with open(p, "rb") as fh:
                pem = fh.read()
        elif cfg.secret_env and (s := get_secret(cfg.secret_env)):
            pem = s.encode()
        self._signer = KalshiSigner(key_id, pem) if (key_id and pem) else None
        self.rest = RestClient(cfg.rest_base_url, signer=self._signer)
        self._series_cache: dict[str, dict[str, Any]] = {}

    @property
    def has_credentials(self) -> bool:
        return self._signer is not None

    async def aclose(self) -> None:
        await self.rest.aclose()

    # ---- discovery ----------------------------------------------------------
    async def _btc_series(self) -> list[dict[str, Any]]:
        data = await self.rest.get("/series", params={"category": "Crypto"})
        out = []
        for s in data.get("series") or []:
            t = str(s.get("ticker", ""))
            m = _BTC_MINUTE_SERIES.match(t)
            if m and int(m.group(1)) in self.cfg.window_lengths_min:
                out.append(s)
                self._series_cache[t] = s
        return out

    async def discover_markets(self) -> list[Market]:
        markets: list[Market] = []
        for s in await self._btc_series():
            cursor: str | None = None
            while True:
                params: dict[str, Any] = {"series_ticker": s["ticker"], "status": "open", "limit": 200}
                if cursor:
                    params["cursor"] = cursor
                data = await self.rest.get("/markets", params=params)
                for raw in data.get("markets") or []:
                    mk = parse_market(raw, s["ticker"])
                    if mk and mk.window_minutes in self.cfg.window_lengths_min:
                        markets.append(mk)
                cursor = data.get("cursor") or None
                if not cursor:
                    break
        return markets

    # ---- books ---------------------------------------------------------------
    async def get_book(self, market_id: str) -> BookSnapshot:
        data = await self.rest.get(f"/markets/{market_id}/orderbook")
        ob = first(data, "orderbook_fp", "orderbook", default={}) or {}
        bids, asks = parse_book_sides(ob)
        book = L2Book(self.venue, market_id)
        book.apply_snapshot(bids, asks, seq=None, exchange_ts=None, recv_ts=utcnow())
        return book.snapshot(source="rest_resnapshot")

    async def stream_book(self, market_ids: list[str], stop: asyncio.Event) -> AsyncIterator[BookEvent]:
        if not self.has_credentials:
            # Kalshi websockets require auth. Without keys, fall back to slow REST polling.
            self._emit_status("degraded", "no credentials: REST polling instead of websocket")
            async for ev in self._poll_books(market_ids, stop):
                yield ev
            return
        async for ev in self._ws_books(market_ids, stop):
            yield ev

    async def _poll_books(self, market_ids: list[str], stop: asyncio.Event) -> AsyncIterator[BookEvent]:
        while not stop.is_set():
            for mid in market_ids:
                try:
                    snap = await self.get_book(mid)
                    yield snap.model_copy(update={"source": "rest_poll"})
                except Exception as e:  # noqa: BLE001
                    yield FeedStatus(source=self.venue.value, event="error", detail=f"{mid}: {e}")
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.cfg.rest_poll_interval_s)
            except asyncio.TimeoutError:
                pass

    async def _ws_books(self, market_ids: list[str], stop: asyncio.Event) -> AsyncIterator[BookEvent]:
        books: dict[str, L2Book] = {}
        sid_seq: dict[int, int] = {}
        ws_path = "/" + self.cfg.ws_url.split("://", 1)[1].split("/", 1)[1]

        async def on_open(ws: Any) -> None:
            books.clear()
            sid_seq.clear()
            await ws.send(json.dumps({
                "id": 1, "cmd": "subscribe",
                "params": {"channels": ["orderbook_delta", "trade"], "market_tickers": market_ids},
            }))

        assert self._signer is not None
        signer = self._signer
        while not stop.is_set():
            gen = reconnecting_ws(
                self.cfg.ws_url, name="kalshi", on_open=on_open,
                headers_fn=lambda: signer("GET", ws_path), on_status=self._emit_status, stop=stop,
            )
            gap = False
            async for msg in gen:
                try:
                    ev = self.handle_ws_message(msg, books, sid_seq)
                except SequenceGap as e:
                    # Kalshi seq is per subscription (sid): one gap makes every
                    # book on that subscription suspect. Drop the connection;
                    # resubscribing makes the server send fresh snapshots.
                    yield FeedStatus(source=self.venue.value, event="gap", detail=str(e))
                    gap = True
                    break
                if ev is not None:
                    yield ev
            await gen.aclose()
            if not gap:
                return

    def handle_ws_message(
        self, msg: dict[str, Any], books: dict[str, L2Book], sid_seq: dict[int, int]
    ) -> BookEvent | None:
        """Apply one websocket message. Pure w.r.t. network, so unit-testable."""
        typ = msg.get("type")
        body = msg.get("msg") or {}
        recv = utcnow()
        sid, seq = msg.get("sid"), msg.get("seq")
        if typ in ("orderbook_snapshot", "orderbook_delta") and sid is not None and seq is not None:
            last = sid_seq.get(sid)
            if typ == "orderbook_delta" and last is not None and seq != last + 1:
                raise SequenceGap(f"kalshi sid {sid}: have seq {last}, got {seq}")
            sid_seq[sid] = seq
        if typ == "orderbook_snapshot":
            mid = body["market_ticker"]
            bids, asks = parse_book_sides(body)
            book = books.setdefault(mid, L2Book(self.venue, mid))
            book.apply_snapshot(bids, asks, seq=None, exchange_ts=parse_ts(body.get("ts")), recv_ts=recv)
            return book.snapshot()
        if typ == "orderbook_delta":
            mid = body["market_ticker"]
            book = books.get(mid)
            if book is None:
                raise SequenceGap(f"kalshi {mid}: delta before snapshot")
            price_raw = first(body, "price_dollars", default=None)
            price = D(price_raw) if price_raw is not None else D(body["price"]) / 100
            delta = D(first(body, "delta_fp", "delta"))
            side = str(body["side"]).lower()
            # YES bid change -> Up bid at p; NO bid change -> Up ask at 1-p.
            if side == "yes":
                book.apply_delta("bid", price, delta=delta, seq=None, exchange_ts=parse_ts(body.get("ts")), recv_ts=recv)
            else:
                book.apply_delta("ask", ONE - price, delta=delta, seq=None, exchange_ts=parse_ts(body.get("ts")), recv_ts=recv)
            return book.snapshot()
        if typ == "trade":
            yp = first(body, "yes_price_dollars", default=None)
            price = D(yp) if yp is not None else D(body["yes_price"]) / 100
            taker = str(body.get("taker_side") or "").lower()
            return TradePrint(
                venue=self.venue,
                market_id=body["market_ticker"],
                price=price,
                size=D(first(body, "count_fp", "count")),
                # Taker bought YES => aggressor bought Up.
                aggressor="buy" if taker == "yes" else ("sell" if taker == "no" else None),
                exchange_ts=parse_ts(body.get("ts")),
                recv_ts=recv,
                trade_id=body.get("trade_id"),
            )
        if typ == "error":
            return FeedStatus(source=self.venue.value, event="error", detail=str(body))
        return None

    # ---- fees / settlement ---------------------------------------------------
    async def get_fee_schedule(self, market: Market) -> FeeSchedule:
        st = market.series_id or ""
        series = self._series_cache.get(st)
        if series is None:
            series = (await self.rest.get(f"/series/{st}")).get("series") or {}
            self._series_cache[st] = series
        sched = fee_schedule_from_series(series, self.cfg)
        waiver = market.meta.get("fee_waiver_expiration_time")
        if waiver:
            # Fee waivers are discretionary/temporary: logged, never counted in edge.
            sched = sched.model_copy(update={"discretionary": [*sched.discretionary, f"fee_waiver_until={waiver}"]})
        return sched

    def get_settlement_rule(self, market: Market) -> SettlementRule:
        return market.settlement

    async def get_settlement_values(self, market_ids: list[str]) -> list[SettlementValue]:
        out = []
        for mid in market_ids:
            data = await self.rest.get(f"/markets/{mid}")
            sv = parse_settlement(data.get("market") or {})
            if sv:
                out.append(sv)
        return out


__all__ = ["KalshiAdapter", "KalshiSigner", "parse_book_sides", "parse_market", "fee_schedule_from_series"]

