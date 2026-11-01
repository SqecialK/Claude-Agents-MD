"""Feed staleness and latency tracking.

* Staleness: time since the last message per source. In trading modes a
  stale pricing input cancels that venue's quotes (Phase 4 wires the action);
  here we measure and record it.
* Latency: ``recv_ts - exchange_ts`` per source (exchange-to-us), tracked as
  rolling percentiles. Negative values indicate clock skew between us and the
  venue and are reported, not clipped.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any


class FeedHealth:
    def __init__(self, staleness_limit_ms: float, window: int = 2000) -> None:
        self.staleness_limit_ms = staleness_limit_ms
        self._last: dict[str, datetime] = {}
        self._lat: dict[str, deque[float]] = {}
        self._window = window
        self.counts: dict[str, int] = {}

    def observe(self, source: str, recv_ts: datetime, exchange_ts: datetime | None) -> None:
        self._last[source] = recv_ts
        self.counts[source] = self.counts.get(source, 0) + 1
        if exchange_ts is not None:
            self._lat.setdefault(source, deque(maxlen=self._window)).append(
                (recv_ts - exchange_ts).total_seconds() * 1000.0
            )

    def staleness_ms(self, source: str, now: datetime) -> float | None:
        last = self._last.get(source)
        return None if last is None else (now - last).total_seconds() * 1000.0

    def is_stale(self, source: str, now: datetime) -> bool:
        s = self.staleness_ms(source, now)
        return s is None or s > self.staleness_limit_ms

    def latency_pcts(self, source: str) -> dict[str, float] | None:
        xs = sorted(self._lat.get(source) or [])
        if not xs:
            return None

        def q(p: float) -> float:
            return xs[min(len(xs) - 1, int(p * (len(xs) - 1) + 0.5))]

        return {"p50": q(0.5), "p90": q(0.9), "p99": q(0.99), "min": xs[0], "n": float(len(xs))}

    def snapshot(self, now: datetime) -> dict[str, Any]:
        return {
            src: {
                "staleness_ms": self.staleness_ms(src, now),
                "count": self.counts.get(src, 0),
                "latency_ms": self.latency_pcts(src),
            }
            for src in sorted(self._last)
        }
