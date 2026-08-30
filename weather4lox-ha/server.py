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
VERSION = "0.3.3"
HA_API = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
CACHE_FILE = "/data/forecast_cache.json"
TARGET_DEFAULT = 181
COLUMNS = 29
VALID_PICTOS = set(range(1, 36))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("weather4lox-ha")
lock = threading.Lock()
cache = None
last_error = None
last_validation = {}
request_count = 0
last_request = None


def opts():
    try:
        with open("/data/options.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log.warning("Cannot read options: %s", exc)
        return {}


def debug(msg, *args):
    if opts().get("debug_logging", True):
        log.debug(msg, *args)


def ha_request(method, path, payload=None):
    if not TOKEN:
        raise RuntimeError("SUPERVISOR_TOKEN is not available")
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(HA_API + path, data=data, method=method, headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"
    })
    try:
        with urlopen(req, timeout=20) as response:
            raw = response.read().decode()
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        body = exc.read().decode(errors="replace")
        log.error("HA API HTTP %s for %s %s: %s", exc.code, method, path, body)
        raise RuntimeError(f"Home Assistant API HTTP {exc.code}: {body}") from exc


def ha_get(path):
    return ha_request("GET", path)


def ha_service(domain, service, payload):
    return ha_request("POST", f"/services/{domain}/{service}?return_response", payload)


def get_state(entity):
    return ha_get("/states/" + entity)


def number(entity):
    if not entity:
        return None
    try:
        value = get_state(entity).get("state")
        if value in (None, "", "unknown", "unavailable"):
            return None
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError, RuntimeError):
        return None


def safe_float(value, default=0.0):
    try:
        if value in (None, "", "unknown", "unavailable"):
            return default
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def clamp(value, low, high):
    return max(low, min(high, value))


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def selected_entity(o=None):
    o = o or opts()
    provider = o.get("weather_provider", "openweathermap")
    if provider == "dwd":
        return o.get("dwd_weather_entity", "weather.wertingen")
    if provider == "custom":
        return o.get("custom_weather_entity", "weather.openweathermap")
    return o.get("weather_entity", "weather.openweathermap")


def snapshot():
    o = opts()
    provider = o.get("weather_provider", "openweathermap")
    entity = selected_entity(o)
    data = get_state(entity)
    attrs = data.get("attributes", {})
    sensor_mode = provider == "openweathermap"
    return {
        "provider": provider, "entity": entity, "state": data.get("state"),
        "temperature": number(o.get("temperature_sensor")) if sensor_mode else attrs.get("temperature"),
        "feels_like": number(o.get("feels_like_sensor")) if sensor_mode else attrs.get("apparent_temperature"),
        "humidity": number(o.get("humidity_sensor")) if sensor_mode else attrs.get("humidity"),
        "pressure": number(o.get("pressure_sensor")) if sensor_mode else attrs.get("pressure"),
        "clouds": number(o.get("cloud_sensor")) if sensor_mode else attrs.get("cloud_coverage"),
        "wind_speed": number(o.get("wind_speed_sensor")) if sensor_mode else attrs.get("wind_speed"),
        "wind_gust": number(o.get("wind_gust_sensor")) if sensor_mode else attrs.get("wind_gust_speed"),
        "wind_direction": number(o.get("wind_direction_sensor")) if sensor_mode else attrs.get("wind_bearing"),
        "rain": number(o.get("rain_sensor")) if sensor_mode else None,
        "snow": number(o.get("snow_sensor")) if sensor_mode else None,
        "raw_attributes": attrs,
    }


def service_forecast(entity, kind):
    response = ha_service("weather", "get_forecasts", {"entity_id": entity, "type": kind})
    data = response.get("service_response", {}).get(entity, {})
    result = data.get("forecast", [])
    if not isinstance(result, list):
        return []
    return sorted([x for x in result if parse_dt(x.get("datetime"))], key=lambda x: x["datetime"])


def load_cache():
    global cache
    with lock:
        if cache is not None:
            return cache
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                cache = json.load(f)
        except FileNotFoundError:
            cache = None
        except Exception as exc:
            log.warning("Cannot load cache: %s", exc)
            cache = None
        return cache


def save_cache(provider, entity, forecast, source, fallback_count):
    global cache
    payload = {"fetched_at": datetime.now(timezone.utc).isoformat(), "provider": provider, "entity": entity, "source": source, "fallback_count": fallback_count, "forecast": forecast}
    tmp = CACHE_FILE + ".tmp"
    with lock:
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp, CACHE_FILE)
            cache = payload
        except Exception as exc:
            log.warning("Cannot save cache: %s", exc)
    return payload


