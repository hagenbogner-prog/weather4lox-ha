#!/usr/bin/env python3
"""Prepare the production compatibility layers for the live service."""

from datetime import datetime
from zoneinfo import ZoneInfo

import server_035

# server_035 imports the proven implementation as ``core`` but intentionally
# does not re-export every helper. The JSON layer and protocol layer use these
# helpers directly.
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


def generated_at():
    return datetime.now(configured_tz()).replace(microsecond=0).isoformat()


# The Loxone format-2 response uses configured local time for its date,
# weekday and hour fields.
server_035.local_dt = local_dt

# Install the exact Weather4Lox/Loxone format-2 structure: 29 metadata
# columns, one 10-column station metadata line, and 19-column hourly rows.
import loxone_format2

loxone_format2.install(server_035)

import live_data

live_data._iso_local = local_dt
live_data._generated_at = generated_at

_original_location = live_data._location


def location(attrs=None):
    result = _original_location(attrs)
    now = datetime.now(configured_tz())
    result["tzOffset"] = now.strftime("%z")
    result["tzShort"] = now.tzname() or "CET"
    return result


live_data._location = location
live_data.HOURLY_LIMIT = 167

# The live JSON files must follow the same envelope/field semantics as the
# current Weather4Lox v4 LoxBerry grabbers. Keep the HTTP handler in
# live_data.py, but replace only the file-generation implementation.
import json_compat

live_data.refresh = json_compat.refresh

if __name__ == "__main__":
    live_data.main()
