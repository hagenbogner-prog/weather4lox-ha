"""Provider-specific policies used by the cache scheduler and diagnostics."""
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    forecast_type: str
    default_refresh_minutes: int
    default_cache_ttl_minutes: int
    max_requested_days: int
    allow_daily_fallback: bool


PROFILES = {
    "dwd": ProviderProfile("dwd", "hourly", 120, 1440, 7, True),
    "openweathermap": ProviderProfile("openweathermap", "hourly", 60, 2880, 7, True),
}


def get_profile(provider: str) -> ProviderProfile:
    if provider not in PROFILES:
        raise ValueError("Unsupported provider; select exactly one of: dwd, openweathermap")
    return PROFILES[provider]


def _options(options: dict | None) -> dict:
    if options is not None:
        return options
    try:
        with open("/data/options.json", encoding="utf-8") as f:
            value = json.load(f)
            return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _section(provider: str, options: dict) -> dict:
    section = options.get(provider, {})
    return section if isinstance(section, dict) else {}


def forecast_days(provider: str, options: dict | None = None) -> int:
    options = _options(options)
    value = int(options.get("forecast_days", 7))
    return max(1, min(value, get_profile(provider).max_requested_days))


def refresh_minutes(provider: str, options: dict | None = None) -> int:
    options = _options(options)
    profile = get_profile(provider)
    value = int(_section(provider, options).get("refresh_interval_minutes", profile.default_refresh_minutes))
    return max(30, min(value, 1440))


def cache_ttl_minutes(provider: str, options: dict | None = None) -> int:
    options = _options(options)
    profile = get_profile(provider)
    value = int(_section(provider, options).get("cache_validity_hours", profile.default_cache_ttl_minutes // 60))
    horizon_minutes = forecast_days(provider, options) * 24 * 60
    return max(24 * 60, min(value * 60, horizon_minutes))


def requested_hours(provider: str, options: dict | None = None) -> int:
    return forecast_days(provider, options) * 24
