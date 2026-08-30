#!/usr/bin/env python3
import json
import logging
import math
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from urllib.request import HTTPError, Request, urlopen

HOST = "0.0.0.0"
PORT = 6066
HA_API = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
CACHE_FILE = "/data/forecast_cache.json"
DEFAULT_TARGET_HOURS = 168  # 7 * 24. Weather4Lox itself uses 7 days of hourly data.

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("weather4lox-ha")

cache_lock = threading.Lock()
forecast_cache = None
last_forecast_error = None
request_count = 0
last_request = None


def options():
    try:
        with open("/data/options.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log.warning("Could not read /data/options.json: %s", exc)
        return {}


def debug(message, *args):
    if options().get("debug_logging", True):
        log.debug(message, *args)


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
    try:
        with urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        log.error("HA API HTTP %s for %s %s: %s", exc.code, method, path, error_body)
        raise RuntimeError(f"Home Assistant API HTTP {exc.code}: {error_body}") from exc


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
        return float(v) if v not in (None, "unknown", "unavailable", "") else None
    except Exception:
        return None


def selected_weather_entity(o=None):
    o = o or options()
    provider = o.get("weather_provider", "openweathermap")
    if provider == "dwd":
        return o.get("dwd_weather_entity", "weather.wertingen")
    if provider == "custom":
        return o.get("custom_weather_entity", "weather.openweathermap")
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
    debug("Weather snapshot: %s", json.dumps(result, ensure_ascii=False, default=str))
    return result


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def to_epoch(value):
    dt = parse_dt(value)
    return dt.timestamp() if dt else None


def safe_float(value, default=0.0):
    try:
        if value in (None, "unknown", "unavailable", ""):
            return default
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def load_cache():
    global forecast_cache
    with cache_lock:
        if forecast_cache is not None:
            return forecast_cache
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                forecast_cache = json.load(f)
                log.info("Loaded forecast cache from %s (%d entries)", CACHE_FILE, len(forecast_cache.get("forecast", [])))
        except FileNotFoundError:
            forecast_cache = None
        except Exception as exc:
            log.warning("Could not load forecast cache: %s", exc)
            forecast_cache = None
        return forecast_cache


def save_cache(provider, entity, forecast, source, interpolated_count=0):
    global forecast_cache
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "entity": entity,
        "source": source,
        "interpolated_count": interpolated_count,
        "forecast": forecast,
    }
    tmp = CACHE_FILE + ".tmp"
    with cache_lock:
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp, CACHE_FILE)
            forecast_cache = payload
        except Exception as exc:
            log.warning("Could not persist forecast cache: %s", exc)
    return payload


def cache_age_minutes(cache):
    if not cache or not cache.get("fetched_at"):
        return None
    dt = parse_dt(cache["fetched_at"])
    if not dt:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 60.0)


def cache_is_fresh(cache):
    age = cache_age_minutes(cache)
    ttl = max(1, int(options().get("cache_ttl_minutes", 60)))
    return age is not None and age <= ttl


def get_service_forecast(entity, forecast_type):
    response = ha_service("weather", "get_forecasts", {"entity_id": entity, "type": forecast_type}, return_response=True)
    service_response = response.get("service_response", {})
    entity_response = service_response.get(entity, {})
    forecast = entity_response.get("forecast", [])
    if not isinstance(forecast, list):
        return []
    return sorted(forecast, key=lambda item: item.get("datetime", ""))


def interpolate_numeric(a, b, ratio):
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    try:
        return float(a) + (float(b) - float(a)) * ratio
    except (TypeError, ValueError):
        return a


