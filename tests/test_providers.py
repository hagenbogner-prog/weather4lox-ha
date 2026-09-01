import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "weather4lox-ha"))

from providers import cache_ttl_minutes, forecast_days, get_profile, refresh_minutes


def test_only_supported_providers_exist():
    assert set(__import__("providers").PROFILES) == {"dwd", "openweathermap"}


def test_provider_specific_defaults_and_bounds():
    dwd = {"forecast_days": 7, "dwd": {"refresh_interval_minutes": 120, "cache_validity_hours": 24}}
    owm = {"forecast_days": 7, "openweathermap": {"refresh_interval_minutes": 60, "cache_validity_hours": 48}}
    assert refresh_minutes("dwd", dwd) == 120
    assert refresh_minutes("openweathermap", owm) == 60
    assert cache_ttl_minutes("dwd", dwd) == 24 * 60
    assert cache_ttl_minutes("openweathermap", owm) == 48 * 60


def test_cache_validity_cannot_exceed_forecast_horizon():
    options = {"forecast_days": 2, "openweathermap": {"cache_validity_hours": 168}}
    assert forecast_days("openweathermap", options) == 2
    assert cache_ttl_minutes("openweathermap", options) == 48 * 60


def test_refresh_is_clamped_to_30_minutes_to_24_hours():
    low = {"openweathermap": {"refresh_interval_minutes": 1}}
    high = {"openweathermap": {"refresh_interval_minutes": 9999}}
    assert refresh_minutes("openweathermap", low) == 30
    assert refresh_minutes("openweathermap", high) == 1440
