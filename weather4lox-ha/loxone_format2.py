#!/usr/bin/env python3
"""Loxone Weather4Lox format-2 response compatibility.

The format-2 response has one metadata header describing all 29 fields,
a single station-metadata row with the first 10 station fields, followed by
hourly rows containing only the 19 forecast fields.
"""
from __future__ import annotations

import json
from datetime import datetime

HEADER_COLUMNS = 29
STATION_COLUMNS = 10
WEATHER_COLUMNS = 19
VALID_PICTOS = set(range(1, 36))


def _fmt(core, value, digits=2, default="0"):
    return core.fmt(value, digits, default)


def _coord(value, default_lon=10.681, default_lat=48.56):
    try:
        lon, lat = str(value).split(",", 1)
        return float(lon), float(lat)
    except (TypeError, ValueError):
        return default_lon, default_lat


def metadata():
    return (
        "id;name;longitude;latitude;height (m.asl.);country;timezone;"
        "utc-timedifference;sunrise;sunset;local date;weekday;local time;"
        "temperature(C);feeledTemperature(C);windspeed(km/h);"
        "winddirection(degr);wind gust(km/h);low clouds(%);medium clouds(%);"
        "high clouds(%);precipitation(mm);probability of Precip(%);snowFraction;"
        "sea level pressure(hPa);relative humidity(%);CAPE;picto-code;"
        "radiation (W/m2)"
    )


def _timezone_info(core):
    now = datetime.now().astimezone()
    return now.tzname() or core.opts().get("timezone", "Europe/Berlin"), now.strftime("UTC%z")


def station_metadata(core, query):
    options = core.opts()
    fallback_coord = f"{options.get('longitude', 10.681)},{options.get('latitude', 48.56)}"
    lon, lat = _coord(query.get("coord", [fallback_coord])[0])
    asl = query.get("asl", [str(options.get("elevation_m", 450))])[0]
    timezone_name, utc_offset = _timezone_info(core)
    return ";".join([
        "",
        str(options.get("location_city", "Wertingen")),
        _fmt(core, lon, 6),
        _fmt(core, lat, 6),
        str(asl),
        str(options.get("country", "Deutschland")),
        timezone_name,
        utc_offset,
        "",
        "",
    ])


def build_rows(core, forecast, query, diagnostic=False):
    snap = (
        core.snapshot()
        if not diagnostic
        else {
            "clouds": 0,
            "temperature": 20,
            "feels_like": 20,
            "wind_speed": 5,
            "wind_direction": 180,
            "wind_gust": 8,
            "pressure": 1013,
            "humidity": 50,
        }
    )
    rows = []
    for item in forecast:
        dt = core.local_dt(item.get("datetime"))
        clouds = core.clamp(
            core.safe_float(item.get("cloud_coverage"), core.safe_float(snap.get("clouds"))),
            0,
            100,
        )
        precipitation = max(0, core.safe_float(item.get("precipitation"), 0))
        probability = core.clamp(
            core.safe_float(item.get("precipitation_probability"), 0), 0, 100
        )
        snow = max(0, core.safe_float(item.get("snow"), 0))
        snow_fraction = snow / precipitation if precipitation else 0
        row = [
            dt.strftime("%d.%m.%Y"),
            dt.strftime("%a"),
            dt.strftime("%H"),
            _fmt(core, item.get("temperature", snap.get("temperature")), 1),
            _fmt(core, item.get("apparent_temperature", snap.get("feels_like")), 1),
            _fmt(core, item.get("wind_speed", snap.get("wind_speed")), 0),
            _fmt(core, item.get("wind_bearing", snap.get("wind_direction")), 0),
            _fmt(core, item.get("wind_gust_speed", snap.get("wind_gust")), 0),
            _fmt(core, 0, 0),
            _fmt(core, clouds, 0),
            _fmt(core, 0, 0),
            _fmt(core, precipitation, 1),
            _fmt(core, probability, 0),
            _fmt(core, snow_fraction, 1),
            _fmt(core, item.get("pressure", snap.get("pressure")), 0),
            _fmt(core, item.get("humidity", snap.get("humidity")), 0),
            _fmt(core, item.get("cape"), 0),
            str(core.DIAGNOSTIC_PICTO if diagnostic else core.picto(item)),
            _fmt(core, item.get("radiation"), 0),
        ]
        if len(row) != WEATHER_COLUMNS:
            raise RuntimeError(f"Forecast row has {len(row)} columns, expected {WEATHER_COLUMNS}")
        rows.append(";".join(row) + ";")
    return rows


