#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import math
import os
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from protocol.loxone_gen1 import (
    DEFAULT_LOXONE_PICTO,
    FORMAT2_HEADER,
    VALID_LOXONE_PICTOS,
    picto_for_condition,
)
from providers import PROFILES, cache_ttl_minutes, forecast_days, refresh_minutes

HOST = "0.0.0.0"
PORT = 6066
VERSION = "0.5.0"
HA_API = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
CACHE_FILE = "/data/forecast_cache.json"
DIAGNOSTIC_PICTO = DEFAULT_LOXONE_PICTO
VALID_PICTOS = VALID_LOXONE_PICTOS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("weather4lox-ha")
lock = threading.RLock()
cache = None
last_error = None
last_attempt = None
last_success = None
last_validation = {}
last_request = None
request_count = 0


def opts():
    try:
        with open("/data/options.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log.warning("Cannot read options: %s", exc)
        return {}


def debug(message, *args):
    if opts().get("debug_logging", True):
        log.debug(message, *args)


def parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def local_dt(value):
    dt = parse_dt(value)
    if dt is None:
        return datetime.now().astimezone()
    return dt.astimezone()


def safe_float(value, default=None):
    try:
        if value in (None, "", "unknown", "unavailable"):
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def clamp(value, low, high):
    return max(low, min(high, value))


def fmt(value, digits=2, default="0"):
    number = safe_float(value)
    if number is None:
        return default
    return str(int(round(number))) if digits == 0 else f"{number:.{digits}f}"


def ha_request(method, path, payload=None):
    if not TOKEN:
        raise RuntimeError("SUPERVISOR_TOKEN is not available")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(
        HA_API + path,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        body = exc.read().decode(errors="replace")
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
        return safe_float(get_state(entity).get("state"))
    except Exception:
        return None


def provider_config(provider, options=None):
    options = options or opts()
    section = options.get(provider) or {}
    if not isinstance(section, dict):
        section = {}
    return section


def provider_entity(provider, options=None):
    section = provider_config(provider, options)
    entity = str(section.get("weather_entity", "auto")).strip()
    if entity and entity != "auto":
        return entity
    return auto_detect_entity(provider, options)


def auto_detect_entity(provider, options=None):
    """Select a weather.* entity using attribution/name hints; manual config wins."""
    options = options or opts()
    states = ha_get("/states")
    if not isinstance(states, list):
        return None
    candidates = []
    needles = {
        "dwd": ("dwd", "deutscher wetterdienst"),
        "openweathermap": ("openweathermap", "open weather map"),
    }[provider]
    for item in states:
        entity_id = str(item.get("entity_id", ""))
        if not entity_id.startswith("weather."):
            continue
        attrs = item.get("attributes") or {}
        text = " ".join(str(attrs.get(k, "")) for k in ("attribution", "friendly_name", "integration", "source"))
        text = f"{entity_id} {text}".lower()
        score = sum(2 for needle in needles if needle in text)
        if score:
            candidates.append((score, entity_id))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: (-pair[0], pair[1]))
    return candidates[0][1]


def selected_entity(provider=None):
    provider = provider or opts().get("weather_provider", "openweathermap")
    entity = provider_entity(provider)
    if not entity:
        raise RuntimeError(f"No Home Assistant weather entity found for provider {provider}")
    return entity


def snapshot(entity=None):
    provider = opts().get("weather_provider", "openweathermap")
    entity = entity or selected_entity(provider)
    data = get_state(entity)
    attrs = data.get("attributes") or {}
    return {
        "provider": provider,
        "entity": entity,
        "state": data.get("state"),
        "temperature": attrs.get("temperature"),
        "feels_like": attrs.get("apparent_temperature"),
        "humidity": attrs.get("humidity"),
        "pressure": attrs.get("pressure"),
        "clouds": attrs.get("cloud_coverage"),
        "wind_speed": attrs.get("wind_speed"),
        "wind_gust": attrs.get("wind_gust_speed"),
        "wind_direction": attrs.get("wind_bearing"),
        "rain": attrs.get("precipitation"),
        "snow": attrs.get("snowfall"),
        "raw_attributes": attrs,
    }


def service_forecast(entity, kind):
    response = ha_service("weather", "get_forecasts", {"entity_id": entity, "type": kind})
    service_response = response.get("service_response") or response.get("response") or {}
    data = service_response.get(entity, {}) if isinstance(service_response, dict) else {}
    result = data.get("forecast", []) if isinstance(data, dict) else []
    if not isinstance(result, list):
        return []
    return sorted(
        [dict(item) for item in result if isinstance(item, dict) and parse_dt(item.get("datetime"))],
        key=lambda item: parse_dt(item["datetime"]),
    )


def load_cache():
    global cache
    with lock:
        if cache is not None:
            return cache
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = None
        return cache


def cache_age_minutes(item=None):
    item = item if item is not None else load_cache()
    if not item:
        return None
    dt = parse_dt(item.get("created_at"))
    if not dt:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 60)


