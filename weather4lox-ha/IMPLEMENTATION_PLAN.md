# Implementation plan

1. Provider selection is exclusive: DWD or OpenWeatherMap.
2. Auto-discover matching `weather.*` entities, with an explicit entity override.
3. Use provider-specific refresh and cache policies.
4. Fetch real forecast data through Home Assistant and preserve its actual coverage/resolution.
5. Never generate synthetic weather values during normal operation.
6. Replace the cache atomically after a successful refresh; preserve the last successful cache after a failure.
7. Serialize the cached normalized data as Loxone Gen 1 Weather4Loxone format=2 on TCP 6066.
8. Optionally publish normalized values to Home Assistant through MQTT Discovery.
9. Expose cache status, refresh/clear controls, and diagnostics.