def validate_payload(core, header, station, rows, expected_rows, expected_picto=None):
    invalid = []
    counts = []
    for index, row in enumerate(rows):
        parts = row.rstrip(";").split(";")
        counts.append(len(parts))
        try:
            pictocode = int(parts[17])
        except (ValueError, IndexError):
            pictocode = None
        if pictocode not in VALID_PICTOS or (
            expected_picto is not None and pictocode != expected_picto
        ):
            invalid.append({"row": index, "picto": pictocode})

    checks = {
        "header_columns": len(header.split(";")),
        "expected_header_columns": HEADER_COLUMNS,
        "station_columns": len(station.rstrip(";").split(";")),
        "expected_station_columns": STATION_COLUMNS,
        "rows": len(rows),
        "expected_rows": expected_rows,
        "row_columns_min": min(counts) if counts else 0,
        "row_columns_max": max(counts) if counts else 0,
        "expected_row_columns": WEATHER_COLUMNS,
        "invalid_pictos": invalid,
        "terminator": True,
    }
    checks["ok"] = (
        checks["header_columns"] == HEADER_COLUMNS
        and checks["station_columns"] == STATION_COLUMNS
        and len(rows) == expected_rows
        and all(count == WEATHER_COLUMNS for count in counts)
        and not invalid
    )
    return checks


def make_payload(core, forecast, query, diagnostic=False):
    if not forecast:
        raise RuntimeError("No forecast data available")
    header = metadata()
    station = station_metadata(core, query)
    rows = build_rows(core, forecast, query, diagnostic)
    validation = validate_payload(
        core,
        header,
        station,
        rows,
        len(forecast),
        core.DIAGNOSTIC_PICTO if diagnostic else None,
    )
    if not validation["ok"]:
        raise RuntimeError("Loxone response validation failed: " + json.dumps(validation))

    valid_until = core.local_dt(forecast[-1]["datetime"]).strftime("%Y-%m-%d")
    payload = (
        "<mb_metadata>\n"
        + header
        + ";\n</mb_metadata>\n"
        + "<valid_until>"
        + valid_until
        + "</valid_until>\n"
        + "<station>\n"
        + station
        + ";\n"
        + "\n".join(rows)
        + "\n</station>\n"
    )
    return payload, validation


def reference_diagnostic(core, query):
    forecast, source, fallback = core.obtain_forecast()
    payload, validation = make_payload(core, forecast, query)
    station_text = payload.split("<station>\n", 1)[1].split("\n</station>", 1)[0]
    lines = station_text.splitlines()
    station = lines[0].rstrip(";").split(";") if lines else []
    rows = [line.rstrip(";").split(";") for line in lines[1:] if line]
    picto_values = sorted({int(row[17]) for row in rows if len(row) > 17})
    return {
        "version": core.VERSION,
        "source": source,
        "fallback_count": fallback,
        "rows": len(rows),
        "columns": len(rows[0]) if rows else 0,
        "station_columns": len(station),
        "first_row": rows[0] if rows else [],
        "middle_row": rows[len(rows) // 2] if rows else [],
        "last_row": rows[-1] if rows else [],
        "picto_codes": picto_values,
        "validation": validation,
    }


def install(core):
    """Patch the proven HTTP server with the documented format-2 serializer."""
    # server_035 deliberately exposes only the high-level helpers. Re-export
    # the low-level formatter helpers needed by this compatibility layer from
    # its proven implementation module.
    implementation = getattr(core, "core", core)
    for name in ("fmt", "safe_float", "clamp", "local_dt", "picto", "DIAGNOSTIC_PICTO", "VERSION"):
        if not hasattr(core, name):
            setattr(core, name, getattr(implementation, name))

    core.metadata = metadata
    core.build_rows = lambda forecast, query, diagnostic=False: build_rows(
        core, forecast, query, diagnostic
    )
    core.validate_payload = lambda header, rows, expected_rows, expected_picto=None: (
        validate_payload(core, header, ";;;;;;;;;", rows, expected_rows, expected_picto)
    )
    core.make_payload = lambda forecast, query, diagnostic=False: make_payload(
        core, forecast, query, diagnostic
    )
    core.reference_diagnostic = lambda query: reference_diagnostic(core, query)
