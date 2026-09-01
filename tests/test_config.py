from pathlib import Path
import yaml


def test_app_configuration_uses_exactly_one_supported_provider_choice():
    config = yaml.safe_load(Path("weather4lox-ha/config.yaml").read_text(encoding="utf-8"))
    assert config["schema"]["weather_provider"] == "list(openweathermap|dwd)"
    assert set(config["options"]) >= {"weather_provider", "dwd", "openweathermap", "forecast_days"}
    assert config["options"]["forecast_days"] == 7
