import sys
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

sys.path.insert(0, str(Path(__file__).parents[1] / "weather4lox-ha"))

import webui


class FakeServer:
    VERSION = "0.6.2"
    last_error = None
    last_attempt = None
    last_success = None
    last_validation = {"ok": True}
    request_count = 12

    def __init__(self, cache, error=None):
        self._cache = cache
        self.last_error = error
        self.check_calls = 0

    def opts(self):
        return {"weather_provider": "openweathermap"}

    @staticmethod
    def debug(*_args):
        pass

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

    def obtain_forecast(self, force=False):
        assert force is True
        self.check_calls += 1
        return self._cache["forecast"], "live", self._cache

    @staticmethod
    def make_payload(forecast, query):
        assert forecast
        assert query == {"coord": ["0,0"], "asl": ["0"]}
        return "payload", {"ok": True}

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


def test_dashboard_builds_neutral_service_links_from_current_host():
    cache = make_cache(datetime.now(timezone.utc) + timedelta(hours=6))
    page = webui.dashboard_html(FakeServer(cache))

    assert "window.location.hostname" in page
    assert "${serviceBase}/status" in page
    assert "${serviceBase}/control/refresh" in page
    assert "192.168." not in page


def test_run_check_returns_visible_success_result():
    cache = make_cache(datetime.now(timezone.utc) + timedelta(hours=6))
    server = FakeServer(cache)

    state = webui.run_check(server)

    assert state["check"]["ok"] is True
    assert state["check"]["level"] == "ok"
    assert "Loxone Format 2 ist gültig" in state["check"]["message"]
    assert state["loxone"]["format_valid"] is True


def test_run_check_returns_visible_error_result():
    cache = make_cache(datetime.now(timezone.utc) + timedelta(hours=6))
    server = FakeServer(cache)

    def fail_refresh(force=False):
        assert force is True
        raise RuntimeError("Provider unavailable")

    server.obtain_forecast = fail_refresh
    state = webui.run_check(server)

    assert state["check"]["ok"] is False
    assert state["check"]["level"] == "error"
    assert "Provider unavailable" in state["check"]["message"]
    assert state["loxone"]["format_valid"] is False


def request_webui(server, method="GET", path="/", headers=None):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), webui.make_handler(server))
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", httpd.server_port, timeout=2)
    try:
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8")
    finally:
        connection.close()
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_webui_rejects_direct_request_without_ingress_identity():
    cache = make_cache(datetime.now(timezone.utc) + timedelta(hours=6))
    status, body = request_webui(FakeServer(cache))
    assert status == 403
    assert "Ingress required" in body


def test_webui_rejects_forged_ingress_header_from_other_ip():
    cache = make_cache(datetime.now(timezone.utc) + timedelta(hours=6))
    status, body = request_webui(
        FakeServer(cache),
        headers={webui.INGRESS_USER_HEADER: "home-assistant-user-id"},
    )
    assert status == 403
    assert "Ingress required" in body


def test_webui_accepts_authenticated_ingress_request(monkeypatch):
    cache = make_cache(datetime.now(timezone.utc) + timedelta(hours=6))
    monkeypatch.setattr(webui, "INGRESS_PROXY_IP", "127.0.0.1")
    status, body = request_webui(
        FakeServer(cache),
        headers={webui.INGRESS_USER_HEADER: "home-assistant-user-id"},
    )
    assert status == 200
    assert "Weather4Lox HA" in body


def test_check_action_requires_ingress_and_uses_post(monkeypatch):
    cache = make_cache(datetime.now(timezone.utc) + timedelta(hours=6))
    server = FakeServer(cache)
    headers = {webui.INGRESS_USER_HEADER: "home-assistant-user-id"}
    monkeypatch.setattr(webui, "INGRESS_PROXY_IP", "127.0.0.1")

    get_status, _ = request_webui(server, path="/api/check", headers=headers)
    post_status, _ = request_webui(server, method="POST", path="/api/check", headers=headers)

    assert get_status == 405
    assert post_status == 200
    assert server.check_calls == 1
