#!/usr/bin/env python3
import json
import logging
import os
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

HOST = "0.0.0.0"
PORT = 6066
HA_API = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
TARGET_HOURS = 181  # Loxone Gen 1 expects roughly seven days of hourly data.

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("weather4lox-ha")


def options():
    try:
        with open("/data/options.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log.warning("Could not read /data/options.json: %s", exc)
        return {}


def ha_request(method, path, payload=None):
    if not TOKEN:
        raise RuntimeError("SUPERVISOR_TOKEN is not available")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(
        HA_API + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urlopen(req, timeout=20) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def ha_get(path):
    return ha_request("GET", path)


def ha_service(domain, service, payload, return_response=False):
    suffix = "?return_response" if return_response else ""
    return ha_request("POST", f"/services/{domain}/{service}{suffix}", payload)


def state(entity_id):
    return ha_get("/states/" + entity_id)


def value(entity_id):
    if not entity_id:
        return None
    try:
        return state(entity_id).get("state")
    except Exception as exc:
        log.warning("Unable to read %s: %s", entity_id, exc)
        return None


def num(entity_id):
    try:
        v = value(entity_id)
        return float(v) if v not in (None, "unknown", "unavailable") else None
    except Exception:
        return None


def selected_weather_entity(o):
    provider = o.get("weather_provider", "openweathermap")
    if provider == "dwd":
        return o.get("dwd_weather_entity", "weather.wertingen")
    return o.get("weather_entity", "weather.openweathermap")


def weather_snapshot():
    o = options()
    provider = o.get("weather_provider", "openweathermap")
    entity = selected_weather_entity(o)
    data = state(entity)
    attrs = data.get("attributes", {})
    use_sensors = provider == "openweathermap"
    result = {
        "provider": provider,
        "entity": entity,
        "state": data.get("state"),
        "temperature": num(o.get("temperature_sensor")) if use_sensors else attrs.get("temperature"),
        "feels_like": num(o.get("feels_like_sensor")) if use_sensors else attrs.get("apparent_temperature"),
        "humidity": num(o.get("humidity_sensor")) if use_sensors else attrs.get("humidity"),
        "pressure": num(o.get("pressure_sensor")) if use_sensors else attrs.get("pressure"),
        "clouds": num(o.get("cloud_sensor")) if use_sensors else attrs.get("cloud_coverage"),
        "wind_speed": num(o.get("wind_speed_sensor")) if use_sensors else attrs.get("wind_speed"),
        "wind_gust": num(o.get("wind_gust_sensor")) if use_sensors else attrs.get("wind_gust_speed"),
        "wind_direction": num(o.get("wind_direction_sensor")) if use_sensors else attrs.get("wind_bearing"),
        "rain": num(o.get("rain_sensor")) if use_sensors else None,
        "snow": num(o.get("snow_sensor")) if use_sensors else None,
        "raw_attributes": attrs,
    }
    log.info("Weather provider=%s entity=%s snapshot=%s", provider, entity, json.dumps(result, ensure_ascii=False, default=str))
    return result


def get_hourly_forecast():
    o = options()
    entity = selected_weather_entity(o)
    log.info("Requesting hourly forecast from Home Assistant: %s", entity)
    response = ha_service("weather", "get_forecasts", {"entity_id": entity, "type": "hourly"}, return_response=True)
    service_response = response.get("service_response", {})
    entity_response = service_response.get(entity, {})
    forecast = entity_response.get("forecast", [])
    if not forecast:
        log.warning("No hourly forecast found. HA response: %s", json.dumps(response, ensure_ascii=False, default=str))
        return []

    forecast = sorted(forecast, key=lambda item: item.get("datetime", ""))
    log.info("Home Assistant returned %d hourly forecast entries", len(forecast))
    if len(forecast) < TARGET_HOURS:
        log.warning(
            "Only %d hourly forecast entries available; %d are required for the full seven-day Loxone report. "
            "This may be caused by the weather provider/API plan.",
            len(forecast), TARGET_HOURS,
        )
    return forecast[:TARGET_HOURS]


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def loxone_pictocode(condition):
    mapping = {
        "clear-night": 1,
        "sunny": 2,
        "partlycloudy": 7,
        "cloudy": 9,
        "rainy": 12,
        "pouring": 12,
        "snowy": 12,
        "snowy-rainy": 12,
        "fog": 10,
        "windy": 10,
        "windy-variant": 10,
        "lightning": 11,
        "lightning-rainy": 12,
        "hail": 12,
        "exceptional": 10,
    }
    return mapping.get(condition, 9)


def safe_float(value, default=0.0):
    try:
        if value in (None, "unknown", "unavailable", ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def station_name():
    try:
        entity = selected_weather_entity(options())
        data = state(entity)
        return data.get("attributes", {}).get("friendly_name", "Home Assistant")
    except Exception:
        return "Home Assistant"


def get_sun_times():
    try:
        attrs = state("sun.sun").get("attributes", {})
        return parse_dt(attrs.get("next_rising")), parse_dt(attrs.get("next_setting"))
    except Exception:
        return None, None


def forecast_response(query):
    w = weather_snapshot()
    coord = query.get("coord", [""])[0]
    asl = query.get("asl", [""])[0]
    user = query.get("user", [""])[0]
    fmt = query.get("format", [""])[0]
    new_api = query.get("new_api", [""])[0]
    log.info("Loxone request: user=%s coord=%s asl=%s format=%s new_api=%s", user, coord, asl, fmt, new_api)

    try:
        longitude, latitude = [p.strip() for p in coord.split(",", 1)]
    except ValueError:
        longitude, latitude = "", ""
        log.warning("Unexpected coord parameter: %r", coord)

    forecast = get_hourly_forecast()
    if not forecast:
        raise RuntimeError("Home Assistant returned no hourly forecast")

    sunrise, sunset = get_sun_times()
    name = station_name()
    now = datetime.now().astimezone()
    valid_until = (now + timedelta(days=7)).date()

    header = (
        "id;name;longitude;latitude;height (m.asl.);country;timezone;utc-timedifference;"
        "sunrise;sunset;local date;weekday;local time;temperature(C);feeledTemperature(C);"
        "windspeed(km/h);winddirection(degr);wind gust(km/h);low clouds(%);medium clouds(%);"
        "high clouds(%);precipitation(mm);probability of Precip(%);snowFraction;"
        "sea level pressure(hPa);relative humidity(%);CAPE;picto-code;radiation (W/m2)"
    )

    rows = []
    for index, item in enumerate(forecast):
        dt = parse_dt(item.get("datetime")) or now
        local_dt = dt.astimezone()
        condition = item.get("condition", "cloudy")
        temperature = safe_float(item.get("temperature"), safe_float(w.get("temperature")))
        apparent = safe_float(item.get("apparent_temperature"), temperature)
        wind_speed = safe_float(item.get("wind_speed"), safe_float(w.get("wind_speed")))
        wind_bearing = safe_float(item.get("wind_bearing"), safe_float(w.get("wind_direction")))
        wind_gust = safe_float(item.get("wind_gust_speed"), safe_float(w.get("wind_gust"), wind_speed))
        cloud = safe_float(item.get("cloud_coverage"), safe_float(w.get("clouds")))
        precipitation = safe_float(item.get("precipitation"), 0)
        precipitation_probability = safe_float(item.get("precipitation_probability"), 0)
        pressure = safe_float(item.get("pressure"), safe_float(w.get("pressure")))
        humidity = safe_float(item.get("humidity"), safe_float(w.get("humidity")))
        snow_fraction = 1.0 if condition in ("snowy", "snowy-rainy") else 0.0
        picto = loxone_pictocode(condition)
        sunrise_text = sunrise.astimezone().strftime("%H:%M") if sunrise else ""
        sunset_text = sunset.astimezone().strftime("%H:%M") if sunset else ""

        row = [
            str(index), name, longitude, latitude, asl, "Germany", "Europe/Berlin", "",
            sunrise_text, sunset_text,
            local_dt.strftime("%d.%m.%Y"), local_dt.strftime("%a"), local_dt.strftime("%H"),
            f"{temperature:.2f}", f"{apparent:.2f}", f"{wind_speed:.2f}",
            f"{wind_bearing:.0f}", f"{wind_gust:.2f}",
            f"{cloud:.0f}", f"{cloud:.0f}", f"{cloud:.0f}",
            f"{precipitation:.2f}", f"{precipitation_probability:.0f}", f"{snow_fraction:.2f}",
            f"{pressure:.1f}", f"{humidity:.0f}", "0", str(picto), "0",
        ]
        rows.append(";".join(row))

    body = (
        "<mb_metadata>\n" + header + "\n</mb_metadata>\n\n"
        + f"<valid_until>{valid_until}</valid_until>\n\n"
        + "<station>\n" + "\n".join(rows) + "\n</station>\n"
    )
    log.info("Sending Weather4Lox response: %d forecast rows, %d bytes, valid_until=%s", len(rows), len(body.encode("utf-8")), valid_until)
    return body


class Handler(BaseHTTPRequestHandler):
    server_version = "Weather4LoxHA/0.2.0"

    def log_message(self, fmt, *args):
        log.info("HTTP %s - %s", self.address_string(), fmt % args)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        log.info("REQUEST %s %s query=%s", self.command, parsed.path, query)
        try:
            if parsed.path == "/health":
                status, body, content_type = 200, "lox-weather-ha-test: OK\n", "text/plain; charset=utf-8"
            elif parsed.path in ("/forecast", "/forecast/"):
                status, body, content_type = 200, forecast_response(query), "text/plain; charset=utf-8"
            elif parsed.path == "/raw":
                status, body, content_type = 200, json.dumps(weather_snapshot(), ensure_ascii=False, indent=2, default=str), "application/json; charset=utf-8"
            elif parsed.path in ("/raw/forecast", "/debug/forecast"):
                status, body, content_type = 200, json.dumps(get_hourly_forecast(), ensure_ascii=False, indent=2, default=str), "application/json; charset=utf-8"
            else:
                status, body, content_type = 404, "Not found\n", "text/plain; charset=utf-8"

            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        except Exception as exc:
            log.exception("Request failed: %s", exc)
            body = f"Internal Server Error: {exc}\n".encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


if __name__ == "__main__":
    log.info("Weather4Lox HA server starting on %s:%s", HOST, PORT)
    log.info("Home Assistant API: %s", HA_API)
    log.info("Configured options: %s", json.dumps(options(), ensure_ascii=False))
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
