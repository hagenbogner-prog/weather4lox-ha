#!/usr/bin/env python3
from __future__ import annotations

import html
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

INGRESS_HOST = "0.0.0.0"
INGRESS_PORT = 8099
INGRESS_PROXY_IP = "172.30.32.2"
INGRESS_USER_HEADER = "X-Remote-User-Id"


def _iso(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def cache_is_usable(server, item, provider, entity):
    """Use the server's single cache-validity decision everywhere."""
    return bool(item and entity and server.cache_is_valid(item, provider, entity))


def is_ingress_request(headers, client_ip):
    """Accept requests authenticated and forwarded by Home Assistant Ingress."""
    user_id = str(headers.get(INGRESS_USER_HEADER, "")).strip()
    return client_ip == INGRESS_PROXY_IP and bool(user_id)


def _friendly_error(provider, entity, raw_error, cache_state):
    if not entity:
        return {
            "code": "weather_entity_missing",
            "title": "Keine passende Wetterentität gefunden",
            "message": "Weather4Lox konnte für den gewählten Provider keine weather.*-Entität finden. Prüfe die App-Konfiguration oder trage die Entität manuell ein.",
        }

    if raw_error:
        raw_lower = raw_error.lower()
        if provider == "openweathermap" and (
            "forecast" in raw_lower
            or "http 500" in raw_lower
            or "returned no forecast" in raw_lower
            or "server got itself in trouble" in raw_lower
        ):
            return {
                "code": "openweathermap_forecast_unavailable",
                "title": "OpenWeatherMap liefert keine Vorhersage",
                "message": "Prüfe in Home Assistant die OpenWeatherMap-Optionen. Weather4Lox benötigt einen Modus mit Forecast-Unterstützung, zum Beispiel 'forecast' oder 'v3.0'. Der Modus 'current' liefert nur aktuelle Wetterdaten.",
            }
        return {
            "code": "forecast_refresh_failed",
            "title": "Wettervorhersage konnte nicht aktualisiert werden",
            "message": raw_error,
        }

    if cache_state == "expired":
        return {
            "code": "forecast_expired",
            "title": "Wettervorhersage ist abgelaufen",
            "message": "Der gespeicherte Forecast ist nicht mehr aktuell. Weather4Lox liefert abgelaufene Vorhersagedaten nicht als gültigen Fallback an Loxone aus.",
        }

    if cache_state == "mismatch":
        return {
            "code": "cache_mismatch",
            "title": "Cache passt nicht zur aktuellen Konfiguration",
            "message": "Provider oder Wetterentität wurden geändert. Führe 'Jetzt prüfen' aus, damit Weather4Lox einen neuen Forecast für die aktuelle Konfiguration lädt.",
        }

    if cache_state == "empty":
        return {
            "code": "forecast_missing",
            "title": "Noch keine Wettervorhersage verfügbar",
            "message": "Weather4Lox hat noch keinen gültigen Forecast gespeichert. Führe 'Jetzt prüfen' aus, um Provider, Wetterentität und Loxone-Ausgabe zu testen.",
        }

    return None


def diagnostics(server):
    options = server.opts()
    provider = options.get("weather_provider", "openweathermap")
    entity = None
    entity_error = None
    try:
        entity = server.selected_entity(provider)
    except Exception as exc:
        entity_error = str(exc)

    cached = server.load_cache()
    age = server.cache_age_minutes(cached)
    ttl = server.cache_ttl_minutes(provider)
    matches = bool(entity and server.cache_matches(cached, provider, entity))
    usable = cache_is_usable(server, cached, provider, entity)
    forecast_entries = len(cached.get("forecast", [])) if cached else 0

    if not cached:
        cache_state = "empty"
    elif not matches:
        cache_state = "mismatch"
    elif usable:
        cache_state = "valid"
    else:
        cache_state = "expired"

    raw_error = entity_error or server.last_error
    issue = _friendly_error(provider, entity, raw_error, cache_state)

    if issue and usable:
        level = "warning"
        label = "Cache/Fallback"
    elif issue:
        level = "error"
        label = "Fehler"
    elif usable:
        level = "ok"
        label = "Betriebsbereit"
    else:
        level = "error"
        label = "Keine gültige Vorhersage"

    validation = server.last_validation or {}
    validation_ok = validation.get("ok") if validation else None
    last_success = server.last_success or (cached or {}).get("last_success")
    last_attempt = server.last_attempt or (cached or {}).get("last_attempt")

    return {
        "version": server.VERSION,
        "level": level,
        "status": label,
        "provider": provider,
        "entity": entity,
        "forecast": {
            "entries": forecast_entries,
            "start": (cached or {}).get("forecast_start"),
            "end": (cached or {}).get("forecast_end"),
            "requested_days": server.forecast_days(provider),
        },
        "cache": {
            "state": cache_state,
            "age_minutes": age,
            "validity_minutes": ttl,
            "usable": usable,
        },
        "refresh": {
            "interval_minutes": server.refresh_minutes(provider),
            "last_attempt": _iso(last_attempt),
            "last_success": _iso(last_success),
        },
        "loxone": {
            "request_count": server.request_count,
            "format_valid": validation_ok,
            "last_validation": validation,
        },
        "issue": issue,
        "raw_error": raw_error,
    }


def run_check(server):
    try:
        forecast, _, _ = server.obtain_forecast(force=True)
        query = {"coord": ["0,0"], "asl": ["0"]}
        _, validation = server.make_payload(forecast, query)
        server.last_validation = validation
    except Exception as exc:
        server.last_error = str(exc)
    return diagnostics(server)


def _fmt_minutes(value):
    if value is None:
        return "—"
    if value < 1:
        return "< 1 min"
    return f"{value:.0f} min"


def _fmt_time(value):
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone().strftime("%d.%m.%Y %H:%M:%S")
    except (TypeError, ValueError):
        return str(value)


def dashboard_html(server):
    state = diagnostics(server)
    level = state["level"]
    issue = state.get("issue")
    icon = {"ok": "✓", "warning": "!", "error": "×"}.get(level, "?")
    status_class = {"ok": "good", "warning": "warn", "error": "bad"}.get(level, "bad")
    issue_html = ""
    if issue:
        issue_html = f"""
        <section class="issue {status_class}">
          <h2>{html.escape(issue['title'])}</h2>
          <p>{html.escape(issue['message'])}</p>
        </section>
        """

    validation = state["loxone"]["format_valid"]
    validation_text = "Noch nicht geprüft" if validation is None else ("Gültig" if validation else "Fehler")
    cache_state_text = {
        "valid": "Gültig",
        "expired": "Abgelaufen",
        "empty": "Leer",
        "mismatch": "Anderer Provider / andere Entität",
    }.get(state["cache"]["state"], state["cache"]["state"])

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Weather4Lox</title>
<style>
:root {{ color-scheme: light dark; font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif; }}
body {{ margin:0; background:#111; color:#eee; }}
main {{ max-width:1050px; margin:0 auto; padding:24px; }}
header {{ display:flex; justify-content:space-between; gap:20px; align-items:center; margin-bottom:22px; }}
h1 {{ margin:0; font-size:28px; }} .sub {{ color:#aaa; margin-top:5px; }}
.status {{ display:flex; align-items:center; gap:12px; padding:14px 18px; border-radius:14px; font-weight:700; }}
.status .mark {{ width:30px; height:30px; display:grid; place-items:center; border-radius:50%; font-size:20px; }}
.good {{ background:#12351f; border:1px solid #2f8f4e; }} .good .mark {{ background:#2f8f4e; }}
.warn {{ background:#3c3012; border:1px solid #b68a1f; }} .warn .mark {{ background:#b68a1f; }}
.bad {{ background:#3b1518; border:1px solid #b43b45; }} .bad .mark {{ background:#b43b45; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; }}
.card {{ background:#1c1c1c; border:1px solid #3b3b3b; border-radius:14px; padding:18px; }}
.card h3 {{ margin:0 0 12px; font-size:15px; color:#aaa; font-weight:600; }}
.value {{ font-size:20px; font-weight:650; overflow-wrap:anywhere; }}
.detail {{ color:#aaa; margin-top:8px; font-size:13px; line-height:1.45; }}
.issue {{ border-radius:14px; padding:18px; margin:16px 0; }} .issue h2 {{ margin:0 0 8px; font-size:18px; }} .issue p {{ margin:0; line-height:1.5; }}
.actions {{ display:flex; flex-wrap:wrap; gap:10px; margin:20px 0; }}
button {{ border:0; border-radius:22px; padding:11px 18px; font-size:14px; font-weight:700; cursor:pointer; background:#03a9d9; color:#001a22; }}
button.secondary {{ background:#3a3a3a; color:#eee; }} button:disabled {{ opacity:.55; cursor:wait; }}
footer {{ color:#888; font-size:12px; margin-top:24px; }}
@media (max-width:640px) {{ header {{ align-items:flex-start; flex-direction:column; }} main {{ padding:16px; }} }}
@media (prefers-color-scheme:light) {{ body {{ background:#f5f5f5; color:#111; }} .card {{ background:white; border-color:#ddd; }} .sub,.detail,.card h3,footer {{ color:#666; }} button.secondary {{ background:#ddd; color:#111; }} }}
</style>
</head>
<body>
<main>
<header>
  <div><h1>Weather4Lox HA</h1><div class="sub">Status & Diagnose · Version {html.escape(str(state['version']))}</div></div>
  <div class="status {status_class}"><span class="mark">{icon}</span><span>{html.escape(state['status'])}</span></div>
</header>
{issue_html}
<div class="actions">
  <button id="check">Jetzt prüfen</button>
  <button class="secondary" id="reload">Anzeige aktualisieren</button>
</div>
<section class="grid">
  <article class="card"><h3>Wetterprovider</h3><div class="value">{html.escape(str(state['provider']))}</div><div class="detail">Aktiv ausgewählter Provider</div></article>
  <article class="card"><h3>Weather-Entität</h3><div class="value">{html.escape(state['entity'] or 'Nicht gefunden')}</div><div class="detail">Von Weather4Lox verwendete Home-Assistant-Entität</div></article>
  <article class="card"><h3>Forecast</h3><div class="value">{state['forecast']['entries']} Einträge</div><div class="detail">Bis {html.escape(_fmt_time(state['forecast']['end']))}</div></article>
  <article class="card"><h3>Cache</h3><div class="value">{html.escape(cache_state_text)}</div><div class="detail">Alter: {_fmt_minutes(state['cache']['age_minutes'])} · Gültigkeit: {_fmt_minutes(state['cache']['validity_minutes'])}</div></article>
  <article class="card"><h3>Letzte erfolgreiche Aktualisierung</h3><div class="value">{html.escape(_fmt_time(state['refresh']['last_success']))}</div><div class="detail">Intervall: {state['refresh']['interval_minutes']} min</div></article>
  <article class="card"><h3>Loxone Format 2</h3><div class="value">{html.escape(validation_text)}</div><div class="detail">Loxone-Anfragen seit Start: {state['loxone']['request_count']}</div></article>
</section>
<footer>Die Statusseite zeigt keine Standortdaten, Koordinaten oder Zugangsdaten an.</footer>
</main>
<script>
const check = document.getElementById('check');
const reload = document.getElementById('reload');
async function perform(path) {{
  check.disabled = true; reload.disabled = true;
  try {{ await fetch(path, {{method:'POST', cache:'no-store'}}); }} finally {{ location.reload(); }}
}}
check.addEventListener('click', () => perform('./api/check'));
reload.addEventListener('click', () => location.reload());
</script>
</body>
</html>"""


def make_handler(server):
    class IngressHandler(BaseHTTPRequestHandler):
        server_version = f"Weather4LoxHA-Ingress/{server.VERSION}"

        def log_message(self, fmt, *args):
            server.debug("Ingress %s - " + fmt, self.address_string(), *args)

        def _reply(self, body, status=200, content_type="text/html; charset=utf-8"):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, data, status=200):
            self._reply(json.dumps(data, ensure_ascii=False, indent=2, default=str), status, "application/json; charset=utf-8")

        def _is_authorized(self):
            if is_ingress_request(self.headers, self.client_address[0]):
                return True
            self._reply("Forbidden: Home Assistant Ingress required\n", 403, "text/plain; charset=utf-8")
            return False

        def do_GET(self):
            if not self._is_authorized():
                return
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            if path == "/":
                self._reply(dashboard_html(server))
                return
            if path == "/api/status":
                self._json(diagnostics(server))
                return
            if path == "/api/check":
                self._reply("Method not allowed\n", 405, "text/plain; charset=utf-8")
                return
            self._reply("Not found\n", 404, "text/plain; charset=utf-8")

        def do_POST(self):
            if not self._is_authorized():
                return
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            if path == "/api/check":
                self._json(run_check(server))
                return
            self._reply("Not found\n", 404, "text/plain; charset=utf-8")

    return IngressHandler


def start(server):
    httpd = ThreadingHTTPServer((INGRESS_HOST, INGRESS_PORT), make_handler(server))
    thread = Thread(target=httpd.serve_forever, name="weather4lox-ingress", daemon=True)
    thread.start()
    server.log.info("Ingress diagnostics UI listening on %s:%d", INGRESS_HOST, INGRESS_PORT)
    return httpd
