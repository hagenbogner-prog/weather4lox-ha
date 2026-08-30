#!/usr/bin/env python3
import json
import logging
import math
import os
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from urllib.request import HTTPError, Request, urlopen

HOST = "0.0.0.0"
PORT = 6066
VERSION = "0.3.2"
HA_API = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
CACHE_FILE = "/data/forecast_cache.json"
DEFAULT_TARGET_HOURS = 181
LOXONE_COLUMNS = 29

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
    req = Request(HA_API + path, data=data, method=method, headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
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


def safe_float(value, default=0.0):
    try:
        if value in (None, "unknown", "unavailable", ""):
            return default
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def clamp(value, low, high):
    return max(low, min(high, value))


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


def save_cache(provider, entity, forecast, source, fallback_count=0):
    global forecast_cache
    payload = {"fetched_at": datetime.now(timezone.utc).isoformat(), "provider": provider, "entity": entity, "source": source, "fallback_count": fallback_count, "forecast": forecast}
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


def _daily_scalar(item, key, default=None):
    value = item.get(key, default)
    if isinstance(value, dict):
        vals = [value.get(k) for k in ("min", "max") if value.get(k) is not None]
        if vals:
            return sum(float(v) for v in vals) / len(vals)
        return default
    return value


def normalize_hourly_forecast(hourly, daily, target_hours):
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
    fallback_count = 0
    numeric_fields = ["temperature", "apparent_temperature", "humidity", "pressure", "wind_speed", "wind_gust_speed", "wind_bearing", "cloud_coverage", "precipitation", "precipitation_probability", "uv_index", "visibility"]

    def daily_fallback(key):
        d = daily_map.get(key.date())
        if not d:
            return None
        item = dict(d)
        item["datetime"] = key.isoformat()
        item["temperature"] = _daily_scalar(d, "temperature")
        item["apparent_temperature"] = _daily_scalar(d, "apparent_temperature", item.get("temperature"))
        item["wind_speed"] = _daily_scalar(d, "wind_speed")
        item["wind_gust_speed"] = _daily_scalar(d, "wind_gust_speed")
        item["pressure"] = _daily_scalar(d, "pressure")
        item["humidity"] = _daily_scalar(d, "humidity")
        item["cloud_coverage"] = _daily_scalar(d, "cloud_coverage")
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
            left, right = hourly_map[before], hourly_map[after]
            span = (after - before).total_seconds()
            ratio = (key - before).total_seconds() / span if span else 0
            item = dict(left)
            item["datetime"] = key.isoformat()
            for field in numeric_fields:
                if field in left or field in right:
                    item[field] = interpolate_numeric(left.get(field), right.get(field), ratio)
            item["condition"] = left.get("condition") if ratio < 0.5 else right.get("condition")
            item["_source"] = "interpolated"
            fallback_count += 1
        else:
            item = daily_fallback(key)
            if item:
                fallback_count += 1
        if item is None and result:
            item = dict(result[-1])
            item["datetime"] = key.isoformat()
            item["_source"] = "last_value_fallback"
            fallback_count += 1
        if item:
            result.append(item)
    source = "hourly"
    if any(x.get("_source") == "daily_fallback" for x in result):
        source = "hourly+daily"
    if any(x.get("_source") == "last_value_fallback" for x in result):
        source = "hourly+daily+last_value"
    return result, fallback_count, source


def generate_synthetic_forecast(existing, target_hours, snapshot):
    """Fill missing forecast hours with a smooth, deterministic continuation of current data."""
    existing = sorted(existing, key=lambda x: parse_dt(x.get("datetime")) or datetime.min.replace(tzinfo=timezone.utc))
    if existing:
        last_dt = parse_dt(existing[-1].get("datetime"))
        last = dict(existing[-1])
    else:
        last_dt = datetime.now().astimezone().replace(minute=0, second=0, microsecond=0)
        last = {}
    if last_dt is None:
        last_dt = datetime.now().astimezone().replace(minute=0, second=0, microsecond=0)
    base_temp = safe_float(last.get("temperature"), safe_float(snapshot.get("temperature"), 15.0))
    base_feels = safe_float(last.get("apparent_temperature"), safe_float(snapshot.get("feels_like"), base_temp))
    base_humidity = safe_float(last.get("humidity"), safe_float(snapshot.get("humidity"), 60.0))
    base_pressure = safe_float(last.get("pressure"), safe_float(snapshot.get("pressure"), 1013.0))
    base_wind = safe_float(last.get("wind_speed"), safe_float(snapshot.get("wind_speed"), 8.0))
    base_gust = safe_float(last.get("wind_gust_speed"), safe_float(snapshot.get("wind_gust"), base_wind * 1.5))
    base_bearing = safe_float(last.get("wind_bearing"), safe_float(snapshot.get("wind_direction"), 180.0))
    base_cloud = safe_float(last.get("cloud_coverage"), safe_float(snapshot.get("clouds"), 50.0))
    base_condition = last.get("condition") or snapshot.get("state") or "cloudy"
    result = list(existing)
    existing_keys = {parse_dt(x.get("datetime")).replace(minute=0, second=0, microsecond=0) for x in existing if parse_dt(x.get("datetime"))}
    start = (last_dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)) if existing else last_dt.replace(minute=0, second=0, microsecond=0)
    for i in range(target_hours - len(result) + 1):
        key = start + timedelta(hours=i)
        if key in existing_keys:
            continue
        hours_from_start = i + 1
        daily_phase = (key.hour - 15) * math.pi / 12.0
        temp = clamp(base_temp + 2.5 * math.sin(daily_phase) - 0.015 * hours_from_start, -30.0, 45.0)
        feels = base_feels + (temp - base_temp) * 0.9
        humidity = clamp(base_humidity - 5.0 * math.sin(daily_phase), 20.0, 100.0)
        pressure = clamp(base_pressure + 1.5 * math.sin(hours_from_start / 8.0), 970.0, 1050.0)
        wind = clamp(base_wind + 1.8 * math.sin(hours_from_start / 5.0), 0.0, 120.0)
        gust = clamp(max(wind, base_gust + 2.0 * math.sin(hours_from_start / 7.0)), 0.0, 160.0)
        bearing = (base_bearing + 12.0 * math.sin(hours_from_start / 9.0)) % 360.0
        cloud = clamp(base_cloud + 12.0 * math.sin(hours_from_start / 10.0), 0.0, 100.0)
        result.append({"datetime": key.isoformat(), "temperature": round(temp, 2), "apparent_temperature": round(feels, 2), "humidity": round(humidity, 1), "pressure": round(pressure, 1), "wind_speed": round(wind, 2), "wind_gust_speed": round(gust, 2), "wind_bearing": round(bearing, 0), "cloud_coverage": round(cloud, 0), "precipitation": 0.0, "precipitation_probability": 0.0, "condition": base_condition, "_source": "synthetic"})
        if len(result) >= target_hours:
            break
    return sorted(result[:target_hours], key=lambda x: parse_dt(x.get("datetime")) or datetime.min.replace(tzinfo=timezone.utc))


