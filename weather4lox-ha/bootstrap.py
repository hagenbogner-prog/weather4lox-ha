#!/usr/bin/env python3
"""Prepare the 0.3.5 compatibility module for the live JSON layer."""

import server_035

# server_035 imports the proven implementation as ``core`` but intentionally
# does not re-export every helper. The JSON layer uses these helpers directly.
for name in (
    "opts",
    "parse_dt",
    "get_state",
    "selected_entity",
    "service_forecast",
    "snapshot",
    "log",
):
    setattr(server_035, name, getattr(server_035.core, name))

import live_data

if __name__ == "__main__":
    live_data.main()
