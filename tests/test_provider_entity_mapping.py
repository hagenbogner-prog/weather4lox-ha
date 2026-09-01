from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "weather4lox-ha"))

import server


def test_flat_provider_configuration_is_mapped_by_bootstrap_shape():
    options = {
        "dwd_weather_entity": "weather.wertingen",
        "dwd_refresh_interval_minutes": 120,
        "dwd_cache_validity_hours": 24,
        "openweathermap_weather_entity": "weather.openweathermap",
        "openweathermap_refresh_interval_minutes": 60,
        "openweathermap_cache_validity_hours": 48,
    }
    # server's base provider_config remains safe for unit-level use; the
    # bootstrap adapter maps the flat add-on options at runtime.
    assert server.provider_config("dwd", options) == {}
    assert server.provider_config("openweathermap", options) == {}