def fetch_forecast(force=False):
    global last_forecast_error
    o = options()
    provider = o.get("weather_provider", "openweathermap")
    entity = selected_weather_entity(o)
    target_hours = max(24, min(240, int(o.get("target_hours", DEFAULT_TARGET_HOURS))))
    cache = load_cache()
    if not force and cache_is_fresh(cache) and cache.get("provider") == provider and cache.get("entity") == entity:
        debug("Using fresh forecast cache age=%.1f minutes", cache_age_minutes(cache) or 0)
        return cache.get("forecast", []), {"source": "cache", "fallback_count": cache.get("fallback_count", 0), "cache_age_minutes": cache_age_minutes(cache)}
    hourly, daily, errors = [], [], []
    try:
        log.info("Fetching hourly forecast: provider=%s entity=%s target_hours=%d", provider, entity, target_hours)
        hourly = get_service_forecast(entity, "hourly")
        log.info("Home Assistant returned %d hourly forecast entries", len(hourly))
    except Exception as exc:
        errors.append(str(exc))
        log.warning("Hourly forecast request failed: %s", exc)
    if len(hourly) < target_hours:
        try:
            daily = get_service_forecast(entity, "daily")
            log.info("Home Assistant returned %d daily forecast entries", len(daily))
        except Exception as exc:
            errors.append(str(exc))
            log.warning("Daily forecast request failed: %s", exc)
    try:
        forecast, fallback_count, source = normalize_hourly_forecast(hourly, daily, target_hours)
    except Exception as exc:
        errors.append(str(exc))
        forecast, fallback_count, source = [], 0, "none"
    if len(forecast) < target_hours and o.get("synthetic_fallback", True):
        try:
            snapshot = weather_snapshot()
        except Exception as exc:
            errors.append(str(exc))
            snapshot = {}
        before = len(forecast)
        forecast = generate_synthetic_forecast(forecast, target_hours, snapshot)
        synthetic_count = max(0, len(forecast) - before)
        fallback_count += synthetic_count
        if synthetic_count:
            source = source + "+synthetic" if source != "none" else "synthetic"
            log.warning("Generated %d synthetic forecast entries", synthetic_count)
    if not forecast:
        last_forecast_error = "; ".join(errors) or "No forecast data available"
        if o.get("fallback_to_cache", True) and cache and cache.get("forecast"):
            age = cache_age_minutes(cache)
            log.warning("Using stale cached forecast after fetch failure; cache age=%s minutes", age)
            return cache["forecast"], {"source": "stale_cache", "fallback_count": cache.get("fallback_count", 0), "cache_age_minutes": age, "error": last_forecast_error}
        raise RuntimeError(last_forecast_error)
    if len(forecast) < target_hours:
        errors.append(f"Only {len(forecast)}/{target_hours} entries available")
    last_forecast_error = "; ".join(errors) if errors else None
    log.info("Forecast ready: %d entries, source=%s, fallback/synthetic=%d", len(forecast), source, fallback_count)
    cache_payload = save_cache(provider, entity, forecast, source, fallback_count)
    return forecast, {"source": source, "fallback_count": fallback_count, "cache_age_minutes": 0, "fetched_at": cache_payload["fetched_at"], "errors": errors}


