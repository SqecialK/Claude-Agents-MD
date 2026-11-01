from datetime import timedelta
from decimal import Decimal as D

from btcmm.data.spot import GeminiSpotParser, parse_bitstamp, parse_coinbase, parse_kraken
from btcmm.data.models import utcnow
from btcmm.monitoring.clock import ClockReport, _to_ntp, build_request, compute_offset, parse_chrony_tracking
from btcmm.monitoring.health import FeedHealth


def test_spot_parsers():
    t = parse_coinbase({"type": "ticker", "product_id": "BTC-USD", "price": "97000.01", "best_bid": "97000",
                        "best_ask": "97000.02", "time": "2026-11-01T12:00:00.123456Z"})
    assert t.price == D("97000.01") and t.exchange_ts is not None
    assert parse_coinbase({"type": "subscriptions"}) is None
    [k] = parse_kraken({"channel": "ticker", "type": "update", "data": [{"symbol": "BTC/USD", "last": 97001, "bid": 97000.5, "ask": 97001.5}]})
    assert k.price == D("97001")
    b = parse_bitstamp({"event": "trade", "data": {"price": 97002, "amount": 0.1, "microtimestamp": "1793534400123456"}})
    assert b.exchange_ts.year == 2026
    g = GeminiSpotParser()
    assert g({"type": "l2_updates", "changes": [["buy", "97000", "1"]]}) == []
    [m] = g({"type": "l2_updates", "changes": [["sell", "97002", "1"]]})
    assert m.price == D("97001")


def test_ntp_offset_math():
    t1, server, t4 = 1000.0, 1000.250, 1000.100  # server clock 0.2s ahead, 0.1s RTT
    resp = bytearray(48)
    resp[0] = (4 << 3) | 4
    resp[1] = 2
    resp[32:40] = _to_ntp(server)
    resp[40:48] = _to_ntp(server)
    off = compute_offset(bytes(resp), t1, t4)
    assert abs(off - 0.200) < 1e-6
    assert build_request(t1)[0] & 0x7 == 3


def test_chrony_parse_and_report():
    assert abs(parse_chrony_tracking("System time     : 0.000250000 seconds slow of NTP time") - 0.25) < 1e-9
    assert parse_chrony_tracking("System time     : 0.5 seconds fast of NTP time") == -500.0
    assert ClockReport(5.0, 3, 3, None, False, 100).ok
    assert not ClockReport(150.0, 3, 3, None, False, 100).ok
    assert not ClockReport(None, 0, 3, None, False, 100).ok  # unknown == unsafe


def test_feed_health_staleness_latency():
    h = FeedHealth(500)
    now = utcnow()
    h.observe("x", now, now - timedelta(milliseconds=40))
    assert not h.is_stale("x", now + timedelta(milliseconds=100))
    assert h.is_stale("x", now + timedelta(milliseconds=600))
    assert h.is_stale("never", now)
    assert abs(h.latency_pcts("x")["p50"] - 40) < 1e-6
