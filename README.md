# Weather4Lox HA

Home Assistant app that emulates the Loxone Gen 1 Weather Service on TCP port 6066. It reads the selected Home Assistant weather entity and serves the `format=2` response expected by a Loxone Miniserver.

The protocol follows the Local Weather Service Emulator architecture described by SmartHome.Exposed: DNS redirection remains external to the app, the app refreshes and stores a local forecast cache, and Loxone reads the local service.

Reference: https://smarthome.exposed/local-weather-service-emulator/

## Architecture

```text
Loxone Miniserver Gen 1
        |
        | weather.loxone.com -> Home Assistant via dnsmasq
        | HTTP :6066 /forecast/
        v
Weather4Lox HA app
        |
        | Home Assistant Supervisor API
        v
Selected HA weather entity
  ├─ OpenWeatherMap
  └─ DWD
        |
        v
normalized forecast -> atomic cache -> Loxone format=2
```

This repository contains only the Home Assistant app. There is no LoxBerry plugin, LoxBerry runtime, or LoxBerry-specific endpoint.

## Loxone endpoint

```text
http://HOME_ASSISTANT_IP:6066/forecast/?user=loxone_TEST&coord=10.681,48.56&asl=450&format=2&new_api=1
```

The response contains:

- a 29-field `<mb_metadata>` header
- a 10-field station metadata line
- 19 fields per forecast row
- numeric Loxone pictograms
- local date/time and UTC offset
- temperature, feels-like, wind, clouds, precipitation, pressure and humidity where supplied by Home Assistant

## Providers and forecast coverage

Exactly one provider is active: `openweathermap` or `dwd`.

The app does **not** call the provider API directly. It consumes the selected `weather.*` entity through Home Assistant. With `weather_entity: auto`, it searches existing weather entities using provider attribution/name hints; an explicit entity ID can always be configured.

The configured forecast horizon is 1–7 days. The app never invents missing weather data to reach that target: the cache records the requested horizon and the actual number/range of forecast entries returned by Home Assistant. A successful refresh completely replaces the previous cache; a failed refresh keeps the last successful cache for fallback.

Provider defaults:

| Provider | Refresh | Cache validity | Max requested horizon |
|---|---:|---:|---:|
| DWD | 120 min | 24 h | 7 days |
| OpenWeatherMap | 60 min | 48 h | 7 days |

Cache validity is bounded by the configured forecast horizon. Refresh is performed immediately at app startup and then at the provider-specific interval.

## Cache and controls

`/status` exposes provider, selected entity, cache age, requested/actual coverage, refresh interval, last attempt/success/error and validation state.

Manual controls:

```text
GET /control/refresh
GET /control/clear-cache
```

Clearing the cache deliberately removes the fallback. A failed manual or scheduled refresh does not destroy an existing cache.

## Home Assistant entities

The app uses the same normalized data for Loxone and can optionally publish sensor entities through MQTT Discovery when the Home Assistant MQTT integration is installed. Loxone operation does not depend on MQTT.

## Default location

- Wertingen, Germany
- latitude `48.56`
- longitude `10.681`
- elevation `450 m`
- timezone `Europe/Berlin`

The Loxone request's `coord` and `asl` values are used in the station metadata response.

## Testing

```bash
curl http://HOME_ASSISTANT_IP:6066/health
curl http://HOME_ASSISTANT_IP:6066/status
curl "http://HOME_ASSISTANT_IP:6066/forecast/?user=loxone_TEST&coord=10.681,48.56&asl=450&format=2&new_api=1"
curl http://HOME_ASSISTANT_IP:6066/control/refresh
curl http://HOME_ASSISTANT_IP:6066/control/clear-cache
```

Diagnostics are also available at `/raw`, `/debug/forecast` and `/debug/loxone/validate`.

## Development

CI compiles the Python sources, validates the Home Assistant app configuration, builds the Docker image and runs the test suite. The project does not create ZIP packages.

## License

MIT

<!-- AUTO-GENERATED: ci-docs.yml -->
Current version: **0.5.0**  
Forecast horizon: **1–7 days**  
Provider refresh: **DWD 120 min / OpenWeatherMap 60 min**  
<!-- END AUTO-GENERATED -->
