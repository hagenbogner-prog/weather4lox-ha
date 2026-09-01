# Implementation plan

1. Provider selection is exclusive: DWD or OpenWeatherMap.
2. Auto-discover matching `weather.*` entities, with explicit entity override.
3. Use provider-specific refresh and cache policies.
4. Request only forecast types supported by the selected HA weather entity and preserve actual coverage/resolution.
5. Remove normal-operation synthetic forecast generation.
6. Keep the last successful cache after refresh failures.
7. Publish normalized values to Loxone Format 2 on port 6066.
8. Optionally publish HA sensors using MQTT discovery when MQTT is available.
9. Expose cache/refresh diagnostics and manual refresh/clear operations.