def cache_age_minutes(c):
    if not c:
        return None
    dt = parse_dt(c.get("fetched_at"))
    if not dt:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 60)


def cache_fresh(c, provider, entity):
    if not c or c.get("provider") != provider or c.get("entity") != entity:
        return False
    age = cache_age_minutes(c)
    return age is not None and age <= max(1, int(opts().get("cache_ttl_minutes", 60)))


def daily_value(item, key, default=None):
    value = item.get(key, default)
    if isinstance(value, dict):
        vals = [value.get(k) for k in ("min", "max") if value.get(k) is not None]
        return sum(float(v) for v in vals) / len(vals) if vals else default
    return value


def interpolate(a, b, ratio):
    if a is None:
        return b
    if b is None:
        return a
    try:
        return float(a) + (float(b) - float(a)) * ratio
    except (TypeError, ValueError):
        return a


def normalize(hourly, daily, target):
    hourly_map = {parse_dt(x["datetime"]).replace(minute=0, second=0, microsecond=0): x for x in hourly}
    daily_map = {parse_dt(x["datetime"]).date(): x for x in daily}
    start = parse_dt(hourly[0]["datetime"]).replace(minute=0, second=0, microsecond=0) if hourly else datetime.now().astimezone().replace(minute=0, second=0, microsecond=0)
    keys = [start + timedelta(hours=i) for i in range(target)]
    known = sorted(hourly_map)
    result = []
    fallback_count = 0
    fields = ["temperature", "apparent_temperature", "humidity", "pressure", "wind_speed", "wind_gust_speed", "wind_bearing", "cloud_coverage", "precipitation", "precipitation_probability", "uv_index", "visibility"]
    for key in keys:
        if key in hourly_map:
            item = dict(hourly_map[key]); item["_source"] = "hourly"; result.append(item); continue
        item = None
        before = next((k for k in reversed(known) if k < key), None)
        after = next((k for k in known if k > key), None)
        if before and after and opts().get("interpolate_missing_hours", True):
            left, right = hourly_map[before], hourly_map[after]
            ratio = (key - before).total_seconds() / (after - before).total_seconds()
            item = dict(left); item["datetime"] = key.isoformat()
            for field in fields:
                if field in left or field in right:
                    item[field] = interpolate(left.get(field), right.get(field), ratio)
            item["condition"] = left.get("condition") if ratio < 0.5 else right.get("condition")
            item["_source"] = "interpolated"
        else:
            day = daily_map.get(key.date())
            if day:
                item = dict(day); item["datetime"] = key.isoformat()
                for field in fields:
                    if field in day: item[field] = daily_value(day, field)
                item["apparent_temperature"] = daily_value(day, "apparent_temperature", item.get("temperature"))
                item["_source"] = "daily_fallback"
        if item is None and result:
            item = dict(result[-1]); item["datetime"] = key.isoformat(); item["_source"] = "last_value_fallback"
        if item is not None:
            result.append(item); fallback_count += 1
    sources = {x.get("_source") for x in result}
    source = "hourly"
    if "daily_fallback" in sources: source = "hourly+daily"
    if "last_value_fallback" in sources: source = "hourly+daily+last_value"
    if "interpolated" in sources and source == "hourly": source = "hourly+interpolated"
    return result[:target], fallback_count, source


