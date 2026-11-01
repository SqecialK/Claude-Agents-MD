"""Multi-venue data recorder.

Records, per venue: discovered markets (with parsed settlement rules), fee
schedules, normalised Up-contract books, trades, feed-health events, periodic
REST reconciliation snapshots and official settlement values. Plus spot
feeds and clock-offset measurements.

Storage: gzip-compressed JSON Lines, one directory per stream, rotated
hourly::

    <out_dir>/<YYYY-MM-DD>/<stream>/<HH>.jsonl.gz

Gzip members are appended and flushed periodically, so a crash loses at most
``flush_interval_s`` of data and the files stay readable (multi-member gzip).
Every record carries ``recv_ts`` (local, UTC) and, where the venue provides
it, ``exchange_ts``. Conversion to Parquet is a later batch step.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import IO, Any

from pydantic import BaseModel

from btcmm.adapters.base import ExchangeAdapter
from btcmm.config import AppConfig, Venue, VenueMode
from btcmm.data.models import BookSnapshot, FeedStatus, Market, SpotTick, TradePrint, utcnow
from btcmm.data.spot import feed_spec, stream_spot
from btcmm.monitoring.clock import check_clock_async
from btcmm.monitoring.health import FeedHealth

log = logging.getLogger(__name__)
BOOK_DEPTH = 10  # levels per side kept in recorded snapshots


class JsonlWriter:
    """Hourly-rotating gzip JSONL writer, one file handle per stream."""

    def __init__(self, root: Path, rotate_seconds: int = 3600) -> None:
        self.root = Path(root)
        self.rotate_seconds = rotate_seconds
        self._fh: dict[str, tuple[int, IO[str]]] = {}
        self.records_written = 0

    def _path(self, stream: str, bucket: int) -> Path:
        dt = datetime.fromtimestamp(bucket * self.rotate_seconds, tz=timezone.utc)
        return self.root / dt.strftime("%Y-%m-%d") / stream / f"{dt.strftime('%H%M')}.jsonl.gz"

    def write(self, stream: str, record: dict[str, Any] | BaseModel) -> None:
        if isinstance(record, BaseModel):
            record = record.model_dump(mode="json")
        bucket = int(time.time() // self.rotate_seconds)
        cur = self._fh.get(stream)
        if cur is None or cur[0] != bucket:
            if cur is not None:
                cur[1].close()
            p = self._path(stream, bucket)
            p.parent.mkdir(parents=True, exist_ok=True)
            self._fh[stream] = (bucket, gzip.open(p, "at", encoding="utf-8"))
        self._fh[stream][1].write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
        self.records_written += 1

    def flush(self) -> None:
        for _, fh in self._fh.values():
            fh.flush()

    def close(self) -> None:
        for _, fh in self._fh.values():
            fh.close()
        self._fh.clear()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _trim(b: BookSnapshot) -> dict[str, Any]:
    d = b.model_dump(mode="json")
    d["bids"] = d["bids"][:BOOK_DEPTH]
    d["asks"] = d["asks"][:BOOK_DEPTH]
    return d


class VenueRecorder:
    """Discovery -> stream -> reconcile -> settle loop for one venue."""

    def __init__(self, adapter: ExchangeAdapter, writer: JsonlWriter, health: FeedHealth, cfg: AppConfig) -> None:
        self.a = adapter
        self.w = writer
        self.health = health
        self.cfg = cfg
        self.vcfg = cfg.venues[adapter.venue]
        self.v = adapter.venue.value
        self.markets: dict[str, Market] = {}
        self.pending_settlement: dict[str, Market] = {}
        self.last_book: dict[str, BookSnapshot] = {}
        self._stream_task: asyncio.Task[None] | None = None
        self._streaming: tuple[str, ...] = ()
        adapter.on_status(self._on_status)

    def _on_status(self, st: FeedStatus) -> None:
        self.w.write(f"{self.v}/status", st)

    def _active_ids(self, now: datetime) -> tuple[str, ...]:
        # Stream markets from shortly before open until close.
        lead = timedelta(minutes=1)
        return tuple(sorted(
            mid for mid, m in self.markets.items()
            if m.window_start - lead <= now < m.window_end
            or (m.window_start > now and m.window_start - now < timedelta(minutes=16))
        ))

    async def _record_new_market(self, m: Market) -> None:
        self.w.write(f"{self.v}/markets", m)
        if not m.settlement.parsed_confidently:
            self.w.write(f"{self.v}/status", FeedStatus(
                source=self.v, event="settlement_rule_unverified",
                detail=f"{m.market_id}: kind={m.settlement.kind.value} ref={m.settlement.reference_index}"))
        try:
            fs = await self.a.get_fee_schedule(m)
            self.w.write(f"{self.v}/fees", {"market_id": m.market_id, **fs.model_dump(mode="json")})
        except Exception as e:  # noqa: BLE001 - fee failures are recorded, never guessed
            self.w.write(f"{self.v}/status", FeedStatus(source=self.v, event="fee_error", detail=f"{m.market_id}: {e}"))

    async def _consume(self, ids: list[str], stop: asyncio.Event) -> None:
        async for ev in self.a.stream_book(ids, stop):
            if isinstance(ev, BookSnapshot):
                self.last_book[ev.market_id] = ev
                self.health.observe(f"{self.v}:book", ev.recv_ts, ev.exchange_ts)
                self.w.write(f"{self.v}/book", _trim(ev))
            elif isinstance(ev, TradePrint):
                self.health.observe(f"{self.v}:trade", ev.recv_ts, ev.exchange_ts)
                self.w.write(f"{self.v}/trades", ev)
            elif isinstance(ev, FeedStatus):
                self.w.write(f"{self.v}/status", ev)

    async def _restart_stream(self, ids: tuple[str, ...], stop: asyncio.Event) -> None:
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._streaming = ids
        self._stream_task = asyncio.create_task(self._consume(list(ids), stop)) if ids else None

    async def discovery_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                found = await self.a.discover_markets()
                for m in found:
                    if m.market_id not in self.markets:
                        self.markets[m.market_id] = m
                        await self._record_new_market(m)
            except Exception as e:  # noqa: BLE001
                log.warning("%s discovery failed: %s", self.v, e)
                self.w.write(f"{self.v}/status", FeedStatus(source=self.v, event="discovery_error", detail=str(e)))
            now = utcnow()
            for mid, m in list(self.markets.items()):
                if m.window_end <= now:
                    self.pending_settlement[mid] = self.markets.pop(mid)
                    self.last_book.pop(mid, None)
            ids = self._active_ids(now)
            if ids != self._streaming:
                await self._restart_stream(ids, stop)
            await _sleep(stop, self.vcfg.discovery_interval_s)
        await self._restart_stream((), stop)

    async def reconcile_loop(self, stop: asyncio.Event) -> None:
        """Periodic REST snapshot alongside the stream. A top-of-book mismatch
        vs the streamed book is logged as ``reconcile_mismatch`` (in trading
        modes this trips a circuit breaker)."""
        while not stop.is_set():
            await _sleep(stop, self.vcfg.rest_reconcile_interval_s)
            for mid in list(self._streaming):
                try:
                    snap = await self.a.get_book(mid)
                except Exception as e:  # noqa: BLE001
                    self.w.write(f"{self.v}/status", FeedStatus(source=self.v, event="reconcile_error", detail=f"{mid}: {e}"))
                    continue
                self.w.write(f"{self.v}/book_reconcile", _trim(snap))
                live = self.last_book.get(mid)
                if live and (_top(live) != _top(snap)):
                    self.w.write(f"{self.v}/status", FeedStatus(
                        source=self.v, event="reconcile_mismatch",
                        detail=f"{mid}: stream={_top(live)} rest={_top(snap)} age_ms="
                               f"{(snap.recv_ts - live.recv_ts).total_seconds() * 1000:.0f}"))

    async def settlement_loop(self, stop: asyncio.Event) -> None:
        give_up = timedelta(hours=24)
        while not stop.is_set():
            await _sleep(stop, self.cfg.recorder.settlement_poll_interval_s)
            if not self.pending_settlement:
                continue
            try:
                vals = await self.a.get_settlement_values(list(self.pending_settlement))
            except Exception as e:  # noqa: BLE001
                self.w.write(f"{self.v}/status", FeedStatus(source=self.v, event="settlement_error", detail=str(e)))
                continue
            for sv in vals:
                self.w.write(f"{self.v}/settlements", sv)
                self.pending_settlement.pop(sv.market_id, None)
            now = utcnow()
            for mid, m in list(self.pending_settlement.items()):
                if now - m.window_end > give_up:
                    self.w.write(f"{self.v}/status", FeedStatus(source=self.v, event="settlement_timeout", detail=mid))
                    self.pending_settlement.pop(mid)


def _top(b: BookSnapshot) -> tuple[str | None, str | None]:
    return (str(b.best_bid.price) if b.best_bid else None, str(b.best_ask.price) if b.best_ask else None)


async def _sleep(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


class Recorder:
    """Top-level orchestrator. Runnable on its own: ``btcmm record``."""

    def __init__(self, cfg: AppConfig, adapters: list[ExchangeAdapter]) -> None:
        self.cfg = cfg
        self.adapters = [a for a in adapters if cfg.venues[a.venue].mode != VenueMode.OFF]
        self.writer = JsonlWriter(cfg.recorder.out_dir, cfg.recorder.rotate_seconds)
        self.health = FeedHealth(cfg.spot.staleness_limit_ms)
        self.stop = asyncio.Event()

    async def _spot(self, name: str) -> None:
        gem_ws = self.cfg.venues[Venue.GEMINI].ws_url
        async for ev in stream_spot(feed_spec(name, gemini_ws_url=gem_ws), self.stop,
                                   on_status=lambda st: self.writer.write("spot/status", st)):
            if isinstance(ev, SpotTick):
                self.health.observe(f"spot:{ev.source}", ev.recv_ts, ev.exchange_ts)
                self.writer.write(f"spot/{name}", ev)
            else:
                self.writer.write("spot/status", ev)

    async def _clock_loop(self) -> None:
        while not self.stop.is_set():
            rep = await check_clock_async(self.cfg.clock.ntp_servers, self.cfg.clock.max_drift_ms)
            self.writer.write("system/clock", {"recv_ts": utcnow().isoformat(), "ok": rep.ok, **rep.__dict__})
            if not rep.ok:
                log.warning("CLOCK: %s", rep.describe())
                if self.cfg.clock.block_recording_on_drift:
                    log.error("clock drift beyond limit and block_recording_on_drift=true: stopping")
                    self.stop.set()
            await _sleep(self.stop, self.cfg.clock.check_interval_s)

    async def _flush_loop(self) -> None:
        while not self.stop.is_set():
            await _sleep(self.stop, self.cfg.recorder.flush_interval_s)
            self.writer.flush()

    async def _health_loop(self) -> None:
        while not self.stop.is_set():
            await _sleep(self.stop, 10.0)
            now = utcnow()
            self.writer.write("system/health", {"recv_ts": now.isoformat(), "feeds": self.health.snapshot(now)})

    async def run(self) -> None:
        tasks: list[asyncio.Task[Any]] = [
            asyncio.create_task(self._clock_loop()),
            asyncio.create_task(self._flush_loop()),
            asyncio.create_task(self._health_loop()),
        ]
        for f in self.cfg.spot.feeds:
            if f.enabled:
                tasks.append(asyncio.create_task(self._spot(f.name)))
        if self.cfg.spot.chainlink_enabled:
            # Chainlink Data Streams need a client id/secret and a report-decoding
            # SDK; not wired in Phase 1. We record that the PM US proxy is a composite.
            self.writer.write("spot/status", FeedStatus(source="spot:chainlink", event="not_implemented",
                                                        detail="Chainlink Data Streams client not wired yet"))
        for a in self.adapters:
            vr = VenueRecorder(a, self.writer, self.health, self.cfg)
            tasks += [asyncio.create_task(vr.discovery_loop(self.stop)),
                      asyncio.create_task(vr.reconcile_loop(self.stop)),
                      asyncio.create_task(vr.settlement_loop(self.stop))]
        try:
            await self.stop.wait()
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for a in self.adapters:
                await a.aclose()
            self.writer.close()
