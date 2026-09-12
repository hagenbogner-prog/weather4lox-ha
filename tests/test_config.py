from pathlib import Path
import yaml


def load_config():
    return yaml.safe_load(Path("weather4lox-ha/config.yaml").read_text(encoding="utf-8"))


def test_app_configuration_uses_exactly_one_supported_provider_choice():
    config = load_config()
    assert config["schema"]["weather_provider"] == "list(openweathermap|dwd)"
    options = config["options"]
    assert {"weather_provider", "dwd_weather_entity", "openweathermap_weather_entity", "forecast_days"} <= set(options)
    assert options["forecast_days"] == 7
    assert options["dwd_refresh_interval_minutes"] == 120
    assert options["openweathermap_refresh_interval_minutes"] == 60


def test_060_enables_ingress_without_reusing_loxone_port():
    config = load_config()
    assert config["version"] == "0.6.0"
    assert config["ingress"] is True
    assert config["ingress_port"] == 8099
    assert config["ports"]["6066/tcp"] == 6066
    assert config["panel_title"] == "Weather4Lox"


def test_public_defaults_do_not_contain_installation_specific_location():
    config = load_config()
    options = config["options"]
    assert options["location_city"] == "Home"
    assert options["latitude"] == 0.0
    assert options["longitude"] == 0.0
    assert options["elevation_m"] == 0
    assert options["timezone"] == "UTC"
