#!/usr/bin/env python3
"""Start the Home Assistant Weather4Lox service with protocol compatibility enabled."""

from datetime import datetime
from zoneinfo import ZoneInfo

import loxone_format2
import server_035

# The compatibility layer builds on the stable HTTP/data implementation while
# keeping the Loxone Gen 1 format-2 serializer isolated from provider logic.
for name in (
    "opts",
    "parse_dt",
    "get_state",
    "selected_entity",
    "service_forecast",
    "snapshot",
    "obtain_forecast",
    "log",
):
    setattr(server_035, name, getattr(server_035.core, name))


def configured_tz():
    return ZoneInfo(server_035.opts().get("timezone", "Europe/Berlin"))


def local_dt(value):
    dt = server_035.parse_dt(value)
    return dt.astimezone(configured_tz()) if dt else datetime.now(configured_tz())


server_035.local_dt = local_dt
loxone_format2.install(server_035)

if __name__ == "__main__":
    server_035.main()
