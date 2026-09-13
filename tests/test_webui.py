import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "weather4lox-ha"))

import webui


class FakeServer:
    VERSION = "0.6.0"
    last_error = None
    last_attempt = None
    last_success = None
    last_validation = {"ok": True}
    request_count = 12

    def __init__(self, cache, error=None):
        self._cache = cache
        self.last_error = error

    def opts(self):
        return {"weather_provider": "openweathermap"}

    def selected_entity(self, provider):
        assert provider == "openweathermap"
        return "weather.openweathermap"

    def load_cache(self):
        return self._cache

    def cache_age_minutes(self, item):
        return 5.0 if item else None

    def cache_ttl_minutes(self, provider):
        return 2880

    def cache_matches(self, item, provider, entity):
        return bool(item and item.get("provider") == provider and item.get("entity") == entity)

    def cache_is_valid(self, item, provider, entity):
        if not self.cache_matches(item, provider, entity):
            return False
        if self.cache_age_minutes(item) > 2880:
            return False
        end = self.parse_dt(item.get("forecast_end"))
        return bool(end and end.astimezone(timezone.utc) >= datetime.now(timezone.utc))

    def forecast_days(self, provider):
        return 7

    def refresh_minutes(self, provider):
        return 60

    @staticmethod
    def parse_dt(value):
        if not value:
            return None
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def make_cache(end):
    now = datetime.now(timezone.utc)
    return {
        "provider": "openweathermap",
        "entity": "weather.openweathermap",
        "created_at": now.isoformat(),
        "last_success": now.isoformat(),
        "forecast_start": now.isoformat(),
        "forecast_end": end.isoformat(),
        "forecast": [{"datetime": end.isoformat()}],
    }


def test_cache_is_usable_only_while_forecast_end_is_in_future():
    current = make_cache(datetime.now(timezone.utc) + timedelta(hours=6))
    expired = make_cache(datetime.now(timezone.utc) - timedelta(hours=1))
    assert webui.cache_is_usable(FakeServer(current), current, "openweathermap", "weather.openweathermap")
    assert not webui.cache_is_usable(FakeServer(expired), expired, "openweathermap", "weather.openweathermap")


def test_same_day_forecast_that_already_ended_is_expired():
    expired = make_cache(datetime.now(timezone.utc) - timedelta(minutes=5))
    status = webui.diagnostics(FakeServer(expired))
    assert status["cache"]["state"] == "expired"
    assert status["level"] == "error"
    assert status["issue"]["code"] == "forecast_expired"


def test_openweathermap_forecast_failure_gets_actionable_hint():
    cache = make_cache(datetime.now(timezone.utc) - timedelta(days=2))
    server = FakeServer(cache, "Home Assistant API HTTP 500: Server got itself in trouble")
    status = webui.diagnostics(server)
    assert status["level"] == "error"
    assert status["issue"]["code"] == "openweathermap_forecast_unavailable"
    assert "forecast" in status["issue"]["message"]
    assert "v3.0" in status["issue"]["message"]


def test_dashboard_does_not_render_location_configuration():
    cache = make_cache(datetime.now(timezone.utc) + timedelta(hours=6))
    server = FakeServer(cache)
    page = webui.dashboard_html(server)
    assert "latitude" not in page.lower()
    assert "longitude" not in page.lower()
    assert "token" not in page.lower()
