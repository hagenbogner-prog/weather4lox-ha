# Protocol test notes

The first LAN test confirms that the add-on is reachable and can read the OpenWeatherMap entity from Home Assistant.

The response currently returned by `/forecast/` is intentionally a minimal diagnostic response. It is **not yet considered production-compatible** with the Loxone Gen-1 Weather Service.

Before the Miniserver is connected, the implementation must be corrected to:

1. emit longitude and latitude as separate CSV columns;
2. provide the expected station metadata layout;
3. obtain hourly forecast data through Home Assistant's `weather.get_forecasts` service;
4. emit approximately seven days of hourly station records;
5. use the documented Loxone/Meteoblue pictogram mapping rather than the current simplified mapping;
6. set `valid_until` to a future date rather than the current date.

The documented Gen-1 service uses TCP port 6066 and `/forecast`, with `coord=<longitude>,<latitude>` and `asl=<elevation>` supplied by the Miniserver. The CSV/XML response contains a header followed by hourly station records and is normally about seven days long.
