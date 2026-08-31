#!/usr/bin/env python3
"""Weather4Lox HA 0.3.5 compatibility layer.

Keeps the stable 0.3.4 core but normalizes the Home Assistant weather
response to the units and field semantics expected by the Loxone Gen 1
weather protocol.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import server as core
from protocol.loxone_gen1 import (
    DEFAULT_LOXONE_PICTO,
    LOXONE_PICTOS,
    VALID_LOXONE_PICTOS,
)

VERSION = "0.3.5"
core.VERSION = VERSION
core.Handler.server_version = f"Weather4LoxHA/{VERSION}"


def as_float(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def bearing(value):
    if isinstance(value, str):
        text = value.strip().lower().replace("-", " ")
        names = {
            "n": 0, "north": 0, "ne": 45, "northeast": 45,
            "e": 90, "east": 90, "se": 135, "southeast": 135,
            "s": 180, "south": 180, "sw": 225, "southwest": 225,
            "w": 270, "west": 270, "nw": 315, "northwest": 315,
        }
        if text in names:
            return names[text]
    return as_float(value, 0.0)


def temperature_c(value, unit):
    value = as_float(value)
    unit = str(unit or "°C").lower()
    return (value - 32) * 5 / 9 if unit in {"°f", "f"} else value


def speed_kmh(value, unit):
    value = as_float(value)
    unit = str(unit or "km/h").lower().replace(" ", "")
    if unit in {"m/s", "ms-1"}:
        return value * 3.6
    if unit in {"mph", "mi/h"}:
        return value * 1.609344
    if unit in {"kn", "knot", "knots"}:
        return value * 1.852
    return value


def pressure_hpa(value, unit):
    value = as_float(value)
    unit = str(unit or "hPa").lower()
    if unit in {"inhg", "in hg"}:
        return value * 33.8638866667
    if unit in {"mmhg", "mm hg"}:
        return value * 1.33322387415
    if unit == "bar":
        return value * 1000
    return value


def precipitation_mm(value, unit):
    value = as_float(value)
    unit = str(unit or "mm").lower()
    if unit in {"in", "inch", "inches"}:
        return value * 25.4
    return value


def timezone_offset_hours(dt):
    offset = dt.utcoffset()
    return 0 if offset is None else int(offset.total_seconds() / 3600)


def loxone_picto(item):
    """Return a protocol-safe Loxone picto code, never an emulator code."""
    condition = str(item.get("condition") or "").lower()
    mapped = LOXONE_PICTOS.get(condition)
    if mapped in VALID_LOXONE_PICTOS:
        return mapped

    try:
        supplied = int(item.get("picto-code"))
        if supplied in VALID_LOXONE_PICTOS:
            return supplied
    except (TypeError, ValueError):
        pass

    return DEFAULT_LOXONE_PICTO


def enhanced_build_rows(forecast, query, diagnostic=False):
    options = core.opts()
    snap = core.snapshot() if not diagnostic else {
        "clouds": 0, "temperature": 20, "feels_like": 20,
        "wind_speed": 5, "wind_direction": 180, "wind_gust": 8,
        "pressure": 1013, "humidity": 50,
    }
    attrs = snap.get("raw_attributes", {}) if isinstance(snap, dict) else {}
    temperature_unit = attrs.get("temperature_unit", "°C")
    speed_unit = attrs.get("wind_speed_unit", "km/h")
    pressure_unit = attrs.get("pressure_unit", "hPa")
    precipitation_unit = attrs.get("precipitation_unit", "mm")
    lon, lat = core.coord(query.get("coord", ["10.681,48.56"])[0])
    asl = query.get("asl", ["450"])[0]
    rows = []

    sunrise = attrs.get("sunrise") or attrs.get("sunrise_time") or ""
    sunset = attrs.get("sunset") or attrs.get("sunset_time") or ""

    for index, item in enumerate(forecast):
        dt = core.local_dt(item.get("datetime"))
        clouds = core.clamp(
            core.safe_float(item.get("cloud_coverage"), core.safe_float(snap.get("clouds"))),
            0,
            100,
        )
        precipitation = max(0, precipitation_mm(item.get("precipitation"), precipitation_unit))
        probability = core.clamp(core.safe_float(item.get("precipitation_probability"), 0), 0, 100)
        snow = max(0, precipitation_mm(item.get("snow"), precipitation_unit))
        snow_fraction = snow / precipitation if precipitation else 0
        temp = temperature_c(item.get("temperature", snap.get("temperature")), temperature_unit)
        feels = temperature_c(item.get("apparent_temperature", snap.get("feels_like")), temperature_unit)
        wind = speed_kmh(item.get("wind_speed", snap.get("wind_speed")), speed_unit)
        gust = speed_kmh(item.get("wind_gust_speed", snap.get("wind_gust")), speed_unit)
        direction = bearing(item.get("wind_bearing", snap.get("wind_direction")))
        pressure = pressure_hpa(item.get("pressure", snap.get("pressure")), pressure_unit)
        humidity = core.safe_float(item.get("humidity", snap.get("humidity")))
        radiation = item.get("radiation", item.get("solar_radiation", 0))

        row = [
            str(index), "Home Assistant", core.fmt(lon, 3), core.fmt(lat, 3), str(asl),
            options.get("country", "Germany"), options.get("timezone", "Europe/Berlin"),
            str(timezone_offset_hours(dt)), sunrise, sunset,
            dt.strftime("%Y-%m-%d"), dt.strftime("%a"), dt.strftime("%H:%M"),
            core.fmt(temp, 2), core.fmt(feels, 2), core.fmt(wind, 2),
            core.fmt(direction, 0), core.fmt(gust, 2), core.fmt(clouds, 0), "0", "0",
            core.fmt(precipitation, 2), core.fmt(probability, 0), core.fmt(snow_fraction, 2),
            core.fmt(pressure, 1), core.fmt(humidity, 0), core.fmt(item.get("cape"), 0),
            str(core.DIAGNOSTIC_PICTO if diagnostic else loxone_picto(item)), core.fmt(radiation, 0),
        ]
        if len(row) != core.COLUMNS:
            raise RuntimeError(f"Row {index} has {len(row)} columns, expected {core.COLUMNS}")
        rows.append(";".join(row))
    return rows


# The core validator must use the protocol range, not the emulator's 1..35 range.
core.VALID_PICTOS = VALID_LOXONE_PICTOS
core.build_rows = enhanced_build_rows


if __name__ == "__main__":
    core.main()
