"""Configuration: YAML file for parameters, environment variables for secrets.

Design decisions
----------------
* Secrets NEVER live in YAML. The YAML only names the environment variable
  that holds a secret (e.g. ``key_id_env: KALSHI_API_KEY_ID``). This keeps
  config files safe to commit and diff.
* Defaults are deliberately conservative (see the spec's CONFIGURATION section).
  Loosening any of them is a manual, explicit config change.
* Each venue has an independent mode: off / record / shadow / paper / live.
  Phase 1 only implements ``record``; any other non-off mode is rejected at
  startup by :func:`validate_phase_capabilities` so nobody can accidentally run
  a mode whose safety machinery doesn't exist yet.
"""

from __future__ import annotations

import os
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class VenueMode(str, Enum):
    OFF = "off"
    RECORD = "record"
    SHADOW = "shadow"
    PAPER = "paper"
    LIVE = "live"


class Venue(str, Enum):
    KALSHI = "kalshi"
    POLYMARKET_US = "polymarket_us"
    GEMINI = "gemini"


# Modes implemented so far. Bumped as phases land; see README.
IMPLEMENTED_MODES: frozenset[VenueMode] = frozenset({VenueMode.OFF, VenueMode.RECORD})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FeeOverride(_Strict):
    """Fee coefficients used when a venue does not publish a machine-readable
    schedule (or as a fallback when the fetch fails).

    Fees are modelled as ``coef * C * P * (1 - P)`` dollars, rounded per the
    venue's rule. ``verified`` must be flipped to true by a human after checking
    the venue's live published schedule; until then calibration/edge reports
    flag every number that depended on it.
    """

    taker_coef: Decimal
    maker_coef: Decimal = Decimal("0")
    # Deterministic per-fill maker rebate coefficient (counted in edge).
    maker_rebate_coef: Decimal = Decimal("0")
    # Rounding increment in dollars and whether rounding applies per order or per fill.
    rounding_increment: Decimal = Decimal("0.01")
    rounding_scope: str = "order"  # "order" | "fill"
    verified: bool = False
    # Discretionary programs (waivers, rebate programs, incentives). Logged only;
    # NEVER included in edge (spec: STRATEGY edge rule).
    discretionary_notes: list[str] = Field(default_factory=list)


class VenueConfig(_Strict):
    mode: VenueMode = VenueMode.OFF
    rest_base_url: str
    ws_url: str
    # Optional separate public REST base (Polymarket US splits gateway vs api).
    public_rest_base_url: str | None = None
    # Names of environment variables (never the secrets themselves).
    key_id_env: str | None = None
    secret_env: str | None = None
    secret_path_env: str | None = None  # e.g. path to a PEM file
    window_lengths_min: list[int] = Field(default_factory=lambda: [5, 15])
    discovery_interval_s: float = 30.0
    rest_reconcile_interval_s: float = 30.0
    # Used only when the authenticated websocket isn't available (no keys):
    # poll REST books instead. Kept slow to respect rate limits.
    rest_poll_interval_s: float = 2.0
    max_ws_subscriptions: int = 50
    fees: FeeOverride | None = None
    # Venue-specific knobs that don't deserve a schema of their own yet.
    extra: dict[str, Any] = Field(default_factory=dict)


class SpotFeedConfig(_Strict):
    name: str  # coinbase | kraken | bitstamp | gemini | binance_us ...
    enabled: bool = True
    # Settlement-index proxy role (e.g. Gemini spot for Gemini; BRTI constituents for Kalshi).
    proxy_for: list[Venue] = Field(default_factory=list)


