# Weather4Lox HA

Home Assistant add-on providing a Loxone Weather Service compatible API on port 6066, replacing the LoxBerry Weather4Loxone plugin for Loxone Miniserver Gen 1.

> **Status:** Experimental / test version. The current release adds the LoxBerry-compatible JSON files needed by the live Weather4Lox client.

## Goal

This project provides a small HTTP service for Home Assistant OS that emulates the weather endpoint expected by a Loxone Miniserver Gen 1.

The intended setup is:

```text
Loxone Miniserver Gen 1
        |
        | HTTP :6066
        v
weather.loxone.com
        |
        v
Home Assistant OS
        |
        v
Weather4Lox HA add-on
        |
        v
Home Assistant weather entity
```

DNSMasq should resolve `weather.loxone.com` to the Home Assistant IP address.

## Live LoxBerry-compatible JSON data

The add-on now persists the three Weather4Lox v4 JSON files under:

```text
/data/weather4lox/current.json
/data/weather4lox/dailyforecast.json
/data/weather4lox/hourlyforecast.json
```

They are exposed to the LoxBerry/Weather4Lox client at the original HTTP paths:

```text
/plugins/weather4lox/current.json
/plugins/weather4lox/dailyforecast.json
/plugins/weather4lox/hourlyforecast.json
```

The envelope and field structure follow the Weather4Lox JSON schema v1.0 used by the original LoxBerry grabbers, including `location`, source metadata, current/daily/hourly data, Weather4Lox condition identifiers and Loxone weather codes. Files are written atomically and refreshed periodically.

## Current test scope

- HTTP server on TCP port 6066
- `/health` endpoint
- `/forecast/` endpoint
- LoxBerry-compatible `current.json`, `dailyforecast.json` and `hourlyforecast.json`
- Request logging for Loxone diagnostics
- Reading weather data from Home Assistant
- Configurable Home Assistant weather entity and sensor entities
- Diagnostic `/raw` endpoint
- Loxone format-2 response generation and validation

## Configuration

The default configuration targets these entities:

- `weather.openweathermap`
- `sensor.openweathermap_temperatur`
- `sensor.openweathermap_gefuhlte_temperatur`
- `sensor.openweathermap_luftfeuchtigkeit`
- `sensor.openweathermap_druck`
- `sensor.openweathermap_bewolkung`
- `sensor.openweathermap_windgeschwindigkeit`
- `sensor.openweathermap_windboengeschwindigkeit`
- `sensor.openweathermap_windrichtung`
- `sensor.openweathermap_regenintensitat`
- `sensor.openweathermap_schneeintensitat`

These can be changed in the add-on configuration.

## Testing

After installation, test the service from another device on the LAN:

```bash
curl http://HOME_ASSISTANT_IP:6066/health
```

Then test the Loxone endpoint:

```bash
curl "http://HOME_ASSISTANT_IP:6066/forecast/?user=loxone_TEST&coord=10.681,48.56&asl=450&format=2&new_api=1"
```

Then test the three JSON files:

```bash
curl "http://HOME_ASSISTANT_IP:6066/plugins/weather4lox/current.json"
curl "http://HOME_ASSISTANT_IP:6066/plugins/weather4lox/dailyforecast.json"
curl "http://HOME_ASSISTANT_IP:6066/plugins/weather4lox/hourlyforecast.json"
```

Finally verify DNS:

```bash
nslookup weather.loxone.com
```

The result should point to the Home Assistant IP address.

## License

MIT

<!-- AUTO-GENERATED: ci-docs.yml -->
Current version: **0.3.7**  
Forecast target: **181 hours**  
<!-- END AUTO-GENERATED -->
