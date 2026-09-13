# Changelog

## 0.6.1

### Added

- Neutral dashboard links to the status and manual refresh endpoints, derived from the current Home Assistant host.
- Reproducible SVG master asset for the Weather4Lox app graphics.

### Fixed

- **Check now** now displays a visible success, warning, or error result instead of silently discarding the API response.
- Replaced the damaged `logo.png` with a valid square 256 × 256 RGBA logo that renders consistently in the Home Assistant app header.
- Updated `icon.png` with transparent outer corners while retaining the recommended 128 × 128 dimensions.

## 0.6.0

### Added

- Home Assistant Ingress web interface for Weather4Lox status and diagnostics.
- Dashboard overview for provider, weather entity, forecast coverage, cache state, last successful refresh, Loxone Format 2 validation, and request count.
- **Check now** action to refresh forecast data and validate the generated Loxone response.
- Human-readable configuration hints for missing or unusable forecast data.
- Specific OpenWeatherMap guidance when the selected Home Assistant weather entity does not provide forecast data.
- German and English configuration descriptions for the Home Assistant app UI.
- App-level README, documentation, and changelog files for the Home Assistant Info and Documentation pages.

### Changed

- App description now explains the purpose and major functions of Weather4Lox more clearly.
- New installations use neutral location defaults instead of project-specific example location data.
- The Ingress dashboard deliberately omits location names, coordinates, tokens, and other private configuration values.
- Cached forecasts are only accepted as fallback while the configured cache validity is active and the exact forecast end time is still in the future.
- The diagnostics server only accepts authenticated requests from the Home Assistant Supervisor Ingress proxy at `172.30.32.2`; its sidebar entry is explicitly administrator-only.
- Weather4Lox version updated to 0.6.0.

### Fixed

- Improved diagnostics for the case where Home Assistant current weather data exists but the selected weather entity cannot provide `weather.get_forecasts` data.
- Prevented expired forecast data from being presented as a usable Loxone fallback.
- Prevented forecasts that ended earlier on the current day from being treated as current.
- Prepared the app icon asset for correct square rendering in the Home Assistant app UI.

### Known provider behavior

- OpenWeatherMap `current` mode provides current conditions only and is not sufficient for Weather4Lox forecast output. Use a forecast-capable OpenWeatherMap mode such as `forecast` or `v3.0`.

## 0.5.0

- Added provider-specific DWD/OpenWeatherMap configuration.
- Added automatic weather entity detection with manual overrides.
- Added provider-specific refresh and cache policies.
- Added 1–7 day requested forecast horizon.
- Added atomic cache replacement and fallback behavior.
- Added Loxone Format 2 validation and diagnostic endpoints.
- Removed synthetic forecast generation from normal operation.
