"""Venue adapters. Use :func:`build_adapters` to construct from config."""

from __future__ import annotations

from btcmm.adapters.base import ExchangeAdapter, WritePathDisabled
from btcmm.config import AppConfig, Venue, VenueMode


def build_adapters(cfg: AppConfig, *, include_off: bool = False) -> list[ExchangeAdapter]:
    # Imported lazily so a missing optional dependency only breaks its venue.
    from btcmm.adapters.gemini import GeminiAdapter
    from btcmm.adapters.kalshi import KalshiAdapter
    from btcmm.adapters.polymarket_us import PolymarketUSAdapter

    classes = {Venue.KALSHI: KalshiAdapter, Venue.POLYMARKET_US: PolymarketUSAdapter, Venue.GEMINI: GeminiAdapter}
    return [
        classes[v](vc)
        for v, vc in cfg.venues.items()
        if include_off or vc.mode != VenueMode.OFF
    ]


__all__ = ["ExchangeAdapter", "WritePathDisabled", "build_adapters"]
