"""Exact per-venue fee arithmetic.

All three venues price fees on the same quadratic shape::

    raw_fee = coef * C * P * (1 - P)          (dollars)

which peaks at P = 0.5 and vanishes at the extremes. What differs is the
coefficient, whether makers pay, whether a deterministic rebate exists, and
how the result is rounded. Rounding matters enormously for small orders:
a 1-contract Kalshi taker order at P=0.50 has raw fee $0.0175 but is charged
$0.02 (a 14% surcharge on the fee). This is why the spec requires a
per-venue minimum order size "where fee rounding remains acceptable" -
see :func:`fee_rounding_overhead`.

Everything is ``Decimal``; floats are never used.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Decimal

from btcmm.data.models import FeeSchedule

ZERO = Decimal(0)
ONE = Decimal(1)


def round_up_to(value: Decimal, increment: Decimal) -> Decimal:
    """Round ``value`` up to the next multiple of ``increment`` (exact)."""
    if increment <= 0:
        return value
    units = (value / increment).to_integral_value(rounding=ROUND_CEILING)
    return units * increment


def raw_quadratic(coef: Decimal, contracts: Decimal, price: Decimal) -> Decimal:
    if not (ZERO <= price <= ONE):
        raise ValueError(f"price {price} outside [0,1]")
    if contracts < 0:
        raise ValueError("contracts must be non-negative")
    return coef * contracts * price * (ONE - price)


def order_fee(sched: FeeSchedule, contracts: Decimal, price: Decimal, *, maker: bool) -> Decimal:
    """Fee CHARGED for one order (or one fill when ``rounding_scope == 'fill'``)
    of ``contracts`` at ``price``. Rebates are NOT netted here - see
    :func:`deterministic_rebate`, so P&L lines stay separate."""
    coef = sched.maker_coef if maker else sched.taker_coef
    if coef == 0:
        return ZERO
    return round_up_to(raw_quadratic(coef, contracts, price), sched.rounding_increment)


def deterministic_rebate(sched: FeeSchedule, contracts: Decimal, price: Decimal) -> Decimal:
    """Deterministic per-fill maker rebate (counted in edge).

    Rebates are rounded DOWN (conservative: we never assume more rebate than
    could be paid). Discretionary programs are never included here.
    """
    if sched.maker_rebate_coef == 0:
        return ZERO
    raw = raw_quadratic(sched.maker_rebate_coef, contracts, price)
    inc = sched.rounding_increment
    if inc <= 0:
        return raw
    return (raw / inc).to_integral_value(rounding=ROUND_FLOOR) * inc


def net_maker_cost(sched: FeeSchedule, contracts: Decimal, price: Decimal) -> Decimal:
    """Maker fee minus deterministic rebate, in dollars (may be negative)."""
    return order_fee(sched, contracts, price, maker=True) - deterministic_rebate(
        sched, contracts, price
    )


def fee_rounding_overhead(
    sched: FeeSchedule, contracts: Decimal, price: Decimal, *, maker: bool
) -> Decimal:
    """Rounded fee minus raw fee, per contract. Used to pick a minimum order
    size where rounding no longer dominates."""
    coef = sched.maker_coef if maker else sched.taker_coef
    if contracts == 0:
        return ZERO
    raw = raw_quadratic(coef, contracts, price)
    return (order_fee(sched, contracts, price, maker=maker) - raw) / contracts


def min_size_for_overhead(
    sched: FeeSchedule,
    price: Decimal,
    *,
    maker: bool,
    max_overhead_per_contract: Decimal,
    size_step: Decimal = ONE,
    max_size: Decimal = Decimal(1000),
) -> Decimal | None:
    """Smallest order size whose worst-case rounding overhead per contract is
    at or below ``max_overhead_per_contract``. Because rounding overhead
    oscillates with size, we require the bound to hold for this size."""
    size = size_step
    while size <= max_size:
        if fee_rounding_overhead(sched, size, price, maker=maker) <= max_overhead_per_contract:
            return size
        size += size_step
    return None


def quantize_cents(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)