def cache_matches(item, provider, entity):
    return bool(item and item.get("provider") == provider and item.get("entity") == entity)


def cache_is_valid(item, provider, entity):
    age = cache_age_minutes(item)
    return cache_matches(item, provider, entity) and age is not None and age <= cache_ttl_minutes(provider)


def write_cache(provider, entity, forecast, source="live"):
    global cache, last_success
    now = datetime.now(timezone.utc)
    dates = [parse_dt(item.get("datetime")) for item in forecast]
    dates = [dt for dt in dates if dt]
    payload = {
        "provider": provider,
        "entity": entity,
        "created_at": now.isoformat(),
        "last_attempt": last_attempt.isoformat() if last_attempt else None,
        "last_success": now.isoformat(),
        "forecast_start": min(dates).isoformat() if dates else None,
        "forecast_end": max(dates).isoformat() if dates else None,
        "requested_days": forecast_days(provider),
        "actual_hours": len(forecast),
        "cache_validity_minutes": cache_ttl_minutes(provider),
        "source": source,
        "status": "live",
        "forecast": forecast,
    }
    tmp = CACHE_FILE + ".tmp"
    with lock:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CACHE_FILE)
        cache = payload
        last_success = now
    return payload


def fetch_live_forecast(provider, entity):
    """Fetch provider-specific forecast from HA and return only real provider data."""
    hourly = service_forecast(entity, "hourly")
    if hourly:
        return hourly
    daily = service_forecast(entity, "daily")
    return daily


def obtain_forecast(force=False):
    """Return live data when possible, otherwise an unmodified valid cache."""
    global last_error, last_attempt
    options = opts()
    provider = options.get("weather_provider", "openweathermap")
    if provider not in PROFILES:
        raise RuntimeError(f"Unsupported provider: {provider}")
    entity = selected_entity(provider)
    cached = load_cache()
    if cached and cache_is_valid(cached, provider, entity) and not force:
        return cached.get("forecast", []), "cache", cached

    last_attempt = datetime.now(timezone.utc)
    try:
        live = fetch_live_forecast(provider, entity)
        if not live:
            raise RuntimeError("Home Assistant returned no forecast entries")
        # Successful refresh is a complete rebuild; never merge old and new data.
        payload = write_cache(provider, entity, live, "live")
        last_error = None
        log.info(
            "Forecast refresh succeeded: provider=%s entity=%s entries=%d range=%s..%s",
            provider, entity, len(live), payload.get("forecast_start"), payload.get("forecast_end"),
        )
        return live, "live", payload
    except Exception as exc:
        last_error = str(exc)
        log.warning("Forecast refresh failed: %s", exc)
        if options.get("fallback_to_cache", True) and cached and cache_matches(cached, provider, entity):
            fallback = dict(cached)
            fallback["status"] = "cache"
            fallback["last_attempt"] = last_attempt.isoformat()
            return fallback.get("forecast", []), "cache", fallback
        raise


def condition_picto(condition):
    return picto_for_condition(condition)


def picto(item):
    value = safe_float(item.get("picto-code"))
    if value is not None and int(value) in VALID_PICTOS:
        return int(value)
    return condition_picto(item.get("condition"))


def coord(value):
    try:
        lon, lat = str(value).split(",", 1)
        return float(lon), float(lat)
    except (TypeError, ValueError):
        o = opts()
        return safe_float(o.get("longitude"), 10.681), safe_float(o.get("latitude"), 48.56)


def metadata():
    return FORMAT2_HEADER


