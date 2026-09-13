# Weather4Lox HA documentation

Weather4Lox HA exposes Home Assistant weather forecasts to a Loxone Miniserver Gen 1 through a local HTTP service on TCP port `6066`.

## How it works

1. Select exactly one provider: `openweathermap` or `dwd`.
2. Weather4Lox selects the configured Home Assistant `weather.*` entity or auto-detects a matching entity.
3. Forecast data is requested through Home Assistant's weather service.
4. A successful refresh completely replaces the previous forecast cache.
5. Weather4Lox converts the cached forecast into the Loxone Weather Service Format 2 response.
6. Loxone reads the local Weather4Lox endpoint.

Weather4Lox does not call DWD or OpenWeatherMap directly. Home Assistant remains responsible for the provider integration.

## Status & diagnostics web interface

Open the Weather4Lox app in Home Assistant and select **Open Web UI**.

The dashboard reports:

- overall state: operational, cache/fallback, or error
- configured provider
- selected weather entity
- number and time range of forecast entries
- cache age and configured validity
- last refresh attempt and last successful refresh
- Loxone Format 2 validation result
- real Loxone `/forecast` request count since app startup
- a human-readable explanation for detected configuration problems

Use **Check now** to perform an immediate forecast refresh and validate the Loxone payload. The dashboard keeps the result visible as a success, warning, or error message and updates the Format 2 status immediately.

The **Direct service endpoints** section provides links to `/status` and `/control/refresh` on port `6066`. The dashboard derives the IP address or hostname from the current Home Assistant browser URL; it does not contain a hard-coded installation address. These links are intended for the local network. Remote Home Assistant URLs normally cannot reach the local Loxone port, and port `6066` should not be forwarded to the internet.

The dashboard does not expose configured location names, coordinates, access tokens, or other private configuration values.

The diagnostics service is available only through Home Assistant Ingress. It accepts connections only from the Supervisor Ingress proxy at `172.30.32.2`, requires the authenticated user header added by the Supervisor, and is not published as a host port. The sidebar entry remains restricted to Home Assistant administrators.

## OpenWeatherMap

Weather4Lox needs forecast-capable data from the Home Assistant OpenWeatherMap integration.

Suitable modes include:

- `forecast`
- `v3.0`

The `current` mode only provides current weather conditions. If OpenWeatherMap is configured as `current`, Home Assistant may still show current weather values, but `weather.get_forecasts` does not provide the forecast required by Weather4Lox.

When this condition is detected, the Weather4Lox dashboard shows a specific configuration hint instead of only presenting the underlying HTTP error.

## DWD

Select `dwd` as the Weather4Lox provider and either leave the weather entity on `auto` or enter the desired DWD `weather.*` entity manually.

## Cache behavior

Each provider has an independent refresh interval and cache validity period.

Default values:

| Provider | Refresh interval | Cache validity |
|---|---:|---:|
| DWD | 120 minutes | 24 hours |
| OpenWeatherMap | 60 minutes | 48 hours |

A successful refresh creates a complete new cache. Weather4Lox never merges old forecast rows into newly received data.

If a refresh fails, a matching cached forecast may only be used while it is still within the configured cache validity and its exact forecast end time is still in the future. An expired forecast is not served as a valid Loxone fallback.

## Forecast coverage

`forecast_days` accepts a value from 1 to 7 days. This setting is the requested Weather4Lox horizon; the actual coverage depends on the selected Home Assistant provider.

Weather4Lox does not invent missing forecast entries to fill the requested horizon.

## Loxone endpoint

The Loxone Miniserver requests the local service on port `6066`, normally through a DNS redirection of `weather.loxone.com` to the Home Assistant host.

The endpoint is:

```text
/forecast/?user=...&coord=longitude,latitude&asl=elevation&format=2&new_api=1
```

The generated Format 2 response is validated before being returned:

- 29 metadata fields
- 10 station metadata fields
- 19 fields per forecast row
- supported numeric Loxone pictograms
- response terminator and structure expected by the Weather Service format

## Configuration

### Weather provider

`weather_provider`

Choose `openweathermap` or `dwd`.

### Weather entity

`openweathermap_weather_entity` and `dwd_weather_entity`

Use `auto` for provider-based detection or enter an explicit Home Assistant weather entity such as `weather.example`.

### Refresh and cache settings

Provider-specific refresh and cache values are configured independently. In normal use the defaults should be sufficient.

### Location metadata

Weather4Lox includes station metadata in the Loxone response. New installations use neutral defaults and should be configured for the local installation if those fallback values are required. Coordinates supplied by the Loxone request are preferred for the response.

Location data is not shown on the Weather4Lox diagnostics dashboard.

## Troubleshooting

### Status: OpenWeatherMap does not provide a forecast

Check Home Assistant:

**Settings → Devices & services → OpenWeatherMap → Options**

Use a forecast-capable mode. `current` is not sufficient for Weather4Lox forecasting.

After changing the Home Assistant integration, open the Weather4Lox web interface and select **Check now**.

### No matching weather entity

Verify that the corresponding Home Assistant weather integration is loaded and has a `weather.*` entity. You can also enter the entity ID manually in the Weather4Lox configuration.

### Cache expired

An expired forecast is deliberately rejected. Fix the provider or weather entity and run **Check now** to rebuild the cache from live Home Assistant forecast data.

### Loxone does not show weather data

Check the dashboard in this order:

1. provider
2. weather entity
3. forecast entry count
4. cache state
5. Loxone Format 2 validation
6. Loxone request counter

If the request counter does not increase while the Miniserver requests weather data, verify DNS redirection and TCP port `6066` reachability.

Opening `/health`, `/status` or another diagnostic endpoint does not increase the Loxone request counter. Stored request diagnostics contain only the endpoint, time, and parameter names; parameter values such as users or coordinates are not retained.

## Diagnostic HTTP endpoints

The Loxone service continues to expose the existing diagnostic endpoints on port `6066`:

```text
/health
/status
/raw
/debug/forecast
/debug/loxone/validate
/control/refresh
```

`/raw` returns normalized weather values only and does not expose the raw Home Assistant attribute dictionary.

The Ingress dashboard is served separately on the internal Ingress port and is intended to be accessed through Home Assistant.
