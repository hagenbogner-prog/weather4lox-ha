import json
import sys
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

sys.path.insert(0, str(Path(__file__).parents[1] / "weather4lox-ha"))

import server


def request(httpd, path):
    connection = HTTPConnection("127.0.0.1", httpd.server_port, timeout=2)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8")
    finally:
        connection.close()


def test_only_real_forecast_requests_are_counted_and_query_values_are_redacted(monkeypatch):
    monkeypatch.setattr(server, "request_count", 0)
    monkeypatch.setattr(server, "last_request", None)
    monkeypatch.setattr(server, "last_validation", {})
    monkeypatch.setattr(server, "last_error", None)
    monkeypatch.setattr(server, "last_attempt", None)
    monkeypatch.setattr(server, "last_success", None)
    monkeypatch.setattr(server, "opts", lambda: {"weather_provider": "openweathermap"})
    monkeypatch.setattr(server, "load_cache", lambda: None)
    monkeypatch.setattr(server, "selected_entity", lambda _provider: "weather.openweathermap")
    monkeypatch.setattr(server, "obtain_forecast", lambda: ([{"datetime": "2026-09-13T12:00:00+00:00"}], "live", {}))
    monkeypatch.setattr(server, "make_payload", lambda _forecast, _query: ("payload", {"ok": True}))

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        status_code, _ = request(httpd, "/status")
        health_code, _ = request(httpd, "/health")
        forecast_code, _ = request(
            httpd,
            "/forecast/?user=private-user&coord=10.0,20.0&asl=100&format=2",
        )
        final_status_code, status_body = request(httpd, "/status")
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)

    status = json.loads(status_body)
    assert (status_code, health_code, forecast_code, final_status_code) == (200, 200, 200, 200)
    assert status["request_count"] == 1
    assert status["last_request"]["path"] == "/forecast"
    assert status["last_request"]["parameters"] == ["asl", "coord", "format", "user"]
    assert "private-user" not in status_body
    assert "10.0,20.0" not in status_body


def test_raw_diagnostics_omit_home_assistant_attributes(monkeypatch):
    monkeypatch.setattr(
        server,
        "snapshot",
        lambda _entity=None: {
            "provider": "openweathermap",
            "temperature": 20,
            "raw_attributes": {"latitude": 10.0, "longitude": 20.0},
        },
    )

    result = server.diagnostic_snapshot()

    assert result == {"provider": "openweathermap", "temperature": 20}