def station_metadata(query):
    o = opts()
    fallback = f"{o.get('longitude', 10.681)},{o.get('latitude', 48.56)}"
    lon, lat = coord(query.get("coord", [fallback])[0])
    asl = query.get("asl", [str(o.get("elevation_m", 450))])[0]
    now = datetime.now().astimezone()
    offset = now.strftime("%z")
    utc_diff = f"UTC{offset[:3]}.{offset[3:]}" if len(offset) == 5 else "UTC+00.00"
    return ";".join([
        "",
        str(o.get("location_city", "Wertingen")),
        fmt(lon, 6),
        fmt(lat, 6),
        str(asl),
        str(o.get("country", "Deutschland")),
        now.tzname() or o.get("timezone", "Europe/Berlin"),
        utc_diff,
        "",
        "",
    ])


def build_rows(forecast, diagnostic=False):
    snap = snapshot() if not diagnostic else {
        "temperature": 20, "feels_like": 20, "humidity": 50, "pressure": 1013,
        "clouds": 0, "wind_speed": 5, "wind_direction": 180, "wind_gust": 8,
    }
    rows = []
    for item in forecast:
        dt = local_dt(item.get("datetime"))
        clouds = clamp(safe_float(item.get("cloud_coverage"), safe_float(snap.get("clouds"), 0)), 0, 100)
        precipitation = max(0.0, safe_float(item.get("precipitation"), 0.0))
        probability = clamp(safe_float(item.get("precipitation_probability"), 0.0), 0, 100)
        snow = max(0.0, safe_float(item.get("snowfall"), safe_float(item.get("snow"), 0.0)))
        snow_fraction = snow / precipitation if precipitation else 0.0
        row = [
            dt.strftime("%d.%m.%Y"),
            dt.strftime("%a"),
            dt.strftime("%H"),
            fmt(item.get("temperature", snap.get("temperature")), 1),
            fmt(item.get("apparent_temperature", snap.get("feels_like")), 1),
            fmt(item.get("wind_speed", snap.get("wind_speed")), 0),
            fmt(item.get("wind_bearing", snap.get("wind_direction")), 0),
            fmt(item.get("wind_gust_speed", snap.get("wind_gust")), 0),
            fmt(item.get("cloud_coverage"), 0),
            fmt(clouds, 0),
            "0",
            fmt(precipitation, 1),
            fmt(probability, 0),
            fmt(snow_fraction, 1),
            fmt(item.get("pressure", snap.get("pressure")), 0),
            fmt(item.get("humidity", snap.get("humidity")), 0),
            fmt(item.get("cape"), 0),
            str(DIAGNOSTIC_PICTO if diagnostic else picto(item)),
            fmt(item.get("radiation"), 0),
        ]
        if len(row) != 19:
            raise RuntimeError(f"Forecast row has {len(row)} columns, expected 19")
        rows.append(";".join(row) + ";")
    return rows


def validate_payload(header, station, rows, expected_rows, expected_picto=None):
    invalid = []
    counts = []
    for index, row in enumerate(rows):
        parts = row.rstrip(";").split(";")
        counts.append(len(parts))
        try:
            code = int(parts[17])
        except (ValueError, IndexError):
            code = None
        if code not in VALID_PICTOS or (expected_picto is not None and code != expected_picto):
            invalid.append({"row": index, "picto": code})
    result = {
        "ok": (
            len(header.split(";")) == 29
            and len(station.rstrip(";").split(";")) == 10
            and len(rows) == expected_rows
            and all(count == 19 for count in counts)
            and not invalid
        ),
        "header_columns": len(header.split(";")),
        "station_columns": len(station.rstrip(";").split(";")),
        "row_columns_min": min(counts) if counts else 0,
        "row_columns_max": max(counts) if counts else 0,
        "rows": len(rows),
        "expected_rows": expected_rows,
        "expected_header_columns": 29,
        "expected_station_columns": 10,
        "expected_row_columns": 19,
        "invalid_pictos": invalid,
    }
    return result


def make_payload(forecast, query, diagnostic=False):
    if not forecast:
        raise RuntimeError("No forecast data available")
    header = metadata()
    station = station_metadata(query)
    rows = build_rows(forecast, diagnostic)
    validation = validate_payload(header, station, rows, len(forecast), DIAGNOSTIC_PICTO if diagnostic else None)
    if not validation["ok"]:
        raise RuntimeError("Loxone response validation failed: " + json.dumps(validation))
    valid_until = local_dt(forecast[-1]["datetime"]).strftime("%Y-%m-%d")
    payload = (
        "<mb_metadata>\n" + header + ";\n</mb_metadata>\n"
        "<valid_until>" + valid_until + "</valid_until>\n"
        "<station>\n" + station + ";\n" + "\n".join(rows) + "\n</station>\n"
    )
    return payload, validation


