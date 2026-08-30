# Weather4Lox HA — test add-on

Experimental Home Assistant OS add-on that emulates the Loxone Gen-1 Weather Service on TCP port 6066.

## Weather provider selection

The add-on can use either of the two weather integrations already present in the user's Home Assistant setup:

- `openweathermap` → `weather.openweathermap` plus the dedicated OpenWeatherMap sensor entities
- `dwd` → `weather.wertingen`

The selection is made in the add-on configuration via **Weather provider**. The selected entity is used for both current conditions and the hourly forecast.

## Seven-day hourly forecast

For every `/forecast/` request the add-on calls Home Assistant's `weather.get_forecasts` service with `type: hourly` and requests the response data through the Home Assistant API. The Loxone-compatible response contains up to 181 hourly entries, matching the roughly seven-day report expected by a Loxone Miniserver Gen 1.

If the selected weather integration provides fewer than 181 hourly entries, the add-on does **not** invent missing weather data. It logs a warning with the number of available entries. This is important because forecast length depends on the underlying weather integration and, for some providers, the API plan.

## Installation

Add the GitHub repository to Home Assistant's add-on/app repository list:

`https://github.com/hagenbogner-prog/weather4lox-ha`

Install **Weather4Lox HA** and start it.

## Configuration

Default provider:

```yaml
weather_provider: openweathermap
```

OpenWeatherMap entities are preconfigured for the entities used in the original test setup. The DWD entity defaults to:

```yaml
dwd_weather_entity: weather.wertingen
```

Change **Weather provider** to `dwd` when you want to use the DWD integration instead.

## First tests

From another device on the LAN:

```bash
curl http://192.168.178.158:6066/health
```

Expected:

```text
lox-weather-ha-test: OK
```

Inspect the current weather data:

```bash
curl http://192.168.178.158:6066/raw
```

Inspect the hourly forecast returned by Home Assistant:

```bash
curl http://192.168.178.158:6066/debug/forecast
```

Finally simulate a Loxone request:

```bash
curl "http://192.168.178.158:6066/forecast/?user=loxone_TEST&coord=10.681,48.56&asl=450&format=2&new_api=1"
```

## DNS test

```bash
nslookup weather.loxone.com
```

It should resolve to the Home Assistant IP.

## Logging

Open the add-on log in Home Assistant. Each request is logged, including the Loxone query parameters, selected weather provider, Home Assistant forecast entity, number of hourly forecast entries and generated response size.

## Important

This is still a compatibility test build, not a production Weather4Lox replacement. Exact Gen-1 response compatibility and the available forecast length of each weather integration need to be verified with the real Miniserver.