class SpotConfig(_Strict):
    feeds: list[SpotFeedConfig] = Field(
        default_factory=lambda: [
            SpotFeedConfig(name="coinbase", proxy_for=[Venue.KALSHI]),
            SpotFeedConfig(name="kraken", proxy_for=[Venue.KALSHI]),
            SpotFeedConfig(name="bitstamp", proxy_for=[Venue.KALSHI]),
            SpotFeedConfig(name="gemini", proxy_for=[Venue.KALSHI, Venue.GEMINI]),
        ]
    )
    # Chainlink BTC/USD Data Streams need credentials; recorded if configured.
    chainlink_enabled: bool = False
    chainlink_ws_url: str | None = None
    chainlink_key_env: str = "CHAINLINK_STREAMS_CLIENT_ID"
    chainlink_secret_env: str = "CHAINLINK_STREAMS_CLIENT_SECRET"
    staleness_limit_ms: int = 500


class ClockConfig(_Strict):
    ntp_servers: list[str] = Field(
        default_factory=lambda: ["time.google.com", "time.cloudflare.com", "pool.ntp.org"]
    )
    max_drift_ms: float = 100.0
    check_interval_s: float = 60.0
    # In record mode a bad clock does not stop recording (we still log the
    # measured offset so data can be corrected), but any trading mode refuses.
    block_recording_on_drift: bool = False


class RecorderConfig(_Strict):
    out_dir: Path = Path("data/recordings")
    # Rotate files hourly; gzip JSONL is append-friendly and crash-tolerant.
    rotate_seconds: int = 3600
    flush_interval_s: float = 1.0
    settlement_poll_interval_s: float = 60.0


class RiskDefaults(_Strict):
    """Conservative defaults from the spec. Not enforced until Phase 3, but
    defined now so config files are stable across phases."""

    per_venue_max_exposure_usd: Decimal = Decimal("75")
    total_max_exposure_usd: Decimal = Decimal("200")
    initial_live_cap_usd: Decimal = Decimal("25")
    per_venue_daily_loss_usd: Decimal = Decimal("20")
    total_daily_loss_usd: Decimal = Decimal("40")
    min_half_spread: Decimal = Decimal("0.02")
    final_cutoff_point_price_s: float = 45.0
    final_cutoff_averaged_s: float = 20.0
    max_participation: float = 0.10
    shadow_period_hours: float = 48.0


class GateDefaults(_Strict):
    min_windows: int = 500
    min_fills: int = 2000
    min_live_paper_fraction: float = 0.30
    max_p_value: float = 0.05


class AppConfig(_Strict):
    venues: dict[Venue, VenueConfig]
    spot: SpotConfig = Field(default_factory=SpotConfig)
    clock: ClockConfig = Field(default_factory=ClockConfig)
    recorder: RecorderConfig = Field(default_factory=RecorderConfig)
    risk: RiskDefaults = Field(default_factory=RiskDefaults)
    gates: GateDefaults = Field(default_factory=GateDefaults)
    log_level: str = "INFO"

    @field_validator("venues")
    @classmethod
    def _all_venues_present(cls, v: dict[Venue, VenueConfig]) -> dict[Venue, VenueConfig]:
        missing = set(Venue) - set(v)
        if missing:
            raise ValueError(f"config missing venues: {sorted(m.value for m in missing)}")
        return v


class ConfigError(RuntimeError):
    pass


def load_config(path: str | Path) -> AppConfig:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    cfg = AppConfig.model_validate(raw)
    validate_phase_capabilities(cfg)
    return cfg


def validate_phase_capabilities(cfg: AppConfig) -> None:
    """Refuse modes whose safety machinery is not built yet.

    This is a hard guard, not a warning: live/paper/shadow need the risk
    module, gates and simulation that arrive in later phases.
    """
    for venue, vc in cfg.venues.items():
        if vc.mode not in IMPLEMENTED_MODES:
            raise ConfigError(
                f"{venue.value}: mode '{vc.mode.value}' is not implemented yet "
                f"(available: {sorted(m.value for m in IMPLEMENTED_MODES)})"
            )


def get_secret(env_name: str | None, *, required: bool = False) -> str | None:
    """Read a secret from the environment. Never logs the value."""
    if not env_name:
        if required:
            raise ConfigError("secret env var name not configured")
        return None
    val = os.environ.get(env_name)
    if required and not val:
        raise ConfigError(f"required environment variable {env_name} is not set")
    return val or None
