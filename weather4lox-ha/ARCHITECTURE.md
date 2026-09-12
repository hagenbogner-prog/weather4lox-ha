# Weather4Lox HA architecture

## Provider model

Exactly one weather provider is active at runtime: `dwd` or `openweathermap`.
The app consumes Home Assistant `weather.*` entities and does not call provider APIs directly.

Each provider has its own refresh/cache policy. The configured forecast horizon is 1–7 days, but the app records the actual forecast length and resolution returned by Home Assistant instead of fabricating missing values.

## Data flow

```text
Loxone Gen 1
    -> DNS redirection -> Home Assistant host :6066
    -> Weather4Lox HA
    -> Home Assistant API
    -> selected DWD/OWM weather entity
    -> normalized real forecast
    -> atomic cache
    -> Loxone Format 2

Home Assistant UI
    -> App Info -> Open Web UI
    -> Ingress :8099 (internal only)
    -> Weather4Lox status and diagnostics
```

The Loxone service remains independent from the diagnostics UI. Loxone continues to use TCP port `6066`; the Home Assistant Ingress interface uses a separate internal port and is not a replacement for the Loxone endpoint.

## Cache rules

- Startup performs an immediate refresh, followed by the configured provider interval.
- A successful refresh completely replaces the previous cache atomically.
- A failed refresh preserves the last successful cache file.
- A preserved cache is only served to Loxone while it still matches provider/entity, remains inside its configured TTL, and its forecast range still covers the current date.
- Expired forecast data is retained for diagnosis but is not presented as a valid Loxone fallback.
- Cache metadata records provider, entity, timestamps, requested horizon, actual coverage, entry count and status.
- No synthetic weather forecast is generated in normal operation.
- Manual cache clearing removes the fallback cache deliberately.

## Entity discovery

With an explicit provider entity configured, that entity is used. With `auto`, the app searches existing `weather.*` states and scores provider attribution/name hints for DWD or OpenWeatherMap.

## Forecast retrieval

Weather4Lox requests forecasts through Home Assistant's `weather.get_forecasts` service. It attempts an hourly forecast first and then a daily forecast if the entity does not provide usable hourly data. Missing forecast support is surfaced as a diagnostic error rather than silently creating forecast values.

## Ingress diagnostics

The diagnostics interface is a presentation layer over the existing Weather4Lox runtime state. It does not maintain a second forecast cache and does not fetch weather from providers independently.

The interface shows provider, entity, forecast coverage, cache health, refresh timestamps, Loxone Format 2 validation and request counts. It intentionally excludes location names, coordinates, access tokens and other installation-specific private values.

## Home Assistant entities

The app can optionally publish normalized values through MQTT Discovery. This is an optional presentation layer; Loxone service operation does not depend on MQTT or on the Ingress dashboard.
