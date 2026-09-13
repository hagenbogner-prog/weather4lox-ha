from pathlib import Path
import re

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


def test_current_release_enables_ingress_without_reusing_loxone_port():
    config = load_config()
    assert config["version"] == "0.6.2"
    assert config["ingress"] is True
    assert config["ingress_port"] == 8099
    assert config["panel_admin"] is True
    assert config["ports"]["6066/tcp"] == 6066
    assert config["panel_title"] == "Weather4Lox"


def test_runtime_version_strings_match_app_version():
    version = load_config()["version"]
    runtime_files = ("server.py", "bootstrap.py", "run.sh")

    for filename in runtime_files:
        content = Path("weather4lox-ha", filename).read_text(encoding="utf-8")
        assert version in content, f"{filename} does not contain app version {version}"

    run_script = Path("weather4lox-ha/run.sh").read_text(encoding="utf-8")
    logged_version = re.search(r"Weather4Lox HA ([0-9.]+) service", run_script)
    assert logged_version and logged_version.group(1) == version


def test_readme_version_matches_app_version():
    version = load_config()["version"]
    readme = Path("README.md").read_text(encoding="utf-8")

    assert f"Current version: **{version}**" in readme


def test_public_defaults_do_not_contain_installation_specific_location():
    config = load_config()
    options = config["options"]
    assert options["location_city"] == "Home"
    assert options["latitude"] == 0.0
    assert options["longitude"] == 0.0
    assert options["elevation_m"] == 0
    assert options["timezone"] == "UTC"


def test_configuration_does_not_offer_unimplemented_options():
    config = load_config()
    configured_keys = set(config["options"]) | set(config["schema"])

    assert "mqtt_entities" not in configured_keys
    assert "mqtt_discovery_prefix" not in configured_keys
    assert "country_code" not in configured_keys
