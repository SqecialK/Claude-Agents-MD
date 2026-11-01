"""SimulatedAdapter: serves any venue's data from memory or recordings.

Phase 1 scope: read paths only, so the core (and tests) can run against
deterministic data with exactly the same interface as a live adapter. The
queue-position fill model and write paths arrive in Phase 3/4; until then
order entry raises ``WritePathDisabled`` like every other adapter.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from btcmm.adapters.base import BookEvent, ExchangeAdapter
from btcmm.config import Venue, VenueConfig, VenueMode
from btcmm.data.models import (
    BookSnapshot,
    FeedStatus,
    FeeSchedule,
    Market,
    SettlementRule,
    SettlementValue,
    TradePrint,
)
from btcmm.data.recorder import read_jsonl


class SimulatedAdapter(ExchangeAdapter):
    def __init__(
        self,
        venue: Venue,
        *,
        markets: list[Market],
        events: list[BookEvent],
        fee_schedule: FeeSchedule,
        settlements: list[SettlementValue] | None = None,
        cfg: VenueConfig | None = None,
    ) -> None:
        super().__init__(cfg or VenueConfig(mode=VenueMode.RECORD, rest_base_url="sim://", ws_url="sim://"))
        self.venue = venue  # type: ignore[misc]
        self._markets = {m.market_id: m for m in markets}
        self._events = sorted(events, key=lambda e: e.recv_ts)
        self._fees = fee_schedule
        self._settlements = {s.market_id: s for s in settlements or []}

    @classmethod
    def from_recording(cls, root: Path, venue: Venue, fee_schedule: FeeSchedule) -> SimulatedAdapter:
        """Load a recorder output directory for one venue."""
        markets: list[Market] = []
        events: list[BookEvent] = []
        settles: list[SettlementValue] = []
        v = venue.value
        for p in sorted(Path(root).glob(f"*/{v}/markets/*.jsonl.gz")):
            markets += [Market.model_validate(r) for r in read_jsonl(p)]
        for p in sorted(Path(root).glob(f"*/{v}/book/*.jsonl.gz")):
            events += [BookSnapshot.model_validate(r) for r in read_jsonl(p)]
        for p in sorted(Path(root).glob(f"*/{v}/trades/*.jsonl.gz")):
            events += [TradePrint.model_validate(r) for r in read_jsonl(p)]
        for p in sorted(Path(root).glob(f"*/{v}/settlements/*.jsonl.gz")):
            settles += [SettlementValue.model_validate(r) for r in read_jsonl(p)]
        return cls(venue, markets=markets, events=events, fee_schedule=fee_schedule, settlements=settles)

    async def discover_markets(self) -> list[Market]:
        return list(self._markets.values())

    async def stream_book(self, market_ids: list[str], stop: asyncio.Event) -> AsyncIterator[BookEvent]:
        want = set(market_ids)
        for ev in self._events:
            if stop.is_set():
                return
            if isinstance(ev, FeedStatus) or ev.market_id in want:
                yield ev

    async def get_book(self, market_id: str) -> BookSnapshot:
        last = None
        for ev in self._events:
            if isinstance(ev, BookSnapshot) and ev.market_id == market_id:
                last = ev
        if last is None:
            raise KeyError(market_id)
        return last

    async def get_fee_schedule(self, market: Market) -> FeeSchedule:
        return self._fees

    def get_settlement_rule(self, market: Market) -> SettlementRule:
        return market.settlement

    async def get_settlement_values(self, market_ids: list[str]) -> list[SettlementValue]:
        return [self._settlements[m] for m in market_ids if m in self._settlements]