def synthetic(existing, target, snap):
    result = sorted([dict(x) for x in existing], key=lambda x: parse_dt(x.get("datetime")) or datetime.min.replace(tzinfo=timezone.utc))
    original_count = len(result)
    if result:
        last_dt = parse_dt(result[-1]["datetime"]); last = result[-1]
    else:
        last_dt = datetime.now().astimezone().replace(minute=0, second=0, microsecond=0); last = {}
    base = {
        "temperature": safe_float(last.get("temperature"), safe_float(snap.get("temperature"), 15)),
        "feels": safe_float(last.get("apparent_temperature"), safe_float(snap.get("feels_like"), 15)),
        "humidity": safe_float(last.get("humidity"), safe_float(snap.get("humidity"), 60)),
        "pressure": safe_float(last.get("pressure"), safe_float(snap.get("pressure"), 1013)),
        "wind": safe_float(last.get("wind_speed"), safe_float(snap.get("wind_speed"), 8)),
        "gust": safe_float(last.get("wind_gust_speed"), safe_float(snap.get("wind_gust"), 12)),
        "bearing": safe_float(last.get("wind_bearing"), safe_float(snap.get("wind_direction"), 180)),
        "clouds": safe_float(last.get("cloud_coverage"), safe_float(snap.get("clouds"), 50)),
    }
    condition = last.get("condition") or snap.get("state") or "cloudy"
    next_dt = last_dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1) if result else last_dt
    while len(result) < target:
        n = len(result) + 1
        phase = (next_dt.hour - 15) * math.pi / 12
        day_wave = math.sin(n * math.pi / 2.8)
        temp = clamp(base["temperature"] + 2.8 * math.sin(phase) + 0.8 * day_wave - 0.01 * n, -30, 45)
        humidity = clamp(base["humidity"] - 7 * math.sin(phase) - 2 * day_wave, 15, 100)
        pressure = clamp(base["pressure"] + 1.8 * math.sin(n / 10), 970, 1050)
        wind = clamp(base["wind"] + 1.8 * math.sin(n / 6), 0, 120)
        gust = clamp(max(wind, base["gust"] + 2.5 * math.sin(n / 8)), 0, 160)
        bearing = (base["bearing"] + 15 * math.sin(n / 11)) % 360
        clouds = clamp(base["clouds"] + 15 * math.sin(n / 13), 0, 100)
        result.append({
            "datetime": next_dt.isoformat(), "temperature": round(temp, 2),
            "apparent_temperature": round(base["feels"] + (temp - base["temperature"]) * 0.9, 2),
            "humidity": round(humidity, 1), "pressure": round(pressure, 1),
            "wind_speed": round(wind, 2), "wind_gust_speed": round(gust, 2),
            "wind_bearing": round(bearing, 1), "cloud_coverage": round(clouds, 1),
            "precipitation": 0.0, "precipitation_probability": 0.0,
            "uv_index": 0.0, "visibility": 10.0, "condition": condition, "_source": "synthetic",
        })
        next_dt += timedelta(hours=1)
    return result[:target], max(0, len(result[:target]) - original_count)


def obtain_forecast(force=False):
    global last_error
    o = opts(); provider = o.get("weather_provider", "openweathermap"); entity = selected_entity(o)
    target = max(1, int(o.get("target_hours", TARGET_DEFAULT)))
    c = load_cache()
    if c and cache_fresh(c, provider, entity) and not force:
        log.info("Using fresh cache: provider=%s entity=%s entries=%d", provider, entity, len(c.get("forecast", [])))
        return c.get("forecast", [])[:target], "cache", int(c.get("fallback_count", 0))

    hourly, daily, error = [], [], None
    try:
        log.info("Requesting hourly forecast: provider=%s entity=%s", provider, entity)
        hourly = service_forecast(entity, "hourly")
        log.info("Home Assistant returned %d hourly entries", len(hourly))
    except Exception as exc:
        error = str(exc); last_error = error
        log.warning("Hourly forecast failed: %s", exc)

    # OpenWeatherMap is intentionally different: if it cannot provide the full
    # 181-hour forecast, do not turn seven daily values into 181 repeated hours.
    # We keep the real hourly part (if any) and synthetically continue it.
    if provider != "openweathermap" and len(hourly) < target:
        try:
            daily = service_forecast(entity, "daily")
            log.info("Home Assistant returned %d daily entries", len(daily))
        except Exception as exc:
            log.warning("Daily forecast failed: %s", exc)

    if provider == "openweathermap" and len(hourly) < target:
        result = list(hourly)
        fallback_count = 0
        source = "hourly"
        if o.get("synthetic_fallback", True):
            result, synthetic_count = synthetic(result, target, snapshot())
            fallback_count += synthetic_count
            source = "hourly+synthetic" if hourly else "synthetic"
            log.warning("OpenWeatherMap forecast shorter than %d: generated %d synthetic entries", target, synthetic_count)
    else:
        result, fallback_count, source = normalize(hourly, daily, target)
        if len(result) < target and o.get("synthetic_fallback", True):
            result, synthetic_count = synthetic(result, target, snapshot())
            fallback_count += synthetic_count
            source = (source + "+synthetic") if source != "none" else "synthetic"
            log.warning("Synthetic fallback: generated %d entries", synthetic_count)

    if len(result) < target and o.get("fallback_to_cache", True) and c and c.get("provider") == provider and c.get("entity") == entity:
        cached = c.get("forecast", [])[:target]
        if len(cached) >= target:
            result, source, fallback_count = cached, "cache", int(c.get("fallback_count", 0))

    if not result:
        raise RuntimeError(error or "No forecast data available")
    save_cache(provider, entity, result, source, fallback_count)
    last_error = error
    log.info("Forecast ready: %d/%d entries source=%s fallback=%d", len(result), target, source, fallback_count)
    return result[:target], source, fallback_count


