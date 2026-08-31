#!/usr/bin/env python3
"""Persist and serve the Weather4Lox v4 JSON files used by the LoxBerry client."""
from __future__ import annotations

import json
import math
import os
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import server_035 as core

DATA_DIR = Path("/data/weather4lox")
CURRENT_FILE = DATA_DIR / "current.json"
DAILY_FILE = DATA_DIR / "dailyforecast.json"
HOURLY_FILE = DATA_DIR / "hourlyforecast.json"
JSON_REFRESH_CURRENT = 300
JSON_REFRESH_FORECAST = 1800
HOURLY_LIMIT = 96
DAILY_LIMIT = 8

_REFRESH_LOCK = threading.Lock()
_LAST_REFRESH = None

# Weather4Lox v4 uses these stable internal names and the corresponding
# Loxone Gen-1 protocol codes. The source schema calls these weather4lox/loxone.
CONDITIONS = {
    "sunny": ("Klarer Himmel", "clear", "SKC", 1),
    "clear-night": ("Klarer Himmel", "clear", "SKC", 1),
    "partlycloudy": ("Teilweise bewölkt", "partly_cloudy", "SCT", 3),
    "cloudy": ("Bedeckt", "overcast", "OVC", 5),
    "fog": ("Nebel", "fog", "OVC", 6),
    "rainy": ("Regen", "overcast_rain_2", "OVC", 11),
    "pouring": ("Starker Regen", "overcast_rain_3", "OVC", 12),
    "snowy": ("Schnee", "overcast_snow_2", "OVC", 21),
    "snowy-rainy": ("Schneeregen", "overcast_sleet_2", "OVC", 26),
    "lightning": ("Gewitter", "overcast_thunderstorm_2", "OVC", 18),
    "lightning-rainy": ("Gewitter mit Regen", "overcast_thunderstorm_2", "OVC", 19),
    "hail": ("Hagel", "overcast_hail_2", "OVC", 23),
    "windy": ("Windig", "wind", "BKN", 4),
    "windy-variant": ("Windig und bewölkt", "wind", "BKN", 4),
    "exceptional": ("Außergewöhnlich", "no_data", "OVC", 5),
}


def _opts():
    return core.opts()


def _finite(value, default=None):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _iso_local(value):
    dt = core.parse_dt(value)
    return dt.astimezone() if dt else datetime.now().astimezone()


def _epoch(value):
    return int(_iso_local(value).timestamp())


def _generated_at():
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _location(attrs=None):
    o = _opts()
    attrs = attrs or {}
    return {
        "city": o.get("location_city", "Wertingen"),
        "country": o.get("country", "Deutschland"),
        "countryCode": o.get("country_code", "DE"),
        "elevation": _finite(o.get("elevation_m", 450)),
        "latitude": _finite(o.get("latitude", 48.56)),
        "longitude": _finite(o.get("longitude", 10.681)),
        "timezone": o.get("timezone", "Europe/Berlin"),
        "tzOffset": datetime.now().astimezone().strftime("%z"),
        "tzShort": datetime.now().astimezone().tzname() or "CET",
    }


def _metadata(filename, label="Home Assistant"):
    generated = _generated_at()
    return {
        "filename": str(filename),
        "generatedAt": generated,
        "grabberLabel": label,
        "grabberScript": "weather4lox-ha.py",
        "schemaVersion": "v1.0",
    }


def _condition(condition):
    return CONDITIONS.get(str(condition or "cloudy").lower(), CONDITIONS["cloudy"])


