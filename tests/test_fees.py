from decimal import Decimal as D

import pytest

from btcmm.adapters.kalshi import fee_schedule_from_series
from btcmm.config import FeeOverride
from btcmm.model.fees import (
    deterministic_rebate, fee_rounding_overhead, min_size_for_overhead, net_maker_cost, order_fee, round_up_to,
)
from tests.conftest import sched, vcfg


def kalshi(fee_type="quadratic", mult=1):
    return fee_schedule_from_series({"ticker": "KXBTC15M", "fee_type": fee_type, "fee_multiplier": mult},
                                    vcfg(fees=FeeOverride(taker_coef=D("0.07"))))


def test_round_up_exact():
    assert round_up_to(D("0.0175"), D("0.01")) == D("0.02")
    assert round_up_to(D("1.75"), D("0.01")) == D("1.75")
    assert round_up_to(D("0.0100"), D("0.01")) == D("0.01")


@pytest.mark.parametrize("c,p,expected", [
    ("1", "0.50", "0.02"),    # 0.0175 -> 0.02 (rounding surcharge 14%)
    ("100", "0.50", "1.75"),  # exact
    ("10", "0.30", "0.15"),   # 0.147 -> 0.15
    ("1", "0.01", "0.01"),    # 0.000693 -> 0.01 : rounding dominates at extremes
    ("5", "0.99", "0.01"),
    ("0", "0.50", "0.00"),
])
def test_kalshi_taker_fee_rounds_up_per_order(c, p, expected):
    assert order_fee(kalshi(), D(c), D(p), maker=False) == D(expected)


def test_kalshi_maker_zero_unless_fee_type_has_maker_fees():
    assert order_fee(kalshi("quadratic"), D(100), D("0.5"), maker=True) == 0
    s = kalshi("quadratic_with_maker_fees")
    assert s.maker_coef == D("0.0175")
    assert order_fee(s, D(100), D("0.5"), maker=True) == D("0.44")  # 0.4375 -> 0.44
    assert kalshi("quadratic_with_combo_maker_fees").maker_coef == D("0.035")


def test_kalshi_fee_multiplier_scales():
    s = kalshi(mult=2)
    assert s.taker_coef == D("0.14")
    assert order_fee(s, D(100), D("0.5"), maker=False) == D("3.50")


def test_kalshi_flat_fee_type_refused():
    with pytest.raises(ValueError):
        kalshi("flat")


def test_gemini_quadratic_maker_and_taker():
    s = sched()
    assert order_fee(s, D(100), D("0.5"), maker=False) == D("1.75")
    assert order_fee(s, D(100), D("0.5"), maker=True) == D("0.44")
    assert order_fee(s, D(10), D("0.2"), maker=True) == D("0.03")  # 0.028 -> 0.03


def test_deterministic_rebate_rounds_down_and_nets():
    s = sched(maker="0", rebate="0.0125")
    assert deterministic_rebate(s, D(100), D("0.5")) == D("0.31")  # 0.3125 -> 0.31 (conservative)
    assert net_maker_cost(s, D(100), D("0.5")) == D("-0.31")
    assert deterministic_rebate(sched(), D(100), D("0.5")) == 0


def test_price_bounds_enforced():
    with pytest.raises(ValueError):
        order_fee(sched(), D(1), D("1.2"), maker=False)
    with pytest.raises(ValueError):
        order_fee(sched(), D(-1), D("0.5"), maker=False)


def test_rounding_overhead_and_min_size():
    s = kalshi()
    assert fee_rounding_overhead(s, D(1), D("0.5"), maker=False) == D("0.0025")
    size = min_size_for_overhead(s, D("0.5"), maker=False, max_overhead_per_contract=D("0.0005"))
    assert size is not None
    assert fee_rounding_overhead(s, size, D("0.5"), maker=False) <= D("0.0005")
    # 4 contracts at 0.5: raw 0.07 exactly
    assert order_fee(s, D(4), D("0.5"), maker=False) == D("0.07")
