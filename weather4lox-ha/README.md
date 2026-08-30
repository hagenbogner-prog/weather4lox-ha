# Weather4Lox HA — 0.3.4

Home Assistant OS app that emulates the Loxone Gen-1 Weather Service on TCP port 6066.

The project is being developed as a replacement for the LoxBerry Weather4Loxone setup. The implementation keeps a strong diagnostic focus so the real Miniserver can be tested safely before production use.

## Provider selection

Three modes are supported:

- `openweathermap` → `weather.openweathermap` plus the configured OpenWeatherMap sensor entities
- `dwd` → the configured DWD `weather.*` entity
- `custom` → any Home Assistant `weather.*` entity configured as `custom_weather_entity`

The selected provider is used for current conditions and forecast retrieval.

## Forecast engine

The target is **181 hourly records**, matching the Loxone Gen-1 weather service layout used by the original Weather4Loxone integration.

- Real hourly values are used unchanged.
- Missing gaps can be linearly interpolated.
- DWD/custom providers can use daily data when hourly data ends early.
- OpenWeatherMap deliberately does not repeat daily values as fake hourly records. If OWM cannot provide the complete hourly forecast, the real hourly part is retained and missing hours are filled with smooth deterministic synthetic continuation data.
- Provider/entity are part of the cache identity, so switching between DWD and OpenWeatherMap cannot accidentally reuse the other provider's cache.
- A cached forecast remains an additional last-resort fallback when enabled.

## Diagnostics

### Health

```text
http://HOME_ASSISTANT_IP:6066/health
```

### Loxone diagnostic endpoints

The 0.3.4 diagnostic endpoints are intentionally independent of DWD/OWM data:

```text
/debug/loxone/minimal
/debug/loxone/validate
/debug/loxone/reference
```

`/debug/loxone/minimal` produces a controlled 181-hour Weather4Lox format-2 response. This is the recommended first test when investigating Loxone Gen-1 `reactWeatherIcon` errors.

## Updating from the GitHub repository

The repository is a Home Assistant app repository. Home Assistant reads the app version from `weather4lox-ha/config.yaml`. Version **0.3.4** is currently published on `main`.

If an installed copy still shows an older version, refresh/repair the repository in the Home Assistant App Store before testing the update. Home Assistant's Supervisor documentation recommends repairing a repository when its store metadata is stale or incorrect.