def get_location_config():
    try:
        return ha_get("/config")
    except Exception as exc:
        debug("Could not read HA config: %s", exc)
        return {}


def station_name():
    try:
        return state(selected_weather_entity()).get("attributes", {}).get("friendly_name", "Home Assistant")
    except Exception:
        return "Home Assistant"


def loxone_pictocode(condition):
    mapping = {"sunny": 1, "clear-night": 1, "partlycloudy": 7, "cloudy": 22, "fog": 16, "rainy": 23, "pouring": 25, "snowy": 24, "snowy-rainy": 35, "lightning": 27, "lightning-rainy": 28, "hail": 32, "windy": 19, "windy-variant": 20, "exceptional": 22}
    return mapping.get(str(condition).lower(), 22)


def validate_loxone_rows(rows):
    errors = []
    if len(rows) != 181:
        errors.append(f"expected 181 rows, got {len(rows)}")
    column_counts = []
    bad_indices = []
    for idx, row in enumerate(rows):
        count = len(row.rstrip(";").split(";"))
        column_counts.append(count)
        if count != LOXONE_COLUMNS:
            bad_indices.append((idx, count))
    if bad_indices:
        errors.append(f"bad column counts: {bad_indices[:5]}")
    return {"valid": not errors, "rows": len(rows), "min_columns": min(column_counts) if column_counts else 0, "max_columns": max(column_counts) if column_counts else 0, "errors": errors}


