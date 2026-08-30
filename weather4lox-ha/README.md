# Weather4Lox HA — test add-on 0.3.3

Home Assistant OS add-on that emulates the Loxone Gen-1 Weather Service on TCP port 6066.

The project is being developed as a replacement for the LoxBerry Weather4Loxone setup. The implementation keeps a strong diagnostic focus so the real Miniserver can be tested safely before production use.

## Provider selection

Three modes are supported:

- `openweathermap` → `weather.openweathermap` plus the configured OpenWeatherMap sensor entities
- `dwd` → the configured DWD `weather.*` entity
- `custom` → any Home Assistant `weather.*` entity configured as `custom_weather_entity`

The selected provider is used for current conditions and forecast retrieval.

## Forecast engine

The add-on requests Home Assistant's `weather.get_forecasts` service for hourly data.

The target is **181 hourly records**, matching the Loxone Gen-1 weather service layout used by the original Weather4Loxone integration.

- Real hourly values are used unchanged.
- Missing gaps can be linearly interpolated.
- DWD/custom providers can use daily data when hourly data ends early.
- OpenWeatherMap deliberately does **not** repeat daily values as fake hourly records. If OWM cannot provide the complete hourly forecast, the real hourly part is retained and the missing hours are filled with smooth, deterministic synthetic continuation data.
- Provider/entity are part of the cache identity, so switching between DWD and OpenWeatherMap cannot accidentally reuse the other provider's cache.
- A cached forecast remains an additional last-resort fallback when enabled.

Synthetic records are marked internally with `_source: synthetic` and are reported in the diagnostics/logging.

## Diagnostics

### Health

```text
http://HOME_ASSISTANT_IP:6066/health
```

### Status

```text
http://HOME_ASSISTANT_IP:6066/status
```

Shows provider, entity, cache age, forecast count, last error, request statistics and the last Loxone validation result.

### Current HA weather data

```text
http://HOME_ASSISTANT_IP:6066/raw
```

### Forecast data from HA / normalized forecast

```text
http://HOME_ASSISTANT_IP:6066/debug/forecast
```

Use `?refresh=1` to bypass the fresh provider cache.

### Exact Loxone response

```text
http://HOME_ASSISTANT_IP:6066/debug/loxone/?user=loxone_TEST&coord=10.681,48.56&asl=450&format=2&new_api=1
```

`/forecast/` produces the same response.

## Loxone validation

Before a response is sent, 0.3.3 validates:

- exactly 181 forecast rows
- exactly 29 metadata columns
- exactly 29 columns in every station row
- numeric/finite weather values where required
- `picto-code` values in the Loxone/Meteoblue-compatible range 1–35
- complete `<mb_metadata>`, `<valid_until>` and `<station>` sections
- no response truncation

The generated response is returned in full; no diagnostic `... (truncated)` text is ever inserted into the Loxone payload.

## Configuration

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

Custom provider:

```yaml
weather_provider: custom
custom_weather_entity: weather.my_provider
```

General defaults:

```yaml
target_hours: 181
cache_ttl_minutes: 60
fallback_to_cache: true
interpolate_missing_hours: true
synthetic_fallback: true
country: Germany
timezone: Europe/Berlin
debug_logging: true
```

## Test sequence

From another device on the LAN:

```bash
curl http://192.168.178.158:6066/health
curl http://192.168.178.158:6066/status
curl http://192.168.178.158:6066/raw
curl "http://192.168.178.158:6066/debug/forecast?refresh=1"
curl "http://192.168.178.158:6066/debug/loxone/?user=loxone_TEST&coord=10.681,48.56&asl=450&format=2&new_api=1"
```

DNS:

```bash
nslookup weather.loxone.com
```

The result should point to the Home Assistant IP.

## Logging

With `debug_logging: true`, the add-on logs request parameters, provider/entity selection, HA forecast counts, cache usage, interpolation/fallback counts, synthetic fallback counts and the complete Loxone validation summary.

## Important

This remains a compatibility test build. Keep the old LoxBerry setup available until the Gen-1 Miniserver has successfully accepted the new service over several update cycles.
