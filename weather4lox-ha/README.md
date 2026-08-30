# Weather4Lox HA — test add-on 0.3.0

Home Assistant OS add-on that emulates the Loxone Gen-1 Weather Service on TCP port 6066.

The project is being developed as a replacement for the LoxBerry Weather4Loxone setup. The implementation deliberately keeps a strong diagnostic focus so the real Miniserver can be tested safely before production use.

## Provider selection

The add-on supports three modes:

- `openweathermap` → `weather.openweathermap` plus the configured OpenWeatherMap sensor entities
- `dwd` → `weather.wertingen`
- `custom` → any Home Assistant `weather.*` entity configured as `custom_weather_entity`

The selected provider is used for current conditions and forecast retrieval.

## Forecast engine

The add-on requests Home Assistant's `weather.get_forecasts` service for `hourly` data and, when the hourly result is shorter than the configured target, also requests `daily` data.

The forecast normalizer creates a one-hour grid:

1. Real hourly values are used unchanged.
2. Gaps between real hourly values can be linearly interpolated when `interpolate_missing_hours` is enabled.
3. When hourly data ends early, daily data is used as a clearly marked fallback.
4. If the provider temporarily fails, the last cached forecast can be served.

The default target is 168 hourly data points (7 x 24). The target is configurable up to 240 hours.

## Cache

Forecast data is cached in the add-on `/data` directory so it survives a restart. The default cache TTL is 60 minutes. This prevents every Loxone request from triggering a new Home Assistant forecast request.

Configuration:

```yaml
cache_ttl_minutes: 60
fallback_to_cache: true
```

## Diagnostics

### Health

```text
http://HOME_ASSISTANT_IP:6066/health
```

### Status

```text
http://HOME_ASSISTANT_IP:6066/status
```

Shows provider, entity, cache age, number of forecast entries, last error and request statistics.

### Current HA weather data

```text
http://HOME_ASSISTANT_IP:6066/raw
```

### Forecast data from HA / normalized forecast

```text
http://HOME_ASSISTANT_IP:6066/debug/forecast
```

Use `?refresh=1` to bypass the fresh cache for a diagnostic request.

### Exact Loxone response

```text
http://HOME_ASSISTANT_IP:6066/debug/loxone/?user=test&coord=10.681,48.56&asl=450&format=1
```

`/forecast/` is the same Loxone response endpoint.

## Loxone compatibility

The response follows the documented Weather4Lox / Meteoblue-style XML/CSV structure:

- `<mb_metadata>` header
- semicolon-separated station columns
- `<valid_until>`
- `<station>` with hourly rows
- 29 data columns
- valid Meteoblue/Loxone `picto-code` values
- explicit trailing semicolons

The icon mapping is kept separately in `loxone_pictos.json` so it can be maintained independently of the server code.

## Configuration example

OpenWeatherMap:

```yaml
weather_provider: openweathermap
weather_entity: weather.openweathermap
```

DWD:

```yaml
weather_provider: dwd
dwd_weather_entity: weather.wertingen
```

Custom HA weather entity:

```yaml
weather_provider: custom
custom_weather_entity: weather.my_provider
```

## Installation

Add the GitHub repository to Home Assistant's add-on/app repository list:

`https://github.com/hagenbogner-prog/weather4lox-ha`

Install **Weather4Lox HA** and start it.

## First test sequence

From another device on the LAN:

```bash
curl http://192.168.178.158:6066/health
curl http://192.168.178.158:6066/status
curl http://192.168.178.158:6066/raw
curl http://192.168.178.158:6066/debug/forecast
curl "http://192.168.178.158:6066/debug/loxone/?user=loxone_TEST&coord=10.681,48.56&asl=450&format=1"
```

DNS:

```bash
nslookup weather.loxone.com
```

The result should point to the Home Assistant IP.

## Logging

With `debug_logging: true`, the add-on logs request parameters, provider/entity selection, forecast counts, cache usage, interpolation/fallback counts and response size. Debug logging can be disabled after compatibility testing.

## Important

This is a compatibility test build. The real Gen-1 Miniserver must be used to validate the final response. Do not remove the old LoxBerry setup until the Miniserver has successfully accepted the new service over several update cycles.
