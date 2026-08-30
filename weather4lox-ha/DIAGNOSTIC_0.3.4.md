# Weather4Lox HA 0.3.4

Diagnostic build for isolating Loxone Gen-1 Weather Service compatibility.

Endpoints:
- `/debug/loxone/minimal` — deterministic 181-hour, 29-column Weather4Lox format-2 response independent of DWD/OWM.
- `/debug/loxone/validate` — validates metadata, station, row/column counts, timestamps, numeric fields, picto codes and complete response termination.
- `/debug/loxone/reference` — compact diagnostic summary of the generated Loxone payload.
