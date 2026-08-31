from datetime import datetime, timezone

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "weather4lox-ha"))
import live_data


def test_condition_mapping_uses_documented_loxone_codes():
    assert live_data._condition("sunny")[3] == 1
    assert live_data._condition("cloudy")[3] == 5
    assert live_data._condition("rainy")[3] == 11
    assert live_data._condition("snowy")[3] == 21
    assert 1 <= live_data._condition("unknown")[3] <= 29


def test_moon_values_are_in_schema_ranges():
    moon = live_data._moon(datetime(2026, 8, 31, tzinfo=timezone.utc))
    assert 0 <= moon["age"] <= 29.6
    assert 0 <= moon["percent"] <= 100
    assert 0 <= moon["phase"] <= 100
    assert moon["direction"] in {"waxing", "waning"}


def test_hourly_item_contains_v4_fields():
    item = live_data._hourly_item(
        {
            "datetime": "2026-08-31T06:00:00+02:00",
            "condition": "cloudy",
            "cloud_coverage": 80,
            "humidity": 60,
            "temperature": 20,
            "apparent_temperature": 20,
            "pressure": 1015,
            "precipitation": 0,
            "precipitation_probability": 10,
            "wind_speed": 5,
            "wind_gust_speed": 8,
            "wind_bearing": 225,
        },
        0,
    )
    assert item["hour"] == 0
    assert item["weatherCode"]["loxone"] == 5
    assert item["wind"]["cardinal"] == "SW"
    assert item["time"]["datetime"].endswith("+02:00")


def test_daily_fallback_groups_hourly_data():
    hourly = [
        {
            "datetime": "2026-08-31T10:00:00+02:00",
            "condition": "sunny",
            "temperature": 25,
            "humidity": 50,
            "cloud_coverage": 10,
            "pressure": 1015,
            "wind_speed": 4,
            "wind_gust_speed": 7,
            "wind_bearing": 180,
            "precipitation": 0,
            "precipitation_probability": 0,
        },
        {
            "datetime": "2026-08-31T14:00:00+02:00",
            "condition": "cloudy",
            "temperature": 29,
            "humidity": 60,
            "cloud_coverage": 80,
            "pressure": 1014,
            "wind_speed": 5,
            "wind_gust_speed": 8,
            "wind_bearing": 225,
            "precipitation": 1,
            "precipitation_probability": 70,
        },
    ]
    daily = live_data._daily_from_hourly(hourly)
    assert len(daily) == 1
    assert daily[0]["temperature"]["min"]["air"] == 25
    assert daily[0]["temperature"]["max"]["air"] == 29
    assert daily[0]["precipitation"]["probability"] == 70