def loxone_response(query):
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
    header1 = "id;name;longitude;latitude;height (m.asl.);country;timezone;utc-timedifference;sunrise;sunset;"
    header2 = "local date;weekday;local time;temperature(C);feeledTemperature(C);windspeed(km/h);winddirection(degr);wind gust(km/h);low clouds(%);medium clouds(%);high clouds(%);precipitation(mm);probability of Precip(%);snowFraction;sea level pressure(hPa);relative humidity(%);CAPE;picto-code;radiation (W/m2);"
    rows = []
    invalid_pictos = []
    for index, item in enumerate(forecast[:181]):
        dt = parse_dt(item.get("datetime")) or now
        local_dt = dt.astimezone()
        condition = item.get("condition", "cloudy")
        temperature = safe_float(item.get("temperature"), safe_float(w.get("temperature")))
        apparent = safe_float(item.get("apparent_temperature"), temperature)
        wind_speed = safe_float(item.get("wind_speed"), safe_float(w.get("wind_speed")))
        wind_bearing = safe_float(item.get("wind_bearing"), safe_float(w.get("wind_direction")))
        wind_gust = safe_float(item.get("wind_gust_speed"), safe_float(w.get("wind_gust"), wind_speed))
        cloud = clamp(safe_float(item.get("cloud_coverage"), safe_float(w.get("clouds"))), 0, 100)
        precipitation = max(0, safe_float(item.get("precipitation"), 0))
        precipitation_probability = clamp(safe_float(item.get("precipitation_probability"), 0), 0, 100)
        pressure = safe_float(item.get("pressure"), safe_float(w.get("pressure")))
        humidity = clamp(safe_float(item.get("humidity"), safe_float(w.get("humidity"))), 0, 100)
        snow_fraction = 1.0 if str(condition).lower() in ("snowy", "snowy-rainy") else 0.0
        picto = loxone_pictocode(condition)
        if not 1 <= picto <= 35:
            invalid_pictos.append((index, picto))
            picto = 22
        row = [str(index), name, longitude, latitude, asl, country, timezone_name, "", "", "", local_dt.strftime("%d.%m.%Y"), local_dt.strftime("%a"), local_dt.strftime("%H:%M"), f"{temperature:.2f}", f"{apparent:.2f}", f"{wind_speed:.2f}", f"{wind_bearing:.0f}", f"{wind_gust:.2f}", f"{cloud:.0f}", f"{cloud:.0f}", f"{cloud:.0f}", f"{precipitation:.2f}", f"{precipitation_probability:.0f}", f"{snow_fraction:.2f}", f"{pressure:.1f}", f"{humidity:.0f}", "0", str(picto), "0"]
        rows.append(";".join(row) + ";")
    validation = validate_loxone_rows(rows)
    log.info("Loxone validation: rows=%d/%d columns=%d-%d/%d invalid_pictos=%d", validation["rows"], 181, validation["min_columns"], validation["max_columns"], LOXONE_COLUMNS, len(invalid_pictos))
    if not validation["valid"]:
        raise RuntimeError("Loxone response validation failed: " + "; ".join(validation["errors"]))
    body = "<mb_metadata>\n" + header1 + "\n" + header2 + "\n</mb_metadata>\n" + f"<valid_until>{valid_until}</valid_until>\n" + "<station>\n" + "\n".join(rows) + "\n</station>\n"
    log.info("Sending Weather4Lox response: %d rows, %d bytes, source=%s, fallback/synthetic=%s", len(rows), len(body.encode("utf-8")), meta.get("source"), meta.get("fallback_count"))
    return body


def diagnostics():
    o = options()
    cache = load_cache()
    age = cache_age_minutes(cache)
    return {"version": VERSION, "server": {"host": HOST, "port": PORT}, "provider": o.get("weather_provider", "openweathermap"), "weather_entity": selected_weather_entity(o), "target_hours": int(o.get("target_hours", DEFAULT_TARGET_HOURS)), "loxone_required_rows": 181, "loxone_columns": LOXONE_COLUMNS, "cache": {"present": bool(cache), "fresh": cache_is_fresh(cache), "age_minutes": age, "entries": len(cache.get("forecast", [])) if cache else 0, "source": cache.get("source") if cache else None, "fallback_count": cache.get("fallback_count", 0) if cache else 0, "fetched_at": cache.get("fetched_at") if cache else None}, "last_forecast_error": last_forecast_error, "requests": {"count": request_count, "last_request": last_request}, "options": {k: v for k, v in o.items() if "token" not in k.lower() and "key" not in k.lower()}}


class Handler(BaseHTTPRequestHandler):
    server_version = f"Weather4LoxHA/{VERSION}"

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
                body, status, content_type = "lox-weather-ha: OK\n", 200, "text/plain; charset=utf-8"
            elif parsed.path == "/status":
                body, status, content_type = json.dumps(diagnostics(), ensure_ascii=False, indent=2, default=str), 200, "application/json; charset=utf-8"
            elif parsed.path == "/raw":
                body, status, content_type = json.dumps(weather_snapshot(), ensure_ascii=False, indent=2, default=str), 200, "application/json; charset=utf-8"
            elif parsed.path in ("/raw/forecast", "/debug/forecast"):
                force = query.get("refresh", ["0"])[0].lower() in ("1", "true", "yes")
                forecast, meta = fetch_forecast(force=force)
                body, status, content_type = json.dumps({"meta": meta, "forecast": forecast}, ensure_ascii=False, indent=2, default=str), 200, "application/json; charset=utf-8"
            elif parsed.path in ("/debug/loxone", "/debug/loxone/", "/forecast", "/forecast/"):
                body, status, content_type = loxone_response(query), 200, "text/plain; charset=utf-8"
            else:
                body, status, content_type = "Not found\n", 404, "text/plain; charset=utf-8"
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
    log.info("Weather4Lox HA %s starting on %s:%s", VERSION, HOST, PORT)
    log.info("Home Assistant API: %s", HA_API)
    log.info("Configured options: %s", json.dumps(options(), ensure_ascii=False))
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
