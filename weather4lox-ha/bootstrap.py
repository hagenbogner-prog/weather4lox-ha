#!/usr/bin/env python3
"""Bootstrap the Weather4Lox HA app and its independent cache refresher."""

from datetime import datetime
from threading import Event, Thread
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
