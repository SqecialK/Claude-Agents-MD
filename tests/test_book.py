from decimal import Decimal as D

import pytest

from btcmm.config import Venue
from btcmm.data.book import L2Book, SequenceGap
from btcmm.data.models import utcnow


def mk():
    b = L2Book(Venue.KALSHI, "M")
    b.apply_snapshot([(D("0.40"), D(10)), (D("0.41"), D(5))], [(D("0.45"), D(7))], seq=10,
                     exchange_ts=None, recv_ts=utcnow())
    return b


def test_snapshot_sorted():
    s = mk().snapshot()
    assert [l.price for l in s.bids] == [D("0.41"), D("0.40")]
    assert s.best_ask.price == D("0.45")


def test_delta_relative_and_absolute():
    b = mk()
    b.apply_delta("bid", D("0.41"), delta=D(-5), seq=11, exchange_ts=None, recv_ts=utcnow())
    assert b.snapshot().best_bid.price == D("0.40")
    b.apply_delta("ask", D("0.44"), size=D(3), seq=12, exchange_ts=None, recv_ts=utcnow())
    assert b.snapshot().best_ask.price == D("0.44")


def test_seq_gap_detected():
    b = mk()
    with pytest.raises(SequenceGap):
        b.apply_delta("bid", D("0.40"), delta=D(1), seq=12, exchange_ts=None, recv_ts=utcnow())


def test_delta_before_snapshot():
    with pytest.raises(SequenceGap):
        L2Book(Venue.KALSHI, "M").apply_delta("bid", D("0.4"), delta=D(1), seq=None, exchange_ts=None, recv_ts=utcnow())


def test_crossed_and_negative_force_resnapshot():
    b = mk()
    with pytest.raises(SequenceGap):
        b.apply_delta("bid", D("0.46"), size=D(1), seq=11, exchange_ts=None, recv_ts=utcnow())
    assert not b.initialized
    b = mk()
    with pytest.raises(SequenceGap):
        b.apply_delta("bid", D("0.40"), delta=D(-11), seq=11, exchange_ts=None, recv_ts=utcnow())