def normalize_hourly_forecast(hourly, daily, target_hours):
    """Create a one-hour grid. Existing hourly values win; missing points are interpolated.
    Daily values are used as a provider-safe fallback when the hourly provider ends early.
    """
    if not hourly and not daily:
        return [], 0, "none"

    hourly = [x for x in hourly if parse_dt(x.get("datetime"))]
    daily = [x for x in daily if parse_dt(x.get("datetime"))]
    hourly_map = {parse_dt(x["datetime"]).replace(minute=0, second=0, microsecond=0): x for x in hourly}
    daily_map = {parse_dt(x["datetime"]).date(): x for x in daily}

    if hourly:
        start = parse_dt(hourly[0]["datetime"]).replace(minute=0, second=0, microsecond=0)
    else:
        start = datetime.now().astimezone().replace(minute=0, second=0, microsecond=0)

    keys = [start + timedelta(hours=i) for i in range(target_hours)]
    known = sorted(hourly_map)
    result = []
    interpolated = 0

    numeric_fields = [
        "temperature", "apparent_temperature", "humidity", "pressure", "wind_speed",
        "wind_gust_speed", "wind_bearing", "cloud_coverage", "precipitation",
        "precipitation_probability", "uv_index", "visibility"
    ]

    def daily_fallback(key):
        d = daily_map.get(key.date())
        if not d:
            candidates = sorted(daily_map.items(), key=lambda pair: abs((pair[0] - key.date()).days))
            d = candidates[0][1] if candidates else None
        if not d:
            return None
        item = dict(d)
        item["datetime"] = key.isoformat()
        # Daily temperature is usually a mapping of min/max rather than a scalar.
        temp = item.get("temperature")
        if isinstance(temp, dict):
            vals = [v for v in (temp.get("min"), temp.get("max")) if v is not None]
            item["temperature"] = sum(map(float, vals)) / len(vals) if vals else None
        item["_source"] = "daily_fallback"
        return item

    for key in keys:
        if key in hourly_map:
            item = dict(hourly_map[key])
            item["_source"] = "hourly"
            result.append(item)
            continue

        before = next((k for k in reversed(known) if k < key), None)
        after = next((k for k in known if k > key), None)
        item = None
        if before and after and options().get("interpolate_missing_hours", True):
            left = hourly_map[before]
            right = hourly_map[after]
            span = (after - before).total_seconds()
            ratio = (key - before).total_seconds() / span if span else 0
            item = dict(left)
            item["datetime"] = key.isoformat()
            for field in numeric_fields:
                if field in left or field in right:
                    item[field] = interpolate_numeric(left.get(field), right.get(field), ratio)
            item["condition"] = left.get("condition") if ratio < 0.5 else right.get("condition")
            item["_source"] = "interpolated"
            interpolated += 1
        else:
            item = daily_fallback(key)
            if item:
                interpolated += 1

        if item is None and result:
            item = dict(result[-1])
            item["datetime"] = key.isoformat()
            item["_source"] = "last_value_fallback"
            interpolated += 1
        if item:
            result.append(item)

    source = "hourly"
    if any(x.get("_source") == "daily_fallback" for x in result):
        source = "hourly+daily"
    if any(x.get("_source") == "last_value_fallback" for x in result):
        source = "hourly+daily+last_value"
    return result, interpolated, source


def fetch_forecast(force=False):
    global last_forecast_error
    o = options()
    provider = o.get("weather_provider", "openweathermap")
    entity = selected_weather_entity(o)
    target_hours = max(24, min(240, int(o.get("target_hours", DEFAULT_TARGET_HOURS))))
    cache = load_cache()

    if not force and cache_is_fresh(cache) and cache.get("provider") == provider and cache.get("entity") == entity:
        debug("Using fresh forecast cache age=%.1f minutes", cache_age_minutes(cache) or 0)
        return cache.get("forecast", []), {"source": "cache", "interpolated_count": cache.get("interpolated_count", 0), "cache_age_minutes": cache_age_minutes(cache)}

    try:
        log.info("Fetching forecast: provider=%s entity=%s target_hours=%d", provider, entity, target_hours)
        hourly = get_service_forecast(entity, "hourly")
        daily = []
        if len(hourly) < target_hours:
            try:
                daily = get_service_forecast(entity, "daily")
            except Exception as exc:
                log.warning("Daily fallback request failed: %s", exc)

        forecast, interpolated, source = normalize_hourly_forecast(hourly, daily, target_hours)
        if not forecast:
            raise RuntimeError("Home Assistant returned no usable forecast data")

        log.info("Forecast ready: %d entries, source=%s, interpolated/fallback=%d", len(forecast), source, interpolated)
        if len(forecast) < target_hours:
            log.warning("Only %d/%d forecast entries could be produced", len(forecast), target_hours)
        last_forecast_error = None
        cache_payload = save_cache(provider, entity, forecast, source, interpolated)
        return forecast, {"source": source, "interpolated_count": interpolated, "cache_age_minutes": 0, "fetched_at": cache_payload["fetched_at"]}
    except Exception as exc:
        last_forecast_error = str(exc)
        log.exception("Forecast fetch failed")
        if o.get("fallback_to_cache", True) and cache and cache.get("forecast"):
            age = cache_age_minutes(cache)
            log.warning("Using cached forecast after fetch failure; cache age=%s minutes", age)
            return cache["forecast"], {"source": "stale_cache", "interpolated_count": cache.get("interpolated_count", 0), "cache_age_minutes": age, "error": str(exc)}
        raise


