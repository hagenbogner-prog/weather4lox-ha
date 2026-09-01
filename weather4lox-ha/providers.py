"""Provider-specific forecast strategies for Weather4Lox HA.

The app deliberately consumes Home Assistant weather entities instead of
calling provider APIs directly.  DWD and OpenWeatherMap nevertheless get
separate policies because their HA forecast capabilities and upstream API
strategies differ.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    forecast_type: str
    default_refresh_minutes: int
    default_cache_ttl_minutes: int
    max_requested_days: int
    allow_daily_fallback: bool


PROFILES = {
    "dwd": ProviderProfile(
        name="dwd",
        forecast_type="hourly",
        default_refresh_minutes=120,
        default_cache_ttl_minutes=1440,
        max_requested_days=7,
        allow_daily_fallback=True,
    ),
    "openweathermap": ProviderProfile(
        name="openweathermap",
        forecast_type="hourly",
        default_refresh_minutes=60,
        default_cache_ttl_minutes=2880,
        max_requested_days=7,
        allow_daily_fallback=True,
    ),
}


def get_profile(provider: str) -> ProviderProfile:
    try:
        return PROFILES[provider]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported provider '{provider}'. Select exactly one of: dwd, openweathermap"
        ) from exc


def requested_hours(options: dict) -> int:
    days = int(options.get("forecast_days", 2))
    days = max(1, min(days, 7))
    return days * 24


def refresh_minutes(options: dict, profile: ProviderProfile) -> int:
    value = int(options.get("refresh_interval_minutes", profile.default_refresh_minutes))
    return max(30, min(value, 1440))


def cache_ttl_minutes(options: dict, profile: ProviderProfile) -> int:
    value = int(options.get("cache_ttl_minutes", profile.default_cache_ttl_minutes))
    # Cache validity may not exceed the configured forecast horizon.
    max_ttl = requested_hours(options) * 60
    return max(60, min(value, max_ttl))
