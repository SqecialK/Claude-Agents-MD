import base64
from decimal import Decimal as D

from nacl.signing import SigningKey

from btcmm.adapters.polymarket_us import (
    PolymarketUSAdapter, PolymarketUSSigner, normalise_book, parse_event_markets, trade_aggressor,
)
from btcmm.data.models import SettlementKind
from tests.conftest import vcfg

EVENT = {
    "slug": "btc-updown-15m-1762000200", "title": "Bitcoin Up or Down - 15 min",
    "description": "Resolves Up if the Chainlink BTC/USD data stream price at the end of the window is greater "
                   "than or equal to the price at the start.",
    "startTime": "2026-11-01T12:00:00Z", "endTime": "2026-11-01T12:15:00Z",
    "series": {"slug": "btc-up-or-down-15m"},
    "markets": [{"slug": "btc-updown-15m-1762000200", "outcome": "Up", "active": True, "closed": False}],
}


def test_parse_event_point_rule_and_filters():
    [m] = parse_event_markets(EVENT, [5, 15])
    assert m.window_minutes == 15 and m.meta["up_is_long"] and m.meta["up_side_confident"]
    assert m.settlement.kind == SettlementKind.POINT and m.settlement.parsed_confidently
    assert parse_event_markets(EVENT, [5]) == []
    assert parse_event_markets({**EVENT, "title": "Ethereum Up or Down"}, [15]) == []


def test_book_inversion_when_long_is_down():
    md = {"bids": [{"px": {"value": "0.40", "currency": "USD"}, "qty": "10"}],
          "offers": [{"px": {"value": "0.45", "currency": "USD"}, "qty": "4"}]}
    assert normalise_book(md, True) == ([(D("0.40"), D(10))], [(D("0.45"), D(4))])
    # Long=Down: offer Down@0.45 == bid Up@0.55; bid Down@0.40 == ask Up@0.60
    assert normalise_book(md, False) == ([(D("0.55"), D(4))], [(D("0.60"), D(10))])


def test_trade_aggressor_intents():
    assert trade_aggressor({"intent": "ORDER_INTENT_BUY_LONG"}, True) == "buy"
    assert trade_aggressor({"intent": "ORDER_INTENT_BUY_SHORT"}, True) == "sell"
    assert trade_aggressor({"intent": "ORDER_INTENT_BUY_SHORT"}, False) == "buy"
    assert trade_aggressor({}, True) is None


def test_ws_market_data_is_full_snapshot():
    a = PolymarketUSAdapter(vcfg())
    ev = a.handle_ws_message({"requestId": "x", "subscriptionType": "SUBSCRIPTION_TYPE_MARKET_DATA",
                              "marketData": {"marketSlug": "s", "bids": [{"px": {"value": "0.5"}, "qty": "1"}],
                                             "offers": [{"px": {"value": "0.52"}, "qty": "2"}],
                                             "transactTime": "2026-11-01T12:00:00.123456789Z"}})
    assert ev.best_bid.price == D("0.5") and ev.exchange_ts.microsecond == 123456


def test_signer_ed25519_verifies():
    sk = SigningKey.generate()
    h = PolymarketUSSigner("kid", base64.b64encode(bytes(sk)).decode())("GET", "/v1/ws/markets")
    sk.verify_key.verify((h["X-PM-Timestamp"] + "GET/v1/ws/markets").encode(),
                         base64.b64decode(h["X-PM-Signature"]))