def _cardinal(degrees):
    value = _finite(degrees)
    if value is None:
        return None
    return ("N", "NE", "E", "SE", "S", "SW", "W", "NW")[int((value % 360 + 22.5) // 45) % 8]


def _moon(now=None):
    """Return the same compact moon fields used by Weather4Lox v4."""
    now = now or datetime.now(timezone.utc)
    known_new_moon = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    synodic = 29.530588853
    age = ((now - known_new_moon).total_seconds() / 86400.0) % synodic
    phase = age / synodic * 100.0
    illumination = (1 - math.cos(2 * math.pi * age / synodic)) / 2 * 100.0
    return {
        "age": round(age, 1),
        "direction": "waxing" if age < synodic / 2 else "waning",
        "percent": round(illumination, 1),
        "phase": round(phase, 1),
    }


def _sun_times(attrs):
    """Use Home Assistant's sun timestamps and return today's local HH:MM values."""
    result = {"sunrise": "", "sunset": ""}
    try:
        sun = core.get_state("sun.sun").get("attributes", {})
    except Exception:
        sun = {}
    today = datetime.now().astimezone().date()
    for key, attr in (("sunrise", "next_rising"), ("sunset", "next_setting")):
        dt = core.parse_dt(sun.get(attr))
        if dt:
            local = dt.astimezone()
            if local.date() != today:
                local -= timedelta(days=1)
            result[key] = local.strftime("%H:%M")
    # Some providers expose the times directly; prefer them when present.
    for key in result:
        value = attrs.get(key) or attrs.get(f"{key}_time")
        if isinstance(value, str) and value:
            result[key] = value[:5]
    return result


def _current():
    snap = core.snapshot()
    attrs = snap.get("raw_attributes", {}) or {}
    condition = str(snap.get("state") or "cloudy")
    description, weather4lox, metar, loxone = _condition(condition)
    now = datetime.now().astimezone().replace(microsecond=0)
    sun = _sun_times(attrs)
    rain = _finite(snap.get("rain"), 0.0) or 0.0
    snow = _finite(snap.get("snow"), None)
    visibility = _finite(attrs.get("visibility"), None)
    if visibility is not None and str(attrs.get("visibility_unit", "km")).lower() == "km":
        visibility *= 1000
    wind = _finite(snap.get("wind_speed"), 0.0) or 0.0
    gust = _finite(snap.get("wind_gust"), 0.0) or 0.0
    direction = _finite(snap.get("wind_direction"), 0.0) or 0.0
    current = {
        "cloudCover": _finite(snap.get("clouds"), 0.0),
        "dewpoint": _finite(attrs.get("dew_point"), None),
        "humidity": _finite(snap.get("humidity"), 0.0),
        "isNight": 1 if condition == "clear-night" else 0,
        "moon": _moon(now.astimezone(timezone.utc)),
        "ozone": _finite(attrs.get("ozone"), None),
        "precipitation": {
            "probability": 0,
            "rain1hr": rain,
            "rainToday": rain,
            "snow1h": snow,
            "snowToday": snow,
            "type": str(attrs.get("precipitation_kind") or "none").lower(),
        },
        "pressure": _finite(snap.get("pressure"), 0.0),
        "solarRadiation": _finite(attrs.get("solar_radiation"), None),
        "sunrise": sun["sunrise"],
        "sunset": sun["sunset"],
        "temperature": {
            "air": _finite(snap.get("temperature"), 0.0),
            "feelsLike": _finite(snap.get("feels_like"), _finite(snap.get("temperature"), 0.0)),
            "heatIndex": None,
            "windChill": None,
        },
        "time": {
            "datetime": now.isoformat(),
            "epoch": int(now.timestamp()),
            "timezone": _location()["timezone"],
            "tzOffset": now.strftime("%z"),
            "tzShort": now.tzname() or "CET",
        },
        "uvIndex": _finite(attrs.get("uv_index"), 0),
        "visibility": visibility,
        "weatherCode": {
            "description": description,
            "image": None,
            "loxone": loxone,
            "metar": metar,
            "weather4lox": weather4lox,
        },
        "wind": {
            "dirLabel": _cardinal(direction),
            "direction": direction,
            "gust": gust,
            "speed": wind,
        },
    }
    return {
        "current": current,
        "generatedAt": _generated_at(),
        "location": _location(attrs),
        "openweather": _metadata(CURRENT_FILE),
        "refresh": JSON_REFRESH_CURRENT,
    }


def _hourly_item(item, index):
    dt = _iso_local(item.get("datetime"))
    description, weather4lox, metar, loxone = _condition(item.get("condition"))
    direction = _finite(item.get("wind_bearing"), 0.0) or 0.0
    return {
        "cloudCover": _finite(item.get("cloud_coverage"), 0),
        "dewpoint": _finite(item.get("dew_point"), None),
        "hour": index,
        "humidity": _finite(item.get("humidity"), 0),
        "isNight": 1 if dt.hour < 6 or dt.hour >= 21 else 0,
        "moon": _moon(dt.astimezone(timezone.utc)),
        "ozone": None,
        "precipitation": {
            "probability": _finite(item.get("precipitation_probability"), 0),
            "rainHigh": _finite(item.get("precipitation"), None),
            "rainLow": _finite(item.get("precipitation"), None),
            "snowHigh": None,
            "snowLow": None,
            "type": "rain" if _finite(item.get("precipitation"), 0) else "none",
        },
        "pressure": _finite(item.get("pressure"), 0),
        "solarRadiation": None,
        "temperature": {
            "air": _finite(item.get("temperature"), 0),
            "feelsLike": _finite(item.get("apparent_temperature"), _finite(item.get("temperature"), 0)),
            "heatIndex": None,
            "windChill": None,
        },
        "time": {"datetime": dt.isoformat(), "epoch": int(dt.timestamp())},
        "uvIndex": _finite(item.get("uv_index"), 0),
        "visibility": _finite(item.get("visibility"), None),
        "weatherCode": {
            "description": description,
            "loxone": loxone,
            "metar": metar,
            "weather4lox": weather4lox,
        },
        "wind": {
            "cardinal": _cardinal(direction),
            "direction": direction,
            "gust": _finite(item.get("wind_gust_speed"), 0),
            "speed": _finite(item.get("wind_speed"), 0),
        },
    }


def _hourly():
    entity = core.selected_entity()
    raw = core.service_forecast(entity, "hourly")[:HOURLY_LIMIT]
    items = [_hourly_item(item, i) for i, item in enumerate(raw)]
    return {
        "generatedAt": _generated_at(),
        "hourlyforecast": items,
        "location": _location(),
        "openweather": _metadata(HOURLY_FILE),
        "refresh": JSON_REFRESH_FORECAST,
    }


def _daily_from_hourly(hourly):
    grouped = defaultdict(list)
    for item in hourly:
        grouped[_iso_local(item.get("datetime")).date()].append(item)
    result = []
    for day_index, date in enumerate(sorted(grouped)[:DAILY_LIMIT]):
        values = grouped[date]
        temps = [_finite(x.get("temperature")) for x in values]
        temps = [x for x in temps if x is not None]
        lows = min(temps) if temps else 0
        highs = max(temps) if temps else 0
        humidity = [_finite(x.get("humidity")) for x in values]
        humidity = [x for x in humidity if x is not None]
        condition = values[len(values) // 2].get("condition") or "cloudy"
        description, weather4lox, metar, loxone = _condition(condition)
        dt = datetime.combine(date, datetime.min.time(), tzinfo=datetime.now().astimezone().tzinfo)
        result.append({
            "cloudCover": round(sum(_finite(x.get("cloud_coverage"), 0) for x in values) / len(values)),
            "day": day_index,
            "dewpoint": None,
            "heatIndex": None,
            "humidity": {"avg": round(sum(humidity) / len(humidity)) if humidity else None, "max": max(humidity) if humidity else None, "min": min(humidity) if humidity else None},
            "moon": _moon(dt.astimezone(timezone.utc)),
            "ozone": None,
            "precipitation": {"duration": None, "probability": max(_finite(x.get("precipitation_probability"), 0) for x in values), "rainHigh": sum(_finite(x.get("precipitation"), 0) for x in values), "snowHigh": None, "type": "rain" if any(_finite(x.get("precipitation"), 0) > 0 for x in values) else "none"},
            "pressure": round(sum(_finite(x.get("pressure"), 0) for x in values) / len(values), 1),
            "solarRadiation": None,
            "sunrise": "",
            "sunset": "",
            "temperature": {"max": {"air": highs, "feelsLike": None, "heatIndex": None}, "min": {"air": lows, "feelsLike": None, "windChill": None}},
            "time": {"datetime": dt.isoformat(), "epoch": int(dt.timestamp())},
            "uvIndex": max(_finite(x.get("uv_index"), 0) for x in values),
            "visibility": None,
            "weatherCode": {"description": description, "image": None, "loxone": loxone, "metar": metar, "weather4lox": weather4lox},
            "wind": {"avg": {"dirLabel": _cardinal(_finite(values[0].get("wind_bearing"), 0)), "direction": _finite(values[0].get("wind_bearing"), 0), "gust": max(_finite(x.get("wind_gust_speed"), 0) for x in values), "speed": round(sum(_finite(x.get("wind_speed"), 0) for x in values) / len(values), 1)}, "max": {"dirLabel": None, "direction": None, "gust": None, "speed": None}},
        })
    return result


def _daily(hourly_raw=None):
    entity = core.selected_entity()
    try:
        raw = core.service_forecast(entity, "daily")[:DAILY_LIMIT]
    except Exception:
        raw = []
    if raw:
        # Normalize HA's daily response to the v4 envelope while retaining source values.
        converted = []
        for i, item in enumerate(raw):
            dt = _iso_local(item.get("datetime"))
            condition = item.get("condition") or "cloudy"
            description, weather4lox, metar, loxone = _condition(condition)
            temp = _finite(item.get("temperature"), 0)
            templow = _finite(item.get("templow"), temp)
            converted.append({
                "cloudCover": _finite(item.get("cloud_coverage"), 0), "day": i, "dewpoint": _finite(item.get("dew_point"), None), "heatIndex": None,
                "humidity": {"avg": _finite(item.get("humidity"), None), "max": None, "min": None}, "moon": _moon(dt.astimezone(timezone.utc)), "ozone": None,
                "precipitation": {"duration": None, "probability": _finite(item.get("precipitation_probability"), 0), "rainHigh": _finite(item.get("precipitation"), None), "snowHigh": None, "type": "rain" if _finite(item.get("precipitation"), 0) else "none"},
                "pressure": _finite(item.get("pressure"), 0), "solarRadiation": None, "sunrise": "", "sunset": "",
                "temperature": {"max": {"air": temp, "feelsLike": _finite(item.get("apparent_temperature"), None), "heatIndex": None}, "min": {"air": templow, "feelsLike": None, "windChill": None}},
                "time": {"datetime": dt.isoformat(), "epoch": int(dt.timestamp())}, "uvIndex": _finite(item.get("uv_index"), 0), "visibility": None,
                "weatherCode": {"description": description, "image": None, "loxone": loxone, "metar": metar, "weather4lox": weather4lox},
                "wind": {"avg": {"dirLabel": _cardinal(_finite(item.get("wind_bearing"), 0)), "direction": _finite(item.get("wind_bearing"), 0), "gust": _finite(item.get("wind_gust_speed"), 0), "speed": _finite(item.get("wind_speed"), 0)}, "max": {"dirLabel": None, "direction": None, "gust": None, "speed": None}},
            })
    else:
        converted = _daily_from_hourly(hourly_raw or core.service_forecast(entity, "hourly"))
    return {"dailyforecast": converted, "generatedAt": _generated_at(), "location": _location(), "openweather": _metadata(DAILY_FILE), "refresh": JSON_REFRESH_FORECAST}


def _write(path, payload):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")
    os.replace(tmp, path)


def refresh(force=False):
    global _LAST_REFRESH
    with _REFRESH_LOCK:
        now = datetime.now(timezone.utc)
        if not force and _LAST_REFRESH and (now - _LAST_REFRESH).total_seconds() < JSON_REFRESH_CURRENT:
            return
        hourly = core.service_forecast(core.selected_entity(), "hourly")
        _write(CURRENT_FILE, _current())
        _write(HOURLY_FILE, {**_hourly(), "generatedAt": _generated_at()})
        _write(DAILY_FILE, _daily(hourly))
        _LAST_REFRESH = now


def refresh_loop():
    while True:
        try:
            refresh()
        except Exception as exc:
            core.log.exception("JSON refresh failed: %s", exc)
        # Current data is intentionally refreshed more often than the forecast files.
        threading.Event().wait(JSON_REFRESH_CURRENT)


def install_handler():
    original_get = core.Handler.do_GET

    def do_get(handler):
        path = handler.path.split("?", 1)[0].rstrip("/")
        mapping = {
            "/plugins/weather4lox/current.json": CURRENT_FILE,
            "/plugins/weather4lox/dailyforecast.json": DAILY_FILE,
            "/plugins/weather4lox/hourlyforecast.json": HOURLY_FILE,
        }
        target = mapping.get(path)
        if target:
            try:
                refresh()
                data = target.read_bytes()
                handler.send_response(200)
                handler.send_header("Content-Type", "application/json; charset=utf-8")
                handler.send_header("Content-Length", str(len(data)))
                handler.send_header("Cache-Control", "no-store")
                handler.end_headers()
                handler.wfile.write(data)
            except Exception as exc:
                core.log.exception("JSON endpoint failed: %s", exc)
                handler.send_error(500, str(exc))
            return
        original_get(handler)

    core.Handler.do_GET = do_get


def main():
    core.VERSION = "0.3.7"
    core.Handler.server_version = "Weather4LoxHA/0.3.7"
    install_handler()
    try:
        refresh(force=True)
    except Exception as exc:
        core.log.exception("Initial JSON generation failed: %s", exc)
    threading.Thread(target=refresh_loop, name="weather4lox-json-refresh", daemon=True).start()
    core.main()


if __name__ == "__main__":
    main()
