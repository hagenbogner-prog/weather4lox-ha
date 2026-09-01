# Weather4Lox HA architecture

## Provider model

Exactly one weather provider is active at runtime: `dwd` or `openweathermap`.
The app consumes Home Assistant `weather.*` entities and does not call provider APIs directly.

Each provider has its own refresh/cache policy. The configured forecast horizon is 1–7 days, but the app records the actual forecast length and resolution returned by Home Assistant instead of fabricating missing values.

## Data flow

```text
Loxone Gen 1
    -> DNSMasq -> Home Assistant host :6066
    -> Weather4Lox HA
    -> Home Assistant Supervisor API
    -> selected DWD/OWM weather entity
    -> normalized real forecast
    -> atomic cache
    -> Loxone format=2
```

Loxone requests are served from the local cache. The periodic refresh loop is independent of Loxone traffic.

## Cache rules

- Startup performs an immediate refresh, followed by the configured provider interval.
- A successful refresh completely replaces the previous cache atomically.
- A failed refresh preserves the last successful cache.
- Cache metadata records provider, entity, timestamps, requested horizon, actual coverage, entry count and status.
- No synthetic weather forecast is generated in normal operation.
- Manual cache clearing removes the fallback cache deliberately.

## Entity discovery

With an explicit provider entity configured, that entity is used. With `auto`, the app searches existing `weather.*` states and scores provider attribution/name hints for DWD or OpenWeatherMap.

## Home Assistant entities

The app can optionally publish normalized values through MQTT Discovery. This is an optional presentation layer; Loxone service operation does not depend on MQTT.
