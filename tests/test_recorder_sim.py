import asyncio
from datetime import timedelta
from decimal import Decimal as D

import pytest

from btcmm.adapters.base import OrderRequest, WritePathDisabled
from btcmm.adapters.simulated import SimulatedAdapter
from btcmm.config import AppConfig, Venue, load_config
from btcmm.data.models import (BookLevel, BookSnapshot, Market, SettlementKind, SettlementRule, SettlementValue,
                               TradePrint, utcnow)
from btcmm.data.recorder import JsonlWriter, VenueRecorder, read_jsonl
from btcmm.monitoring.health import FeedHealth
from tests.conftest import sched
from tests.test_config import DEFAULT


def fixture_adapter():
    now = utcnow()
    live = Market(venue=Venue.GEMINI, market_id="LIVE", window_start=now - timedelta(minutes=1),
                  window_end=now + timedelta(minutes=4), window_minutes=5,
                  settlement=SettlementRule(kind=SettlementKind.POINT, reference_index="Gemini BTCUSD",
                                            parsed_confidently=True))
    done = live.model_copy(update={"market_id": "DONE", "window_start": now - timedelta(minutes=10),
                                   "window_end": now - timedelta(minutes=5)})
    events = [
        BookSnapshot(venue=Venue.GEMINI, market_id="LIVE", bids=[BookLevel(price=D("0.48"), size=D(5))],
                     asks=[BookLevel(price=D("0.52"), size=D(5))], exchange_ts=None, recv_ts=now),
        TradePrint(venue=Venue.GEMINI, market_id="LIVE", price=D("0.52"), size=D(1), aggressor="buy",
                   exchange_ts=None, recv_ts=now),
    ]
    settles = [SettlementValue(venue=Venue.GEMINI, market_id="DONE", value=D(1), recv_ts=now)]
    return SimulatedAdapter(Venue.GEMINI, markets=[live, done], events=events, fee_schedule=sched(),
                            settlements=settles)


def cfg_for(tmp_path) -> AppConfig:
    cfg = load_config(DEFAULT)
    cfg.recorder.out_dir = tmp_path
    cfg.recorder.settlement_poll_interval_s = 0.05
    for v in cfg.venues.values():
        v.discovery_interval_s = 0.05
        v.rest_reconcile_interval_s = 0.05
    return cfg


async def test_venue_recorder_end_to_end(tmp_path):
    cfg = cfg_for(tmp_path)
    w = JsonlWriter(tmp_path)
    vr = VenueRecorder(fixture_adapter(), w, FeedHealth(500), cfg)
    stop = asyncio.Event()
    tasks = [asyncio.create_task(c(stop)) for c in (vr.discovery_loop, vr.reconcile_loop, vr.settlement_loop)]
    await asyncio.sleep(0.4)
    stop.set()
    await asyncio.gather(*tasks)
    w.close()
    streams = {p.parent.name: read_jsonl(p) for p in tmp_path.glob("*/gemini/*/*.jsonl.gz")}
    assert {m["market_id"] for m in streams["markets"]} == {"LIVE", "DONE"}
    assert streams["book"][0]["market_id"] == "LIVE"
    assert streams["trades"][0]["aggressor"] == "buy"
    assert streams["settlements"][0]["market_id"] == "DONE" and streams["settlements"][0]["value"] == "1"
    assert streams["fees"][0]["taker_coef"] == "0.07"
    assert "book_reconcile" in streams


async def test_simulated_roundtrip_from_recording(tmp_path):
    await test_venue_recorder_end_to_end(tmp_path)
    sim = SimulatedAdapter.from_recording(tmp_path, Venue.GEMINI, sched())
    assert {m.market_id for m in await sim.discover_markets()} == {"LIVE", "DONE"}
    assert (await sim.get_book("LIVE")).best_bid.price == D("0.48")
    with pytest.raises(WritePathDisabled):
        await sim.place_order(OrderRequest(market_id="LIVE", side="buy_up", price=D("0.5"), size=D(1), client_order_id="c"))