def validate_real_payload(query):
    forecast, source, meta = obtain_forecast()
    payload, validation = make_payload(forecast, query)
    validation.update({
        "version": VERSION,
        "provider": meta.get("provider"),
        "entity": meta.get("entity"),
        "source": source,
        "payload_bytes": len(payload.encode("utf-8")),
    })
    return validation


class Handler(BaseHTTPRequestHandler):
    server_version = f"Weather4LoxHA/{VERSION}"

    def log_message(self, fmt_text, *args):
        debug("HTTP %s - " + fmt_text, self.address_string(), *args)

    def reply(self, body, status=200, content_type="text/plain; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def json(self, obj, status=200):
        self.reply(json.dumps(obj, ensure_ascii=False, indent=2, default=str), status, "application/json; charset=utf-8")

    def do_GET(self):
        global request_count, last_request, last_validation
        request_count += 1
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        last_request = {"path": parsed.path, "query": query, "time": datetime.now(timezone.utc).isoformat()}
        try:
            if parsed.path == "/health":
                self.reply(f"Weather4Lox HA OK (v{VERSION})\n")
            elif parsed.path == "/status":
                c = load_cache()
                provider = opts().get("weather_provider", "openweathermap")
                entity = None
                try:
                    entity = selected_entity(provider)
                except Exception:
                    pass
                age = cache_age_minutes(c)
                status = "🟢 Live" if c and cache_matches(c, provider, entity) and age is not None and age <= cache_ttl_minutes(provider) else ("🟡 Cache/Fallback" if c else "🔴 Error")
                self.json({
                    "version": VERSION,
                    "provider": provider,
                    "entity": entity,
                    "status": status,
                    "cache_age_minutes": age,
                    "cache_validity_minutes": cache_ttl_minutes(provider),
                    "cache_entries": len(c.get("forecast", [])) if c else 0,
                    "forecast_days_requested": forecast_days(provider),
                    "refresh_interval_minutes": refresh_minutes(provider),
                    "last_attempt": last_attempt,
                    "last_success": last_success,
                    "last_error": last_error,
                    "request_count": request_count,
                    "last_request": last_request,
                    "last_validation": last_validation,
                })
            elif parsed.path == "/raw":
                self.json(snapshot())
            elif parsed.path == "/debug/forecast":
                force = query.get("refresh", ["0"])[0] == "1"
                forecast, source, meta = obtain_forecast(force=force)
                self.json({"version": VERSION, "source": source, "metadata": meta, "forecast": forecast})
            elif parsed.path.rstrip("/") in ("/forecast", "/debug/loxone"):
                forecast, _, _ = obtain_forecast()
                payload, validation = make_payload(forecast, query)
                last_validation = validation
                self.reply(payload, content_type="application/xml; charset=utf-8")
            elif parsed.path.rstrip("/") == "/debug/loxone/minimal":
                now = datetime.now().astimezone().replace(minute=0, second=0, microsecond=0)
                minimal = [{"datetime": (now + timedelta(hours=i)).isoformat(), "temperature": 20, "apparent_temperature": 20, "humidity": 50, "pressure": 1013, "wind_speed": 5, "wind_gust_speed": 8, "wind_bearing": 180, "cloud_coverage": 0, "condition": "sunny"} for i in range(24)]
                payload, validation = make_payload(minimal, query, diagnostic=True)
                last_validation = validation
                self.reply(payload, content_type="application/xml; charset=utf-8")
            elif parsed.path.rstrip("/") == "/debug/loxone/validate":
                self.json(validate_real_payload(query))
            else:
                self.reply("Not found\n", 404)
        except Exception as exc:
            log.exception("Request failed for %s", self.path)
            self.reply(f"Internal Server Error: {exc}\n", 500)


def main():
    o = opts()
    log.info("Weather4Lox HA %s starting on %s:%d", VERSION, HOST, PORT)
    log.info("Config: provider=%s refresh=%sm cache=%sm forecast_days=%s", o.get("weather_provider"), refresh_minutes(o.get("weather_provider", "openweathermap")), cache_ttl_minutes(o.get("weather_provider", "openweathermap")), forecast_days(o.get("weather_provider", "openweathermap")))
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
