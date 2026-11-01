import base64
from decimal import Decimal as D

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from btcmm.adapters.base import WritePathDisabled, OrderRequest
from btcmm.adapters.kalshi import KalshiAdapter, KalshiSigner, parse_book_sides, parse_market, parse_settlement
from btcmm.data.book import SequenceGap
from btcmm.data.models import BookSnapshot, SettlementKind, TradePrint
from tests.conftest import vcfg

MARKET = {
    "ticker": "KXBTC15M-26NOV011215-15", "event_ticker": "KXBTC15M-26NOV011215",
    "title": "BTC price up in next 15 mins?", "status": "active",
    "open_time": "2026-11-01T12:00:00Z", "close_time": "2026-11-01T12:15:00Z",
    "rules_primary": "If the simple average of the sixty seconds of CF Benchmarks' Bitcoin Real-Time Index "
                     "(BRTI) prior to 12:15 PM ET is greater than or equal to the 60 second average before "
                     "12:00 PM ET, then the market resolves to Yes.",
    "rules_secondary": "", "floor_strike": 97000.12,
    "price_ranges": [{"start": "0.01", "end": "0.99", "step": "0.01"}],
    "fee_waiver_expiration_time": None,
}


def test_parse_market_and_averaged_rule():
    m = parse_market(MARKET, "KXBTC15M")
    assert m.window_minutes == 15 and m.series_id == "KXBTC15M"
    assert m.settlement.kind == SettlementKind.AVERAGED
    assert m.settlement.averaging_seconds == 60
    assert m.settlement.reference_index == "CF Benchmarks BRTI"
    assert m.settlement.parsed_confidently
    assert m.tick_ranges[0].step == D("0.01")


def test_unrecognised_rule_not_confident():
    m = parse_market({**MARKET, "rules_primary": "Resolves Yes if BTC goes up."}, "KXBTC15M")
    assert m.settlement.kind == SettlementKind.POINT and not m.settlement.parsed_confidently


def test_book_normalisation_dollars_and_legacy_cents():
    bids, asks = parse_book_sides({"yes_dollars": [["0.4200", "10.00"]], "no_dollars": [["0.5500", "3.50"]]})
    assert bids == [(D("0.4200"), D("10.00"))]
    assert asks == [(D("0.4500"), D("3.50"))]  # NO bid 0.55 == Up ask 0.45
    bids, asks = parse_book_sides({"yes": [[42, 10]], "no": [[55, 3]]})
    assert bids == [(D("0.42"), D(10))] and asks == [(D("0.45"), D(3))]


def ad():
    return KalshiAdapter(vcfg())


def test_ws_snapshot_delta_trade_and_gap():
    a, books, seqs = ad(), {}, {}
    snap = a.handle_ws_message({"type": "orderbook_snapshot", "sid": 1, "seq": 1, "msg": {
        "market_ticker": "M", "yes_dollars": [["0.40", "10"]], "no_dollars": [["0.55", "5"]]}}, books, seqs)
    assert isinstance(snap, BookSnapshot) and snap.best_ask.price == D("0.45")
    ev = a.handle_ws_message({"type": "orderbook_delta", "sid": 1, "seq": 2, "msg": {
        "market_ticker": "M", "price_dollars": "0.57", "delta_fp": "2", "side": "no"}}, books, seqs)
    assert ev.best_ask.price == D("0.43")
    tr = a.handle_ws_message({"type": "trade", "msg": {"market_ticker": "M", "yes_price_dollars": "0.43",
                              "count_fp": "1.00", "taker_side": "yes", "ts": 1793534400}}, books, seqs)
    assert isinstance(tr, TradePrint) and tr.aggressor == "buy"
    with pytest.raises(SequenceGap):
        a.handle_ws_message({"type": "orderbook_delta", "sid": 1, "seq": 4, "msg": {
            "market_ticker": "M", "price_dollars": "0.40", "delta_fp": "1", "side": "yes"}}, books, seqs)


def test_settlement_parse():
    sv = parse_settlement({**MARKET, "status": "settled", "result": "no", "expiration_value": "96950.1"})
    assert sv.value == 0 and sv.reference_end == D("96950.1")
    assert parse_settlement({**MARKET, "status": "active"}) is None


def test_signer_rsa_pss_verifies():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    h = KalshiSigner("kid", pem)("GET", "/trade-api/v2/portfolio/balance?x=1")
    msg = (h["KALSHI-ACCESS-TIMESTAMP"] + "GET" + "/trade-api/v2/portfolio/balance").encode()
    key.public_key().verify(base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"]), msg,
                            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                            hashes.SHA256())


async def test_write_paths_disabled():
    a = ad()
    with pytest.raises(WritePathDisabled):
        await a.place_order(OrderRequest(market_id="M", side="buy_up", price=D("0.4"), size=D(1), client_order_id="x"))
    with pytest.raises(WritePathDisabled):
        await a.cancel_all()
    await a.aclose()
