#!/usr/bin/env python3
import json
import logging
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

HOST = "0.0.0.0"
PORT = 6066
HA_API = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("weather4lox-ha")


def options():
    try:
        with open("/data/options.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log.warning("Could not read /data/options.json: %s", exc)
        return {}


def ha_get(path):
    if not TOKEN:
        raise RuntimeError("SUPERVISOR_TOKEN is not available")
    req = Request(HA_API + path, headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    with urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


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


def weather_snapshot():
    o = options()
    entity = o.get("weather_entity", "weather.openweathermap")
    data = state(entity)
    attrs = data.get("attributes", {})

    result = {
        "entity": entity,
        "state": data.get("state"),
        "temperature": num(o.get("temperature_sensor")) if o.get("temperature_sensor") else attrs.get("temperature"),
        "feels_like": num(o.get("feels_like_sensor")) if o.get("feels_like_sensor") else attrs.get("apparent_temperature"),
        "humidity": num(o.get("humidity_sensor")) if o.get("humidity_sensor") else attrs.get("humidity"),
        "pressure": num(o.get("pressure_sensor")) if o.get("pressure_sensor") else attrs.get("pressure"),
        "clouds": num(o.get("cloud_sensor")) if o.get("cloud_sensor") else attrs.get("cloud_coverage"),
        "wind_speed": num(o.get("wind_speed_sensor")) if o.get("wind_speed_sensor") else attrs.get("wind_speed"),
        "wind_gust": num(o.get("wind_gust_sensor")) if o.get("wind_gust_sensor") else attrs.get("wind_gust_speed"),
        "wind_direction": num(o.get("wind_direction_sensor")) if o.get("wind_direction_sensor") else attrs.get("wind_bearing"),
        "rain": num(o.get("rain_sensor")),
        "snow": num(o.get("snow_sensor")),
        "raw_attributes": attrs,
    }
    log.info("HA weather snapshot: %s", json.dumps(result, ensure_ascii=False, default=str))
    return result


def loxone_pictocode(condition):
    mapping = {
        "clear-night": 1,
        "sunny": 2,
        "partlycloudy": 3,
        "cloudy": 4,
        "rainy": 5,
        "pouring": 6,
        "snowy": 7,
        "snowy-rainy": 8,
        "fog": 9,
        "windy": 10,
        "windy-variant": 10,
        "lightning": 11,
        "lightning-rainy": 12,
        "hail": 13,
        "exceptional": 0,
    }
    return mapping.get(condition, 0)


def forecast_response(query):
    w = weather_snapshot()
    coord = query.get("coord", [""])[0]
    asl = query.get("asl", [""])[0]
    user = query.get("user", [""])[0]
    fmt = query.get("format", [""])[0]
    new_api = query.get("new_api", [""])[0]

    log.info("Loxone request: user=%s coord=%s asl=%s format=%s new_api=%s", user, coord, asl, fmt, new_api)

    now = datetime.now(timezone.utc).astimezone()
    temperature = w["temperature"] if w["temperature"] is not None else 0
    feels = w["feels_like"] if w["feels_like"] is not None else temperature
    wind = w["wind_speed"] if w["wind_speed"] is not None else 0
    direction = w["wind_direction"] if w["wind_direction"] is not None else 0
    gust = w["wind_gust"] if w["wind_gust"] is not None else wind
    clouds = w["clouds"] if w["clouds"] is not None else 0
    rain = w["rain"] if w["rain"] is not None else 0
    snow = w["snow"] if w["snow"] is not None else 0
    pressure = w["pressure"] if w["pressure"] is not None else 0
    humidity = w["humidity"] if w["humidity"] is not None else 0
    picto = loxone_pictocode(w["state"])

    header = "id;name;longitude;latitude;height (m.asl.);country;timezone;utc-timedifference;sunrise;sunset;local date;weekday;local time;temperature(C);feeledTemperature(C);windspeed (km/h);winddirection(degr);wind gust(km/h);low clouds(%);medium clouds(%);high clouds(%);precipitation(mm);probability of Precip(%);snowFraction;sea level pressure(hPa);relative humidity(%);CAPE;picto-code;radiation (W/m2)"
    station = f"0;Home Assistant;{coord};{asl};Germany;Europe/Berlin;0;;;;{now:%Y-%m-%d};{now:%a};{now:%H:%M};{temperature:.2f};{feels:.2f};{wind:.2f};{direction:.0f};{gust:.2f};{clouds:.0f};{clouds:.0f};{clouds:.0f};{rain:.2f};0;{snow:.2f};{pressure:.1f};{humidity:.0f};0;{picto};0"

    body = "<mb_metadata>\n" + header + "\n</mb_metadata>\n\n<valid_until>" + f"{now.date()}" + "</valid_until>\n\n<station>\n" + station + "\n</station>\n"
    log.info("Sending Weather4Lox response (%d bytes)", len(body.encode("utf-8")))
    return body


class Handler(BaseHTTPRequestHandler):
    server_version = "Weather4LoxHA/0.1.0"

    def log_message(self, fmt, *args):
        log.info("HTTP %s - %s", self.address_string(), fmt % args)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        log.info("REQUEST %s %s query=%s", self.command, parsed.path, query)

        try:
            if parsed.path == "/health":
                body = "lox-weather-ha-test: OK\n"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
            elif parsed.path in ("/forecast", "/forecast/"):
                body = forecast_response(query)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
            elif parsed.path == "/raw":
                body = json.dumps(weather_snapshot(), ensure_ascii=False, indent=2, default=str)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
            else:
                self.send_response(404)
                body = "Not found\n"
                self.send_header("Content-Type", "text/plain; charset=utf-8")
            encoded = body.encode("utf-8")
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
    log.info("Weather4Lox HA test server starting on %s:%s", HOST, PORT)
    log.info("Home Assistant API: %s", HA_API)
    log.info("Configured options: %s", json.dumps(options(), ensure_ascii=False))
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
