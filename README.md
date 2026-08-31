# Weather4Lox HA

Home Assistant add-on that provides the Loxone Gen 1 Weather Service API on TCP port 6066. It reads weather data from Home Assistant and serves the `format=2` response expected by a Loxone Miniserver.

## Architecture

```text
Loxone Miniserver Gen 1
        |
        | HTTP :6066
        v
Weather4Lox HA add-on
        |
        | Home Assistant Supervisor API
        v
Home Assistant weather entity / sensors
```

The add-on is a native Home Assistant add-on. It does not contain or install a LoxBerry plugin. Historical LoxBerry-only JSON endpoints and runtime files are intentionally not part of the add-on.

## Loxone endpoint

The main service endpoint is:

```text
http://HOME_ASSISTANT_IP:6066/forecast/?user=loxone_TEST&coord=10.681,48.56&asl=450&format=2&new_api=1
```

The `format=2` response follows the documented Local Weather Service structure used by the Loxone Gen 1 client:

- 29 metadata columns
- one 10-column station metadata line
- 19 columns per hourly forecast row
- protocol-safe Loxone weather pictograms
- local date/time and timezone information

The implementation can normalize Home Assistant forecast data to the configured target of 181 hourly values, using interpolation, daily fallback, cache fallback and synthetic fallback where configured.

## Configuration

The default configuration targets:

- `weather.openweathermap`
- the corresponding OpenWeatherMap temperature, feels-like, humidity, pressure, cloud, wind, rain and snow sensors
- location `Wertingen`, Germany
- latitude `48.56`, longitude `10.681`
- timezone `Europe/Berlin`

All entities and fallback behavior can be changed in the add-on configuration.

## Testing

Check that the add-on is reachable:

```bash
curl http://HOME_ASSISTANT_IP:6066/health
```

Check the Loxone-compatible response:

```bash
curl "http://HOME_ASSISTANT_IP:6066/forecast/?user=loxone_TEST&coord=10.681,48.56&asl=450&format=2&new_api=1"
```

Useful diagnostics are available at `/status`, `/raw` and `/debug/loxone/validate`.

## Development

CI compiles the Python sources, validates the add-on configuration, builds the Home Assistant Docker image, runs the test suite and updates the version/forecast information in this README.

The CI deliberately does **not** create ZIP packages. Home Assistant add-on installation is performed from the repository/add-on store or from the add-on source directory.

## License

MIT

<!-- AUTO-GENERATED: ci-docs.yml -->
Current version: **0.4.1**  
Forecast target: **181 hours**  
<!-- END AUTO-GENERATED -->
