#!/usr/bin/env python3
"""Weather4Lox v4 JSON compatibility layer.

Mirrors the JSON envelope and field names produced by the current
Weather4Lox v4 grabbers. Persistent files live under /data/weather4lox and
are exposed by the existing /plugins/weather4lox/*.json endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import live_data
import server_035 as core

PROVIDER_LABELS = {
    "openweathermap": "OpenWeather",
    "dwd": "DWD",
    "custom": "Home Assistant",
}


def _number(value: Any, default=None):
    return live_data._finite(value, default)


def _time(value):
    return live_data._iso_local(value)


def _metadata(path, provider):
    return {
        "filename": str(path),
        "generatedAt": live_data._generated_at(),
        "grabberLabel": PROVIDER_LABELS.get(str(provider), "Home Assistant"),
        "grabberScript": "weather4lox-ha.py",
        "schemaVersion": "v1.0",
    }


def _weather_code(condition, include_image=False):
    description, weather4lox, metar, loxone = live_data._condition(condition)
    result = {
        "description": description,
        "loxone": str(loxone),
        "metar": metar,
        "weather4lox": weather4lox,
    }
    if include_image:
        result["image"] = None
    return result


def _precip_type(item):
    explicit = str(item.get("precipitation_kind") or item.get("precipitation_type") or "").lower()
    if explicit in {"rain", "snow", "mixed", "none"}:
        return explicit
    rain = _number(item.get("precipitation"), 0) or 0
    snow = _number(item.get("snow"), 0) or 0
    if rain and snow:
        return "mixed"
    if snow:
        return "snow"
    if rain:
        return "rain"
    return "none"


def hourly_item(item, index):
    dt = _time(item.get("datetime"))
    condition = item.get("condition") or "cloudy"
    return {
        "cloudCover": _number(item.get("cloud_coverage"), 0),
        "dewpoint": _number(item.get("dew_point")),
        "hour": index,
        "humidity": _number(item.get("humidity"), 0),
        "isNight": int(item.get("isNight", dt.hour < 6 or dt.hour >= 21)),
        "moon": live_data._moon(dt.astimezone(timezone.utc)),
        "ozone": _number(item.get("ozone")),
        "precipitation": {
            "duration": _number(item.get("precipitation_duration")),
            "probability": _number(item.get("precipitation_probability"), 0),
            "rainHigh": _number(item.get("precipitation")),
            "rainLow": _number(item.get("precipitation_low")),
            "snowHigh": _number(item.get("snow")),
            "snowLow": _number(item.get("snow_low")),
            "type": _precip_type(item),
        },
        "pressure": _number(item.get("pressure"), 0),
        "solarRadiation": _number(item.get("solar_radiation")),
        "temperature": {
            "air": _number(item.get("temperature"), 0),
            "feelsLike": _number(item.get("apparent_temperature"), _number(item.get("temperature"), 0)),
            "heatIndex": _number(item.get("heat_index")),
            "windChill": _number(item.get("wind_chill")),
        },
        "time": {"datetime": dt.isoformat(), "epoch": int(dt.timestamp())},
        "uvIndex": _number(item.get("uv_index")),
        "visibility": _number(item.get("visibility")),
        "weatherCode": _weather_code(condition),
        "wind": {
            "dirLabel": live_data._cardinal(item.get("wind_bearing")),
            "direction": _number(item.get("wind_bearing"), 0),
            "gust": _number(item.get("wind_gust_speed")),
            "speed": _number(item.get("wind_speed"), 0),
        },
    }


def daily_from_hourly(hourly):
    grouped = {}
    for item in hourly:
        grouped.setdefault(_time(item.get("datetime")).date(), []).append(item)

    result = []
    for day_index, date in enumerate(sorted(grouped)[: live_data.DAILY_LIMIT]):
        values = grouped[date]
        temps = [x for x in (_number(v.get("temperature")) for v in values) if x is not None]
        feels = [x for x in (_number(v.get("apparent_temperature")) for v in values) if x is not None]
        humidity = [x for x in (_number(v.get("humidity")) for v in values) if x is not None]
        rain = [x for x in (_number(v.get("precipitation")) for v in values) if x is not None]
        snow = [x for x in (_number(v.get("snow")) for v in values) if x is not None]
        wind_speed = [x for x in (_number(v.get("wind_speed")) for v in values) if x is not None]
        wind_gust = [x for x in (_number(v.get("wind_gust_speed")) for v in values) if x is not None]
        bearings = [x for x in (_number(v.get("wind_bearing")) for v in values) if x is not None]
        condition = values[len(values) // 2].get("condition") or "cloudy"
        tz = _time(values[0].get("datetime")).tzinfo
        dt = datetime.combine(date, datetime.min.time(), tzinfo=tz)
        avg_dir = bearings[len(bearings) // 2] if bearings else 0
        result.append({
            "cloudCover": round(sum(_number(v.get("cloud_coverage"), 0) for v in values) / len(values)),
            "day": day_index,
            "dewpoint": None,
            "heatIndex": None,
            "humidity": {"avg": round(sum(humidity) / len(humidity), 1) if humidity else None, "max": max(humidity) if humidity else None, "min": min(humidity) if humidity else None},
            "moon": live_data._moon(dt.astimezone(timezone.utc)),
            "ozone": None,
            "precipitation": {
                "duration": None,
                "probability": max((_number(v.get("precipitation_probability"), 0) for v in values), default=0),
                "rainHigh": sum(rain) if rain else None,
                "rainLow": None,
                "snowHigh": sum(snow) if snow else None,
                "snowLow": None,
                "type": "mixed" if rain and snow else ("rain" if rain else ("snow" if snow else "none")),
            },
            "pressure": round(sum(_number(v.get("pressure"), 0) for v in values) / len(values), 1),
            "solarRadiation": None,
            "sunrise": "",
            "sunset": "",
            "temperature": {
                "max": {"air": max(temps) if temps else 0, "feelsLike": max(feels) if feels else None, "heatIndex": None},
                "min": {"air": min(temps) if temps else 0, "feelsLike": min(feels) if feels else None, "windChill": None},
            },
            "time": {"datetime": dt.isoformat(), "epoch": int(dt.timestamp())},
            "uvIndex": max((_number(v.get("uv_index"), 0) for v in values), default=0),
            "visibility": None,
            "weatherCode": _weather_code(condition, include_image=True),
            "wind": {
                "avg": {"dirLabel": live_data._cardinal(avg_dir), "direction": avg_dir, "gust": max(wind_gust) if wind_gust else None, "speed": round(sum(wind_speed) / len(wind_speed), 1) if wind_speed else None},
                "max": {"dirLabel": live_data._cardinal(avg_dir) if wind_speed else None, "direction": avg_dir if wind_speed else None, "gust": max(wind_gust) if wind_gust else None, "speed": max(wind_speed) if wind_speed else None},
            },
        })
    return result


def daily_from_provider(raw):
    converted = []
    for index, item in enumerate(raw[: live_data.DAILY_LIMIT]):
        dt = _time(item.get("datetime"))
        condition = item.get("condition") or "cloudy"
        temp = item.get("temperature")
        if isinstance(temp, dict):
            temp_max = _number(temp.get("max"), 0)
            temp_min = _number(temp.get("min"), temp_max)
        else:
            temp_max = _number(temp, 0)
            temp_min = _number(item.get("templow"), temp_max)
        feels = item.get("apparent_temperature")
        if isinstance(feels, dict):
            feels_max = _number(feels.get("max"))
            feels_min = _number(feels.get("min"))
        else:
            feels_max = _number(feels)
            feels_min = None
        humidity = item.get("humidity")
        if isinstance(humidity, dict):
            humidity_avg = _number(humidity.get("avg"))
            humidity_min = _number(humidity.get("min"))
            humidity_max = _number(humidity.get("max"))
        else:
            humidity_avg = _number(humidity)
            humidity_min = None
            humidity_max = None
        direction = _number(item.get("wind_bearing"), 0)
        converted.append({
            "cloudCover": _number(item.get("cloud_coverage"), 0),
            "day": index,
            "dewpoint": _number(item.get("dew_point")),
            "heatIndex": _number(item.get("heat_index")),
            "humidity": {"avg": humidity_avg, "max": humidity_max, "min": humidity_min},
            "moon": live_data._moon(dt.astimezone(timezone.utc)),
            "ozone": _number(item.get("ozone")),
            "precipitation": {
                "duration": _number(item.get("precipitation_duration")),
                "probability": _number(item.get("precipitation_probability"), 0),
                "rainHigh": _number(item.get("precipitation")),
                "rainLow": _number(item.get("precipitation_low")),
                "snowHigh": _number(item.get("snow")),
                "snowLow": _number(item.get("snow_low")),
                "type": _precip_type(item),
            },
            "pressure": _number(item.get("pressure"), 0),
            "solarRadiation": _number(item.get("solar_radiation")),
            "sunrise": str(item.get("sunrise") or "")[:5],
            "sunset": str(item.get("sunset") or "")[:5],
            "temperature": {"max": {"air": temp_max, "feelsLike": feels_max, "heatIndex": None}, "min": {"air": temp_min, "feelsLike": feels_min, "windChill": None}},
            "time": {"datetime": dt.isoformat(), "epoch": int(dt.timestamp())},
            "uvIndex": _number(item.get("uv_index"), 0),
            "visibility": _number(item.get("visibility")),
            "weatherCode": _weather_code(condition, include_image=True),
            "wind": {
                "avg": {"dirLabel": live_data._cardinal(direction), "direction": direction, "gust": _number(item.get("wind_gust_speed")), "speed": _number(item.get("wind_speed"))},
                "max": {"dirLabel": None, "direction": None, "gust": None, "speed": None},
            },
        })
    return converted


def refresh(force=False):
    """Write all three v4 JSON files using one normalized forecast."""
    provider = core.opts().get("weather_provider", "openweathermap")
    hourly, source, fallback_count = core.obtain_forecast(force=force)
    try:
        provider_daily = core.service_forecast(core.selected_entity(), "daily")
    except Exception:
        provider_daily = []

    current = live_data._current()["current"]
    generated = live_data._generated_at()
    location = live_data._location()
    common = {"location": location, "generatedAt": generated, "refresh": live_data.JSON_REFRESH_FORECAST}
    files = (
        (live_data.CURRENT_FILE, {**common, "refresh": live_data.JSON_REFRESH_CURRENT, provider: _metadata(live_data.CURRENT_FILE, provider), "current": current}),
        (live_data.HOURLY_FILE, {**common, provider: _metadata(live_data.HOURLY_FILE, provider), "hourlyforecast": [hourly_item(item, i) for i, item in enumerate(hourly[:167])]}),
        (live_data.DAILY_FILE, {**common, provider: _metadata(live_data.DAILY_FILE, provider), "dailyforecast": daily_from_provider(provider_daily) if provider_daily else daily_from_hourly(hourly)}),
    )
    for path, payload in files:
        live_data._write(path, payload)
    core.log.info("Live JSON ready: provider=%s source=%s fallback=%d hourly=%d", provider, source, fallback_count, len(hourly))
    return files
