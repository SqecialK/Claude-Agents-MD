from decimal import Decimal as D

from btcmm.adapters.gemini import GeminiAdapter, parse_events, parse_settlements
from btcmm.data.models import SettlementKind
from tests.conftest import vcfg

EVENTS = {"data": [
    {"ticker": "BTC15M2611011200", "title": "Bitcoin Up or Down 15 min",
     "description": "Resolves Up if the Gemini BTC/USD exchange price at expiry is greater than or equal to the price at open.",
     "effectiveDate": "2026-11-01T12:00:00Z", "expiryDate": "2026-11-01T12:15:00Z",
     "contracts": [{"label": "Up", "instrumentSymbol": "GEMI-BTC15M-UP-2611011215", "status": "active"},
                   {"label": "Down", "instrumentSymbol": "GEMI-BTC15M-DN-2611011215", "status": "active"}]},
    {"ticker": "X", "title": "Bitcoin Up or Down 5 min", "effectiveDate": "2026-11-01T12:00:00Z",
     "expiryDate": "2026-11-01T12:05:00Z", "contracts": [{"label": "Up"}]},  # no instrumentSymbol -> skipped
    {"ticker": "Y", "title": "Fed decision", "contracts": []},
], "pagination": {"limit": 100, "offset": 0}}


def test_parse_events_uses_instrument_symbol_only():
    ms = parse_events(EVENTS, [5, 15])
    assert [m.market_id for m in ms] == ["GEMI-BTC15M-UP-2611011215"]
    m = ms[0]
    assert m.window_minutes == 15 and m.settlement.kind == SettlementKind.POINT
    assert m.settlement.reference_index == "Gemini BTCUSD" and m.settlement.parsed_confidently


def test_ws_l2_snapshot_then_updates():
    a, books = GeminiAdapter(vcfg()), {}
    [s] = a.handle_ws_message({"type": "l2_updates", "symbol": "S",
                               "changes": [["buy", "0.40", "10"], ["sell", "0.45", "3"]]}, books)
    assert s.best_bid.price == D("0.40")
    out = a.handle_ws_message({"type": "l2_updates", "symbol": "S", "changes": [["sell", "0.45", "0"], ["sell", "0.47", "1"]],
                               "trades": [{"symbol": "S", "price": "0.45", "quantity": "3", "side": "buy", "timestamp": 1793534400000}]}, books)
    assert out[0].best_ask.price == D("0.47") and out[1].aggressor == "buy"


def test_settlement_parse():
    data = {"data": [{"contracts": [{"instrumentSymbol": "A", "resolutionSide": "yes"},
                                    {"instrumentSymbol": "B", "resolutionSide": "no"},
                                    {"instrumentSymbol": "C"}]}]}
    out = {s.market_id: s.value for s in parse_settlements(data, {"A", "B", "C"})}
    assert out == {"A": 1, "B": 0}