def get_location_config():
    try:
        return ha_get("/config")
    except Exception as exc:
        debug("Could not read HA config: %s", exc)
        return {}


def station_name():
    try:
        entity = selected_weather_entity()
        return state(entity).get("attributes", {}).get("friendly_name", "Home Assistant")
    except Exception:
        return "Home Assistant"


def loxone_pictocode(condition):
    # Meteoblue/Loxone picto-code mapping documented for the Gen-1 weather service.
    mapping = {
        "sunny": 1,
        "clear-night": 1,
        "partlycloudy": 7,
        "cloudy": 22,
        "fog": 16,
        "rainy": 23,
        "pouring": 25,
        "snowy": 24,
        "snowy-rainy": 35,
        "lightning": 27,
        "lightning-rainy": 28,
        "hail": 32,
        "windy": 19,
        "windy-variant": 20,
        "exceptional": 22,
    }
    code = mapping.get(condition, 22)
    if code < 1 or code > 35:
        return 22
    return code


def wind_speed_kmh(value):
    return safe_float(value)


def forecast_response(query):
    o = options()
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

    forecast, meta = fetch_forecast(force=False)
    if not forecast:
        raise RuntimeError("No forecast available")

    now = datetime.now().astimezone()
    valid_until = (now + timedelta(days=365 * 5)).date()
    cfg = get_location_config()
    timezone_name = o.get("timezone") or cfg.get("time_zone") or "Europe/Berlin"
    country = o.get("country", "Germany")
    name = station_name()

    # Keep the header byte-for-byte close to Weather4Lox. The original plugin
    # terminates the metadata column lines with semicolons.
    header1 = "id;name;longitude;latitude;height (m.asl.);country;timezone;utc-timedifference;sunrise;sunset;"
    header2 = "local date;weekday;local time;temperature(C);feeledTemperature(C);windspeed(km/h);winddirection(degr);wind gust(km/h);low clouds(%);medium clouds(%);high clouds(%);precipitation(mm);probability of Precip(%);snowFraction;sea level pressure(hPa);relative humidity(%);CAPE;picto-code;radiation (W/m2);"

    rows = []
    for index, item in enumerate(forecast):
        dt = parse_dt(item.get("datetime")) or now
        local_dt = dt.astimezone()
        condition = item.get("condition", "cloudy")
        temperature = safe_float(item.get("temperature"), safe_float(w.get("temperature")))
        apparent = safe_float(item.get("apparent_temperature"), temperature)
        wind_speed = wind_speed_kmh(item.get("wind_speed"))
        wind_bearing = safe_float(item.get("wind_bearing"), safe_float(w.get("wind_direction")))
        wind_gust = wind_speed_kmh(item.get("wind_gust_speed"))
        if wind_gust == 0:
            wind_gust = safe_float(w.get("wind_gust"), wind_speed)
        cloud = safe_float(item.get("cloud_coverage"), safe_float(w.get("clouds")))
        precipitation = safe_float(item.get("precipitation"), 0)
        precipitation_probability = safe_float(item.get("precipitation_probability"), 0)
        pressure = safe_float(item.get("pressure"), safe_float(w.get("pressure")))
        humidity = safe_float(item.get("humidity"), safe_float(w.get("humidity")))
        snow_fraction = 1.0 if condition in ("snowy", "snowy-rainy") else 0.0
        picto = loxone_pictocode(condition)

        row = [
            str(index), name, longitude, latitude, asl, country, timezone_name, "",
            "", "",
            local_dt.strftime("%d.%m.%Y"), local_dt.strftime("%a"), local_dt.strftime("%H"),
            f"{temperature:.2f}", f"{apparent:.2f}", f"{wind_speed:.2f}",
            f"{wind_bearing:.0f}", f"{wind_gust:.2f}",
            f"{cloud:.0f}", f"{cloud:.0f}", f"{cloud:.0f}",
            f"{precipitation:.2f}", f"{precipitation_probability:.0f}", f"{snow_fraction:.2f}",
            f"{pressure:.1f}", f"{humidity:.0f}", "0", str(picto), "0",
        ]
        rows.append(";".join(row) + ";")

    body = (
        "<mb_metadata>\n" + header1 + "\n" + header2 + "\n</mb_metadata>\n"
        + f"<valid_until>{valid_until}</valid_until>\n"
        + "<station>\n" + "\n".join(rows) + "\n</station>\n"
    )
    log.info("Sending Weather4Lox response: %d rows, %d bytes, source=%s, fallback/interpolated=%s", len(rows), len(body.encode("utf-8")), meta.get("source"), meta.get("interpolated_count"))
    return body


