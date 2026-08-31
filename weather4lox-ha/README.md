# Weather4Lox HA — 0.3.7

Home Assistant OS app that emulates the Loxone Gen-1 Weather Service on TCP port 6066.

The project is being developed as a replacement for the LoxBerry Weather4Loxone setup. The implementation keeps a strong diagnostic focus so the real Miniserver can be tested safely before production use.

## Provider selection

Three modes are supported:

- `openweathermap` → `weather.openweathermap` plus the configured OpenWeatherMap sensor entities
- `dwd` → the configured DWD `weather.*` entity
- `custom` → any Home Assistant `weather.*` entity configured as `custom_weather_entity`

The selected provider is used for current conditions and forecast retrieval.

## Forecast engine

The Loxone Gen-1 service target is **181 hourly records**.

- Real hourly values are used unchanged where available.
- Missing gaps can be linearly interpolated.
- DWD/custom providers can use daily data when hourly data ends early.
- OpenWeatherMap deliberately does not repeat daily values as fake hourly records. If OWM cannot provide the complete hourly forecast, the real hourly part is retained and missing hours are filled with smooth deterministic synthetic continuation data for the legacy `/forecast` service.
- Provider/entity are part of the cache identity, so switching between DWD and OpenWeatherMap cannot accidentally reuse the other provider's cache.
- A cached forecast remains an additional last-resort fallback when enabled.

## Live LoxBerry-compatible JSON files

Version 0.3.7 adds the JSON data store used by the current Weather4Lox client format. Files are persisted inside the add-on at:

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

The JSON envelope follows Weather4Lox JSON schema v1.0, including `location`, source metadata, `current`/`dailyforecast`/`hourlyforecast`, Weather4Lox condition names and Loxone weather codes. Files are written atomically so a client never receives a partially written JSON document.

The JSON refresh is performed on startup and periodically while the service is running. A request to one of the JSON endpoints also refreshes stale data before serving the file.

## 0.3.5 Loxone compatibility layer

The legacy Loxone response keeps the proven 0.3.4 forecast engine and adds a compatibility layer between Home Assistant's weather response and the Loxone format-2 response:

- Converts Fahrenheit temperatures to Celsius.
- Converts m/s, mph and knots to km/h.
- Converts inHg, mmHg and bar to hPa.
- Converts inch precipitation to millimetres.
- Converts cardinal wind directions such as `SW` to degrees.
- Emits the configured timezone offset instead of a hard-coded zero.
- Keeps the Loxone response at exactly 29 columns per station row and validates the picto code range.

Home Assistant's `weather.get_forecasts` response provides fields such as temperature, apparent temperature, humidity, cloud coverage, precipitation, precipitation probability, pressure, wind bearing and wind speed. Providers may omit fields they do not supply.

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

The repository is a Home Assistant app repository. Home Assistant reads the app version from `weather4lox-ha/config.yaml`. Version **0.3.7** is now the version declared on `main`.

If an installed copy still shows an older version, refresh/repair the repository in the Home Assistant App Store before testing the update.
