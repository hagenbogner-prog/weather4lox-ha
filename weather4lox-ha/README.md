# Weather4Lox HA

Weather4Lox HA provides weather forecasts from Home Assistant to a Loxone Miniserver Gen 1 using the Loxone Weather Service format.

The app reads a supported Home Assistant `weather.*` entity, stores a provider-specific forecast cache, validates the generated Loxone Format 2 payload, and serves it locally on TCP port `6066`.

## Highlights

- OpenWeatherMap and DWD support
- Automatic or manual weather entity selection
- Provider-specific refresh intervals and cache validity
- Loxone Weather Service Format 2 output
- Integrated status and diagnostics web interface via Home Assistant Ingress
- Clear configuration hints when no usable forecast is available
- Manual forecast check from the web interface
- No synthetic forecast data during normal operation

## Status and diagnostics

After starting the app, open **Web UI** on the app Info page. The status page shows:

- overall Weather4Lox status
- selected weather provider
- selected Home Assistant weather entity
- forecast entry count and range
- cache state and age
- last successful refresh
- Loxone Format 2 validation state
- number of Loxone requests since startup
- actionable configuration errors

The diagnostics page intentionally does not display configured coordinates, location names, tokens, or other private configuration values.

## OpenWeatherMap note

Weather4Lox requires an OpenWeatherMap mode that provides forecast data. Modes such as `forecast` or `v3.0` can provide forecast data, while `current` provides current conditions only and is therefore not sufficient for Weather4Lox forecasting.

See the **Documentation** tab for setup and troubleshooting details.
