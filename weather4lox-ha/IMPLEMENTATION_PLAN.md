# Weather4Lox HA implementation plan

## Core rules

1. Provider selection is exclusive: DWD or OpenWeatherMap.
2. Auto-discover matching `weather.*` entities, with an explicit entity override.
3. Use provider-specific refresh and cache policies.
4. Fetch real forecast data through Home Assistant and preserve its actual coverage/resolution.
5. Never generate synthetic weather values during normal operation.
6. Replace the cache atomically after a successful refresh.
7. Preserve the last successful cache after a failure, but only serve it while it is still valid and its forecast still covers the current date.
8. Serialize cached normalized data as Loxone Gen 1 Weather Service Format 2 on TCP 6066.
9. Keep optional MQTT Discovery independent from Loxone operation.

## Version 0.6.0

1. Add a Home Assistant Ingress status and diagnostics interface on internal port 8099.
2. Keep the existing Loxone endpoint on TCP 6066 unchanged and independent from the Web UI.
3. Show provider, selected weather entity, forecast coverage, cache health, refresh state, Format 2 validation and request count.
4. Add a manual **Check now** action that refreshes live forecast data and validates the generated Loxone payload.
5. Translate common provider failures into actionable configuration messages, including the OpenWeatherMap case where current weather exists but no forecast is available.
6. Reject expired forecast data as a valid Loxone fallback.
7. Add app Info, Documentation and Changelog content plus German/English configuration descriptions.
8. Replace installation-specific public defaults and examples with neutral placeholders.
9. Keep location names, coordinates, tokens and other private installation data out of the diagnostics interface and public documentation.
10. Add CI/tests that prevent known installation-specific values from being reintroduced.
11. Use a square 128×128 app icon suitable for the Home Assistant app card.

## Release process

- Develop 0.6.0 on a feature branch.
- Run Python compilation, unit tests, configuration checks, privacy checks and app-image builds in CI.
- Review the pull request before changing `main`.
- Merge only after the release candidate passes CI and has been reviewed.
