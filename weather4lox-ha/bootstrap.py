#!/usr/bin/env python3
"""Bootstrap the Weather4Lox HA app and its independent cache refresher."""

import os
from datetime import datetime
from threading import Event, Thread
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import loxone_format2
import server

VERSION = "0.5.0"
server.VERSION = VERSION
server.Handler.server_version = f"Weather4LoxHA/{VERSION}"


def configured_tz():
    return ZoneInfo(server.opts().get("timezone", "Europe/Berlin"))


def local_dt(value):
    dt = server.parse_dt(value)
    return dt.astimezone(configured_tz()) if dt else datetime.now(configured_tz())


server.local_dt = local_dt
loxone_format2.install(server)


def provider_config(provider, options=None):
    options = options or server.opts()
    prefix = "dwd" if provider == "dwd" else "openweathermap"
    return {
        "weather_entity": options.get(f"{prefix}_weather_entity", "auto"),
        "refresh_interval_minutes": options.get(f"{prefix}_refresh_interval_minutes"),
        "cache_validity_hours": options.get(f"{prefix}_cache_validity_hours"),
    }


server.provider_config = provider_config

_original_do_get = server.Handler.do_GET


def control_do_get(self):
    path = urlparse(self.path).path.rstrip("/")
    if path == "/control/clear-cache":
        try:
            with server.lock:
                server.cache = None
                if os.path.exists(server.CACHE_FILE):
                    os.remove(server.CACHE_FILE)
            self.json({"ok": True, "status": "🔴 Error", "message": "Cache cleared"})
        except Exception as exc:
            self.json({"ok": False, "error": str(exc)}, 500)
        return
    if path == "/control/refresh":
        try:
            forecast, source, meta = server.obtain_forecast(force=True)
            self.json({"ok": True, "source": source, "entries": len(forecast), "metadata": meta})
        except Exception as exc:
            self.json({"ok": False, "error": str(exc)}, 500)
        return
    _original_do_get(self)


server.Handler.do_GET = control_do_get


def refresh_loop(stop: Event) -> None:
    """Refresh immediately, then retry at the selected provider interval."""
    while not stop.is_set():
        try:
            server.obtain_forecast(force=True)
        except Exception as exc:
            server.log.warning("Scheduled forecast refresh failed: %s", exc)
        provider = server.opts().get("weather_provider", "openweathermap")
        interval = max(30, server.refresh_minutes(provider, server.opts())) * 60
        stop.wait(interval)


def main() -> None:
    stop = Event()
    Thread(target=refresh_loop, args=(stop,), name="forecast-refresh", daemon=True).start()
    try:
        server.main()
    finally:
        stop.set()


if __name__ == "__main__":
    main()