def condition_picto(condition):
    return {"sunny": 1, "clear-night": 1, "partlycloudy": 7, "cloudy": 22, "fog": 16, "rainy": 23, "pouring": 25, "snowy": 24, "snowy-rainy": 35, "lightning": 27, "lightning-rainy": 28, "hail": 32, "windy": 19, "windy-variant": 20, "exceptional": 22}.get(str(condition or "").lower(), 22)


def picto(item):
    try:
        value = int(item.get("picto-code"))
        if value in VALID_PICTOS:
            return value
    except (TypeError, ValueError):
        pass
    return condition_picto(item.get("condition"))


def coord(value):
    try:
        a, b = str(value).split(",", 1); return float(a), float(b)
    except (ValueError, TypeError):
        return 10.681, 48.56


def fmt(value, digits=2, default="0"):
    if value is None: return default
    try:
        value = float(value)
        if not math.isfinite(value): return default
        return str(int(round(value))) if digits == 0 else f"{value:.{digits}f}"
    except (TypeError, ValueError): return default


def local_dt(value):
    dt = parse_dt(value)
    return datetime.now().astimezone() if dt is None else dt.astimezone()


def metadata():
    return "id;name;longitude;latitude;height (m.asl.);country;timezone;utc-timedifference;sunrise;sunset;local date;weekday;local time;temperature(C);feeledTemperature(C);windspeed (km/h);winddirection(degr);wind gust(km/h);low clouds(%);medium clouds(%);high clouds(%);precipitation(mm);probability of Precip(%);snowFraction;sea level pressure(hPa);relative humidity(%);CAPE;picto-code;radiation (W/m2)"


def make_loxone(query):
    global last_validation
    o = opts(); provider = o.get("weather_provider", "openweathermap"); entity = selected_entity(o)
    target = max(1, int(o.get("target_hours", TARGET_DEFAULT)))
    user = query.get("user", ["loxone"])[0]; coord_text = query.get("coord", ["10.681,48.56"])[0]
    asl = query.get("asl", ["450"])[0]; fmt_arg = query.get("format", ["2"])[0]; new_api = query.get("new_api", ["0"])[0]
    lon, lat = coord(coord_text)
    log.info("Loxone request: user=%s coord=%s asl=%s format=%s new_api=%s provider=%s entity=%s", user, coord_text, asl, fmt_arg, new_api, provider, entity)
    snap = snapshot(); forecast, source, fallback_count = obtain_forecast()
    rows = []
    for index, item in enumerate(forecast[:target]):
        dt = local_dt(item.get("datetime"))
        clouds = clamp(safe_float(item.get("cloud_coverage"), safe_float(snap.get("clouds"))), 0, 100)
        precipitation = max(0, safe_float(item.get("precipitation"), 0)); probability = clamp(safe_float(item.get("precipitation_probability"), 0), 0, 100)
        snow = max(0, safe_float(item.get("snow"), 0)); snow_fraction = snow / precipitation if precipitation > 0 else 0
        row = [
            str(index), "Home Assistant", fmt(lon, 3), fmt(lat, 3), str(asl), o.get("country", "Germany"), o.get("timezone", "Europe/Berlin"), "0", "", "",
            dt.strftime("%Y-%m-%d"), dt.strftime("%a"), dt.strftime("%H:%M"), fmt(item.get("temperature", snap.get("temperature")), 2), fmt(item.get("apparent_temperature", snap.get("feels_like")), 2),
            fmt(item.get("wind_speed", snap.get("wind_speed")), 2), fmt(item.get("wind_bearing", snap.get("wind_direction")), 0), fmt(item.get("wind_gust_speed", snap.get("wind_gust")), 2),
            fmt(clouds, 0), "0", "0", fmt(precipitation, 2), fmt(probability, 0), fmt(snow_fraction, 2), fmt(item.get("pressure", snap.get("pressure")), 1), fmt(item.get("humidity", snap.get("humidity")), 0),
            fmt(item.get("cape"), 0), str(picto(item)), fmt(item.get("radiation"), 0),
        ]
        if len(row) != COLUMNS: raise RuntimeError(f"Row {index} has {len(row)} columns, expected {COLUMNS}")
        rows.append(";".join(row))
    head = metadata(); counts = [len(row.split(";")) for row in rows]; invalid = []
    for i, row in enumerate(rows):
        try:
            p = int(row.split(";")[27])
            if p not in VALID_PICTOS: invalid.append({"row": i, "picto": p})
        except (ValueError, IndexError): invalid.append({"row": i, "picto": None})
    last_validation = {"header_columns": len(head.split(";")), "expected_columns": COLUMNS, "rows": len(rows), "expected_rows": target, "row_columns_min": min(counts) if counts else 0, "row_columns_max": max(counts) if counts else 0, "invalid_pictos": invalid, "source": source, "fallback_count": fallback_count, "provider": provider, "entity": entity, "format": fmt_arg, "new_api": new_api}
    log.info("Loxone validation: rows=%d/%d columns=%d/%d row_columns=%d-%d invalid_pictos=%d source=%s fallback=%d", len(rows), target, len(head.split(";")), COLUMNS, min(counts) if counts else 0, max(counts) if counts else 0, len(invalid), source, fallback_count)
    if len(rows) != target or len(head.split(";")) != COLUMNS or any(c != COLUMNS for c in counts) or invalid:
        raise RuntimeError("Loxone response validation failed: " + json.dumps(last_validation, ensure_ascii=False))
    valid_until = local_dt(forecast[-1].get("datetime")).strftime("%Y-%m-%d")
    return "<mb_metadata>\n" + head + "\n</mb_metadata>\n\n<valid_until>" + valid_until + "</valid_until>\n\n<station>\n" + "\n".join(rows) + "\n</station>\n"


