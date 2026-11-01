from pathlib import Path

import pytest
import yaml

from btcmm.config import AppConfig, ConfigError, Venue, VenueMode, get_secret, load_config

DEFAULT = Path(__file__).resolve().parents[1] / "config" / "default.yaml"


def test_default_config_loads_with_conservative_defaults():
    cfg = load_config(DEFAULT)
    assert set(cfg.venues) == set(Venue)
    assert all(v.mode in (VenueMode.OFF, VenueMode.RECORD) for v in cfg.venues.values())
    assert str(cfg.risk.per_venue_max_exposure_usd) == "75"
    assert str(cfg.risk.total_max_exposure_usd) == "200"
    assert str(cfg.risk.initial_live_cap_usd) == "25"
    assert str(cfg.risk.min_half_spread) == "0.02"
    assert cfg.risk.final_cutoff_point_price_s == 45 and cfg.risk.final_cutoff_averaged_s == 20
    assert cfg.spot.staleness_limit_ms == 500 and cfg.clock.max_drift_ms == 100
    assert cfg.gates.min_windows == 500 and cfg.gates.min_fills == 2000


@pytest.mark.parametrize("mode", ["shadow", "paper", "live"])
def test_unimplemented_modes_are_refused(tmp_path, mode):
    raw = yaml.safe_load(DEFAULT.read_text())
    raw["venues"]["kalshi"]["mode"] = mode
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(raw))
    with pytest.raises(ConfigError):
        load_config(p)


def test_missing_venue_rejected():
    raw = yaml.safe_load(DEFAULT.read_text())
    del raw["venues"]["gemini"]
    with pytest.raises(Exception):
        AppConfig.model_validate(raw)


def test_unknown_keys_rejected():
    raw = yaml.safe_load(DEFAULT.read_text())
    raw["venues"]["kalshi"]["api_secret"] = "oops"  # secrets must not live in YAML
    with pytest.raises(Exception):
        AppConfig.model_validate(raw)


def test_secrets_from_env(monkeypatch):
    monkeypatch.setenv("BTCMM_TEST_SECRET", "s3cret")
    assert get_secret("BTCMM_TEST_SECRET") == "s3cret"
    assert get_secret("BTCMM_NOT_SET") is None
    with pytest.raises(ConfigError):
        get_secret("BTCMM_NOT_SET", required=True)
