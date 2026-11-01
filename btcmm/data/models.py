"""Venue-agnostic data model.

Conventions (apply everywhere in the codebase)
---------------------------------------------
* Prices are ``Decimal`` dollars per contract in [0, 1]. Each contract pays $1
  if it resolves in the money. Floats are never used for prices or fees,
  because fee rounding is exact per venue and float error would leak into
  edge estimates.
* Every book is normalised to the **Up** contract: ``bids`` are prices at which
  someone will buy Up, ``asks`` are prices at which someone will sell Up.
  Venue adapters are responsible for this mapping (e.g. Kalshi publishes only
  YES and NO bids; a NO bid at q is an Up ask at 1-q).
* Quantities are ``Decimal`` contracts (Kalshi supports 0.01-contract
  granularity, so ints are not enough).
* All timestamps are timezone-aware UTC. Every event carries both the
  exchange timestamp (if the venue provides one) and our local receive time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from btcmm.config import Venue


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _Msg(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SettlementKind(str, Enum):
    # Settles on the index value at a single instant (Polymarket US / Chainlink).
    POINT = "point"
    # Settles on an average of the index over a window (Kalshi / BRTI 60s average).
    AVERAGED = "averaged"
    UNKNOWN = "unknown"


class SettlementRule(_Msg):
    """How a contract resolves. Correlated-but-different rules across venues are
    the main reason cross-venue gaps are NOT arbitrage."""

    kind: SettlementKind
    reference_index: str  # e.g. "CF Benchmarks BRTI", "Chainlink BTC/USD", "Gemini BTCUSD"
    # For AVERAGED: length of the averaging window at open and at close.
    averaging_seconds: int | None = None
    # Comparison applied: Up/YES wins if end <cmp> start. ">=" means ties go to Up.
    comparator: str = ">="
    # Fixed strike if the venue publishes one (e.g. Kalshi floor_strike once known).
    strike: Decimal | None = None
    # Verbatim rule text so humans can audit our parse.
    source_text: str = ""
    # True only if the parser matched an expected, recognised rule pattern.
    parsed_confidently: bool = False


class TickRange(_Msg):
    start: Decimal
    end: Decimal
    step: Decimal


class Market(_Msg):
    """One tradable BTC Up/Down window on one venue."""

    venue: Venue
    market_id: str  # venue-native id: Kalshi ticker, PM US slug, Gemini instrumentSymbol
    event_id: str | None = None
    series_id: str | None = None
    title: str = ""
    window_start: datetime
    window_end: datetime
    window_minutes: int
    settlement: SettlementRule
    tick_ranges: list[TickRange] = Field(default_factory=list)
    min_order_size: Decimal = Decimal("1")
    status: str = ""
    # Venue-specific extras we may need later (e.g. PM US intent mapping).
    meta: dict[str, Any] = Field(default_factory=dict)


class BookLevel(_Msg):
    price: Decimal
    size: Decimal


class BookSnapshot(_Msg):
    """Full normalised Up-contract book at a point in time."""

    venue: Venue
    market_id: str
    bids: list[BookLevel]  # descending price
    asks: list[BookLevel]  # ascending price
    exchange_ts: datetime | None
    recv_ts: datetime
    seq: int | None = None
    source: str = "ws"  # ws | rest_poll | rest_resnapshot

    @property
    def best_bid(self) -> BookLevel | None:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> BookLevel | None:
        return self.asks[0] if self.asks else None


class TradePrint(_Msg):
    venue: Venue
    market_id: str
    price: Decimal  # Up-contract price
    size: Decimal
    # "buy" if the aggressor bought Up, "sell" if aggressor sold Up, None if unknown.
    aggressor: str | None
    exchange_ts: datetime | None
    recv_ts: datetime
    trade_id: str | None = None


class SpotTick(_Msg):
    source: str
    symbol: str
    price: Decimal
    bid: Decimal | None = None
    ask: Decimal | None = None
    exchange_ts: datetime | None
    recv_ts: datetime


class SettlementValue(_Msg):
    """Official resolution of a market, as reported by the venue."""

    venue: Venue
    market_id: str
    # 1 if Up/YES won, 0 if Down/NO won, fractional only if the venue says so.
    value: Decimal
    reference_start: Decimal | None = None
    reference_end: Decimal | None = None
    settled_ts: datetime | None = None
    recv_ts: datetime
    raw: dict[str, Any] = Field(default_factory=dict)


class FeeSchedule(_Msg):
    """Per-venue (per-series) fee model.

    fee(C, P) = round_up_to(rounding_increment, coef * C * P * (1 - P))

    * ``taker_coef`` / ``maker_coef`` are *charges* (positive numbers).
    * ``maker_rebate_coef`` is a *deterministic* per-fill rebate (counted in edge).
    * ``discretionary`` lists waivers / rebate programs / incentives that are
      logged separately and NEVER counted in edge.
    """

    venue: Venue
    scope_id: str  # series ticker, market slug, or "*"
    fee_type: str
    taker_coef: Decimal
    maker_coef: Decimal
    maker_rebate_coef: Decimal = Decimal("0")
    rounding_increment: Decimal = Decimal("0.01")
    rounding_scope: str = "order"  # "order" | "fill"
    source: str  # "api" | "config"
    verified: bool
    fetched_at: datetime
    discretionary: list[str] = Field(default_factory=list)


class FeedStatus(_Msg):
    """Health event emitted by adapters/feeds (connects, gaps, resnapshots)."""

    source: str
    event: str  # connected | disconnected | gap | resnapshot | stale | error
    detail: str = ""
    recv_ts: datetime = Field(default_factory=utcnow)