def forecast_json(force=False):
    forecast, source, fallback_count = obtain_forecast(force)
    return {"version": VERSION, "provider": opts().get("weather_provider"), "entity": selected_entity(), "source": source, "fallback_count": fallback_count, "count": len(forecast), "target_hours": int(opts().get("target_hours", TARGET_DEFAULT)), "forecast": forecast, "last_error": last_error}


class Handler(BaseHTTPRequestHandler):
    server_version = f"Weather4LoxHA/{VERSION}"
    def log_message(self, fmt_text, *args): debug("HTTP %s - " + fmt_text, self.address_string(), *args)
    def reply(self, body, status=200, content_type="text/plain; charset=utf-8"):
        data = body.encode("utf-8"); self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)
    def json(self, obj, status=200): self.reply(json.dumps(obj, ensure_ascii=False, indent=2, default=str), status, "application/json; charset=utf-8")
    def do_GET(self):
        global request_count, last_request
        request_count += 1; parsed = urlparse(self.path); query = parse_qs(parsed.query); last_request = {"path": parsed.path, "query": query, "time": datetime.now(timezone.utc).isoformat()}
        try:
            if parsed.path == "/health": self.reply(f"lox-weather-ha-test: OK (v{VERSION})\n")
            elif parsed.path == "/status":
                c = load_cache(); self.json({"version": VERSION, "provider": opts().get("weather_provider"), "entity": selected_entity(), "cache_age_minutes": cache_age_minutes(c), "cache_entries": len(c.get("forecast", [])) if c else 0, "last_error": last_error, "request_count": request_count, "last_request": last_request, "last_validation": last_validation})
            elif parsed.path == "/raw":
                s = snapshot(); self.json({k: s.get(k) for k in ("entity", "state", "temperature", "feels_like", "humidity", "pressure", "clouds", "wind_speed", "wind_gust", "wind_direction", "rain", "snow", "raw_attributes")})
            elif parsed.path == "/debug/forecast": self.json(forecast_json(query.get("refresh", ["0"])[0] == "1"))
            elif parsed.path.rstrip("/") in ("/debug/loxone", "/forecast"): self.reply(make_loxone(query), content_type="application/xml; charset=utf-8")
            else: self.reply("Not found\n", 404)
        except Exception as exc:
            log.exception("Request failed for %s", self.path); self.reply(f"Internal Server Error: {exc}\n", 500)


def main():
    log.info("Weather4Lox HA %s starting on %s:%d", VERSION, HOST, PORT)
    o = opts(); log.info("Config: provider=%s weather_entity=%s dwd_entity=%s target_hours=%s synthetic_fallback=%s debug_logging=%s", o.get("weather_provider"), o.get("weather_entity"), o.get("dwd_weather_entity"), o.get("target_hours", TARGET_DEFAULT), o.get("synthetic_fallback", True), o.get("debug_logging", True))
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__": main()