def diagnostics():
    o = options()
    cache = load_cache()
    age = cache_age_minutes(cache)
    return {
        "version": "0.3.0",
        "server": {"host": HOST, "port": PORT},
        "provider": o.get("weather_provider", "openweathermap"),
        "weather_entity": selected_weather_entity(o),
        "target_hours": int(o.get("target_hours", DEFAULT_TARGET_HOURS)),
        "cache": {
            "present": bool(cache),
            "fresh": cache_is_fresh(cache),
            "age_minutes": age,
            "entries": len(cache.get("forecast", [])) if cache else 0,
            "source": cache.get("source") if cache else None,
            "interpolated_count": cache.get("interpolated_count", 0) if cache else 0,
            "fetched_at": cache.get("fetched_at") if cache else None,
        },
        "last_forecast_error": last_forecast_error,
        "requests": {"count": request_count, "last_request": last_request},
        "options": {k: v for k, v in o.items() if "token" not in k.lower() and "key" not in k.lower()},
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "Weather4LoxHA/0.3.0"

    def log_message(self, fmt, *args):
        log.info("HTTP %s - %s", self.address_string(), fmt % args)

    def do_GET(self):
        global request_count, last_request
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        request_count += 1
        last_request = {"time": datetime.now(timezone.utc).isoformat(), "path": parsed.path, "query": query, "client": self.client_address[0]}
        log.info("REQUEST %s %s query=%s", self.command, parsed.path, query)
        try:
            if parsed.path == "/health":
                body = "lox-weather-ha: OK\n"
                status, content_type = 200, "text/plain; charset=utf-8"
            elif parsed.path == "/status":
                body = json.dumps(diagnostics(), ensure_ascii=False, indent=2, default=str)
                status, content_type = 200, "application/json; charset=utf-8"
            elif parsed.path == "/raw":
                body = json.dumps(weather_snapshot(), ensure_ascii=False, indent=2, default=str)
                status, content_type = 200, "application/json; charset=utf-8"
            elif parsed.path in ("/raw/forecast", "/debug/forecast"):
                force = query.get("refresh", ["0"])[0] in ("1", "true", "yes")
                forecast, meta = fetch_forecast(force=force)
                body = json.dumps({"meta": meta, "forecast": forecast}, ensure_ascii=False, indent=2, default=str)
                status, content_type = 200, "application/json; charset=utf-8"
            elif parsed.path in ("/debug/loxone", "/forecast", "/forecast/"):
                body = forecast_response(query)
                status, content_type = 200, "text/plain; charset=utf-8"
            else:
                body = "Not found\n"
                status, content_type = 404, "text/plain; charset=utf-8"

            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)
        except Exception as exc:
            log.exception("Request failed: %s", exc)
            body = f"Internal Server Error: {exc}\n".encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)


if __name__ == "__main__":
    log.info("Weather4Lox HA 0.3.0 starting on %s:%s", HOST, PORT)
    log.info("Home Assistant API: %s", HA_API)
    log.info("Configured options: %s", json.dumps(options(), ensure_ascii=False))
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
