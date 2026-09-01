from pathlib import Path
import yaml


def test_app_configuration_uses_exactly_one_supported_provider_choice():
    config = yaml.safe_load(Path("weather4lox-ha/config.yaml").read_text(encoding="utf-8"))
    assert config["schema"]["weather_provider"] == "list(openweathermap|dwd)"
    options = config["options"]
    assert {"weather_provider", "dwd_weather_entity", "openweathermap_weather_entity", "forecast_days"} <= set(options)
    assert options["forecast_days"] == 7
    assert options["dwd_refresh_interval_minutes"] == 120
    assert options["openweathermap_refresh_interval_minutes"] == 60
