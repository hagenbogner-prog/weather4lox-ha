# Weather4Lox HA

Weather4Lox HA is a Home Assistant app that provides Home Assistant weather forecasts to a Loxone Miniserver Gen 1 using the local Loxone Weather Service protocol on TCP port `6066`.

It reads a selected Home Assistant `weather.*` entity, maintains a provider-specific forecast cache, validates the generated Loxone Format 2 payload, and serves the result locally to Loxone.

## Architecture

```text
Loxone Miniserver Gen 1
        |
        | weather.loxone.com -> Home Assistant via DNS redirection
        | HTTP :6066 /forecast/
        v
Weather4Lox HA app
        |
        | Home Assistant API
        v
Selected HA weather entity
  ├─ OpenWeatherMap
  └─ DWD
        |
        v
forecast -> cache -> Loxone Format 2
```

This repository contains only the Home Assistant app. It does not require LoxBerry.

## Features

- OpenWeatherMap and DWD provider support
- automatic or manual Home Assistant weather entity selection
- provider-specific refresh intervals and cache validity
- requested forecast horizon from 1 to 7 days
- atomic cache replacement after successful refreshes
- no synthetic forecast generation during normal operation
- Loxone Format 2 validation
- Home Assistant Ingress status and diagnostics web interface
- clear error hints for missing or unsupported forecast data
- manual forecast check from the web interface

## Home Assistant installation

Add this GitHub repository as a Home Assistant app repository:

```text
https://github.com/hagenbogner-prog/weather4lox-ha
```

Then install **Weather4Lox HA** from the Home Assistant App Store.

## Status & diagnostics

Starting with version 0.6.0, the app provides a Home Assistant Ingress web interface. Open the Weather4Lox app and select **Open Web UI**.

The dashboard shows:

- overall status
- selected provider
- selected weather entity
- forecast entry count and range
- cache state and age
- last successful refresh
- Loxone Format 2 validation state
- Loxone request count
- actionable configuration errors

The diagnostics interface intentionally does not display configured location names, coordinates, access tokens, or other private settings.

## Providers

Exactly one provider is active: `openweathermap` or `dwd`.

Weather4Lox does not call the provider API directly. It consumes the selected Home Assistant `weather.*` entity through Home Assistant.

### OpenWeatherMap

Weather4Lox requires a forecast-capable OpenWeatherMap mode. Modes such as `forecast` or `v3.0` can provide forecast data. The `current` mode provides current conditions only and therefore cannot supply the forecast Weather4Lox needs.

### DWD

DWD forecast data can be selected automatically when a matching Home Assistant weather entity is available, or an entity ID can be configured manually.

## Cache behavior

A successful refresh fully replaces the previous forecast cache. If a refresh fails, Weather4Lox may use the last matching cached forecast only while it is inside its configured TTL and its exact forecast end time is still in the future.

Expired forecast data is not presented to Loxone as a valid fallback.

Provider defaults:

| Provider | Refresh | Cache validity |
|---|---:|---:|
| DWD | 120 min | 24 h |
| OpenWeatherMap | 60 min | 48 h |

The requested forecast horizon is 1–7 days. Actual coverage depends on the Home Assistant provider. Weather4Lox does not invent missing forecast rows.

## Loxone endpoint

The local service is available on port `6066`:

```text
http://HOME_ASSISTANT_IP:6066/forecast/?user=loxone&coord=longitude,latitude&asl=elevation&format=2&new_api=1
```

The response is validated for:

- 29 metadata fields
- 10 station metadata fields
- 19 fields per forecast row
- supported numeric Loxone pictograms
- expected Format 2 structure

## Diagnostics endpoints

```text
GET /health
GET /status
GET /raw
GET /debug/forecast
GET /debug/loxone/validate
GET /control/refresh
GET /control/clear-cache
```

## Documentation

The Home Assistant app includes dedicated Info, Documentation, Configuration, Log, and Web UI views. See `weather4lox-ha/DOCS.md` for detailed setup and troubleshooting information.

## Development

CI compiles the Python sources, runs the test suite, validates configuration files, and builds the app image for supported architectures.

## Privacy

Public documentation and example configuration intentionally use neutral placeholders. Do not commit personal coordinates, local IP addresses, access tokens, or other private installation details to this repository.

## License

MIT

<!-- AUTO-GENERATED: ci-docs.yml -->
Current version: **0.6.0**  
Forecast horizon: **1–7 days**  
Provider refresh: **DWD 120 min / OpenWeatherMap 60 min**  
<!-- END AUTO-GENERATED -->
