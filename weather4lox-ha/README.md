# Weather4Lox HA — 0.3.8

Home Assistant OS app that emulates the Loxone Gen-1 Weather Service on TCP port 6066.

The project is being developed as a replacement for the LoxBerry Weather4Loxone setup. The implementation keeps a strong diagnostic focus so the real Miniserver can be tested safely before production use.

## Provider selection

Three modes are supported:

- `openweathermap` → `weather.openweathermap` plus the configured OpenWeatherMap sensor entities
- `dwd` → the configured DWD `weather.*` entity
- `custom` → any Home Assistant `weather.*` entity configured as `custom_weather_entity`

The selected provider is used for current conditions and forecast retrieval.

## Forecast engine

The legacy Loxone Gen-1 service target is **181 hourly records**. The live Weather4Lox JSON files follow the current Weather4Lox v4 schema and contain up to **167 forecast hours**, matching the v4 LoxBerry grabber behaviour after excluding the current/past hour.

- Real hourly values are used unchanged where available.
- Missing gaps can be linearly interpolated.
- DWD/custom providers can use daily data when hourly data ends early.
- OpenWeatherMap can use the deterministic continuation already implemented by the legacy forecast engine when the provider does not supply the complete target range.
- Provider/entity are part of the cache identity, so switching between DWD and OpenWeatherMap cannot accidentally reuse the other provider's cache.
- A cached forecast remains an additional last-resort fallback when enabled.

## Live LoxBerry-compatible JSON files

The add-on persists the three v4 JSON files at:

```text
/data/weather4lox/current.json
/data/weather4lox/dailyforecast.json
/data/weather4lox/hourlyforecast.json
```

The same files are exposed at the client-compatible HTTP paths:

```text
/plugins/weather4lox/current.json
/plugins/weather4lox/dailyforecast.json
/plugins/weather4lox/hourlyforecast.json
```

The envelope and nested field names follow the Weather4Lox JSON schema v1.0: `location`, provider-specific metadata, `current`/`dailyforecast`/`hourlyforecast`, Weather4Lox condition names, Loxone weather codes, nested wind/temperature/precipitation structures and Unix epoch timestamps.

Files are written atomically so a client never receives a partially written JSON document. The JSON generator is separated into `json_compat.py` so the HTTP layer remains small and the schema can be tested independently.

## Legacy Loxone response

The legacy `/forecast` response remains the format-2, 29-column semicolon-delimited service used by the Gen-1 Miniserver. The compatibility layer keeps protocol-safe Loxone picto codes in the documented 1..29 range and performs the required unit conversions.

## Diagnostics

### Health

```text
http://HOME_ASSISTANT_IP:6066/health
```

### Loxone diagnostic endpoints

```text
/debug/loxone/minimal
/debug/loxone/validate
/debug/loxone/reference
```

`/debug/loxone/minimal` produces a controlled 181-hour Weather4Lox format-2 response. This is the recommended first test when investigating Loxone Gen-1 `reactWeatherIcon` errors.

## Updating from the GitHub repository

The repository is a Home Assistant app repository. Home Assistant reads the app version from `weather4lox-ha/config.yaml`. Version **0.3.8** is the live JSON compatibility release.

If an installed copy still shows an older version, refresh/repair the repository in the Home Assistant App Store before testing the update.
