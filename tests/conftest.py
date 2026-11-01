from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from btcmm.config import Venue, VenueConfig, VenueMode
from btcmm.data.models import FeeSchedule, utcnow


def vcfg(**kw) -> VenueConfig:
    base = dict(mode=VenueMode.RECORD, rest_base_url="https://example.invalid", ws_url="wss://example.invalid/ws")
    base.update(kw)
    return VenueConfig(**base)


def sched(venue=Venue.GEMINI, taker="0.07", maker="0.0175", rebate="0", inc="0.01") -> FeeSchedule:
    return FeeSchedule(venue=venue, scope_id="*", fee_type="test", taker_coef=Decimal(taker),
                       maker_coef=Decimal(maker), maker_rebate_coef=Decimal(rebate),
                       rounding_increment=Decimal(inc), source="config", verified=False, fetched_at=utcnow())


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
