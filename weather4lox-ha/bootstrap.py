#!/usr/bin/env python3
"""Start Weather4Lox HA with the documented Loxone Gen 1 format=2 serializer."""

from datetime import datetime
from threading import Event, Thread
from time import sleep
from zoneinfo import ZoneInfo

import loxone_format2
import server

VERSION = "0.4.2"
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
    """Refresh the local forecast cache independently of Loxone requests."""
    while not stop.is_set():
        try:
            server.obtain_forecast(force=True)
        except Exception as exc:
            server.log.warning("Scheduled forecast refresh failed: %s", exc)
        interval = max(5, int(server.opts().get("refresh_interval_minutes", 30))) * 60
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
