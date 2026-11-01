"""ExchangeAdapter interface.

One adapter per venue translates venue-native APIs into the venue-agnostic
model in :mod:`btcmm.data.models`. The core (fair value, strategy, risk,
simulation) only ever sees this interface.

Phase 1 implements the READ paths. Write paths (place/modify/cancel/
cancel_all) exist on the interface so the shape is fixed, but every concrete
adapter raises :class:`WritePathDisabled` until Phase 4, where they are
tested only against Kalshi demo, Gemini sandbox and the SimulatedAdapter.
"""

from __future__ import annotations

import abc
import asyncio
from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from btcmm.config import Venue, VenueConfig
from btcmm.data.models import (
    BookSnapshot,
    FeedStatus,
    FeeSchedule,
    Market,
    SettlementRule,
    SettlementValue,
    TradePrint,
)


class WritePathDisabled(RuntimeError):
    """Order entry is not available in this build/phase."""


class OrderRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    market_id: str
    side: Literal["buy_up", "sell_up"]  # always expressed on the Up contract
    price: Decimal
    size: Decimal
    post_only: bool = True
    client_order_id: str


BookEvent = BookSnapshot | TradePrint | FeedStatus


class ExchangeAdapter(abc.ABC):
    venue: Venue

    def __init__(self, cfg: VenueConfig) -> None:
        self.cfg = cfg
        self._status_cb: Callable[[FeedStatus], None] | None = None

    def on_status(self, cb: Callable[[FeedStatus], None]) -> None:
        self._status_cb = cb

    def _emit_status(self, event: str, detail: str = "") -> None:
        if self._status_cb:
            self._status_cb(FeedStatus(source=self.venue.value, event=event, detail=detail))

    # ---- lifecycle -------------------------------------------------------
    async def aclose(self) -> None:  # pragma: no cover - default no-op
        return None

    @property
    def has_credentials(self) -> bool:
        return False

    # ---- read paths (Phase 1) -------------------------------------------
    @abc.abstractmethod
    async def discover_markets(self) -> list[Market]:
        """Active BTC Up/Down markets for configured window lengths.
        Never hardcode tickers/symbols - always discover."""

    @abc.abstractmethod
    def stream_book(
        self, market_ids: list[str], stop: asyncio.Event
    ) -> AsyncIterator[BookEvent]:
        """Normalised Up-contract book snapshots (one per update) plus trades
        and feed-health events. Must resnapshot on any gap/reconnect."""

    @abc.abstractmethod
    async def get_book(self, market_id: str) -> BookSnapshot:
        """REST snapshot (used for resnapshot and reconciliation)."""

    @abc.abstractmethod
    async def get_fee_schedule(self, market: Market) -> FeeSchedule:
        """Fee schedule applicable to this market, loaded at runtime."""

    @abc.abstractmethod
    def get_settlement_rule(self, market: Market) -> SettlementRule:
        """Parsed settlement rule (already attached to Market at discovery)."""

    @abc.abstractmethod
    async def get_settlement_values(self, market_ids: list[str]) -> list[SettlementValue]:
        """Official settlement outcomes for any of these markets that have settled."""

    async def stream_private(self, stop: asyncio.Event) -> AsyncIterator[dict[str, Any]]:
        """Private fills/orders/positions/balances (source of truth for fills).
        Read-only in Phase 1; adapters without credentials yield nothing."""
        if False:  # pragma: no cover
            yield {}
        return

    async def get_positions(self) -> list[dict[str, Any]]:
        raise WritePathDisabled("positions reconciliation lands with Phase 4")

    async def get_balance(self) -> Decimal:
        raise WritePathDisabled("balance reconciliation lands with Phase 4")

    # ---- write paths (Phase 4) ------------------------------------------
    async def place_order(self, req: OrderRequest) -> str:
        raise WritePathDisabled(f"{self.venue.value}: order entry disabled until Phase 4")

    async def modify_order(self, order_id: str, price: Decimal, size: Decimal) -> str:
        raise WritePathDisabled(f"{self.venue.value}: order entry disabled until Phase 4")

    async def cancel_order(self, order_id: str) -> None:
        raise WritePathDisabled(f"{self.venue.value}: order entry disabled until Phase 4")

    async def cancel_all(self) -> int:
        raise WritePathDisabled(f"{self.venue.value}: order entry disabled until Phase 4")
