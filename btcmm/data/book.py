"""Mutable L2 book with sequence-gap detection.

Adapters feed venue-native snapshot/delta messages into an ``L2Book`` after
converting prices to Up-contract dollars. The book enforces:

* deltas are only applied after a snapshot (``SequenceGap`` otherwise);
* if the venue provides sequence numbers, every delta must be exactly
  ``last_seq + 1`` - anything else raises ``SequenceGap`` and the adapter
  must resnapshot (spec: MARKET DATA, gap checks and resnapshot);
* crossed books after an update are treated as corruption and also force a
  resnapshot (a crossed book on a single venue is a data error, not edge).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from btcmm.config import Venue
from btcmm.data.models import BookLevel, BookSnapshot


class SequenceGap(Exception):
    """Raised when book integrity can no longer be trusted. Caller must resnapshot."""


class L2Book:
    def __init__(self, venue: Venue, market_id: str) -> None:
        self.venue = venue
        self.market_id = market_id
        self._bids: dict[Decimal, Decimal] = {}
        self._asks: dict[Decimal, Decimal] = {}
        self.seq: int | None = None
        self.initialized = False
        self.last_exchange_ts: datetime | None = None
        self.last_recv_ts: datetime | None = None

    def apply_snapshot(
        self,
        bids: list[tuple[Decimal, Decimal]],
        asks: list[tuple[Decimal, Decimal]],
        *,
        seq: int | None,
        exchange_ts: datetime | None,
        recv_ts: datetime,
    ) -> None:
        self._bids = {p: s for p, s in bids if s > 0}
        self._asks = {p: s for p, s in asks if s > 0}
        self.seq = seq
        self.initialized = True
        self.last_exchange_ts = exchange_ts
        self.last_recv_ts = recv_ts
        self._check_crossed()

    def apply_delta(
        self,
        side: str,
        price: Decimal,
        *,
        size: Decimal | None = None,
        delta: Decimal | None = None,
        seq: int | None,
        exchange_ts: datetime | None,
        recv_ts: datetime,
    ) -> None:
        """Apply one level change. Exactly one of ``size`` (absolute) or
        ``delta`` (relative, Kalshi-style) must be given."""
        if not self.initialized:
            raise SequenceGap(f"{self.venue.value}:{self.market_id} delta before snapshot")
        if seq is not None and self.seq is not None and seq != self.seq + 1:
            raise SequenceGap(
                f"{self.venue.value}:{self.market_id} seq gap: have {self.seq}, got {seq}"
            )
        if (size is None) == (delta is None):
            raise ValueError("exactly one of size/delta required")
        levels = self._bids if side == "bid" else self._asks
        if side not in ("bid", "ask"):
            raise ValueError(f"bad side {side!r}")
        new = size if size is not None else levels.get(price, Decimal(0)) + delta  # type: ignore[operator]
        if new < 0:
            raise SequenceGap(
                f"{self.venue.value}:{self.market_id} negative size at {price}: book out of sync"
            )
        if new == 0:
            levels.pop(price, None)
        else:
            levels[price] = new
        if seq is not None:
            self.seq = seq
        self.last_exchange_ts = exchange_ts
        self.last_recv_ts = recv_ts
        self._check_crossed()

    def _check_crossed(self) -> None:
        if self._bids and self._asks and max(self._bids) >= min(self._asks):
            self.initialized = False
            raise SequenceGap(
                f"{self.venue.value}:{self.market_id} crossed book "
                f"bid={max(self._bids)} ask={min(self._asks)}"
            )

    def snapshot(self, source: str = "ws") -> BookSnapshot:
        assert self.last_recv_ts is not None
        return BookSnapshot(
            venue=self.venue,
            market_id=self.market_id,
            bids=[BookLevel(price=p, size=s) for p, s in sorted(self._bids.items(), reverse=True)],
            asks=[BookLevel(price=p, size=s) for p, s in sorted(self._asks.items())],
            exchange_ts=self.last_exchange_ts,
            recv_ts=self.last_recv_ts,
            seq=self.seq,
            source=source,
        )
