from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "weather4lox-ha"))
import bootstrap

json_compat = bootstrap.json_compat
live_data = bootstrap.live_data


def test_hourly_item_matches_v4_field_names():
    item = json_compat.hourly_item(
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
    assert item["weatherCode"]["loxone"] == "5"
    assert item["wind"]["dirLabel"] == "SW"
    assert "cardinal" not in item["wind"]
    assert set(item["precipitation"]) == {
        "duration", "probability", "rainHigh", "rainLow", "snowHigh", "snowLow", "type"
    }


def test_daily_fallback_has_v4_nested_shape():
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

    daily = json_compat.daily_from_hourly(hourly)
    assert len(daily) == 1
    assert daily[0]["temperature"]["min"]["air"] == 25
    assert daily[0]["temperature"]["max"]["air"] == 29
    assert set(daily[0]["humidity"]) == {"avg", "max", "min"}
    assert set(daily[0]["wind"]) == {"avg", "max"}
    assert set(daily[0]["wind"]["avg"]) == {"dirLabel", "direction", "gust", "speed"}


def test_current_envelope_uses_provider_metadata_key(tmp_path, monkeypatch):
    monkeypatch.setattr(live_data, "CURRENT_FILE", tmp_path / "current.json")
    monkeypatch.setattr(live_data, "HOURLY_FILE", tmp_path / "hourlyforecast.json")
    monkeypatch.setattr(live_data, "DAILY_FILE", tmp_path / "dailyforecast.json")
    monkeypatch.setattr(live_data, "_current", lambda: {
        "current": {
            "temperature": {"air": 23.1, "feelsLike": 23.1},
            "weatherCode": {"loxone": 5},
        }
    })
    monkeypatch.setattr(live_data, "_location", lambda: {"city": "Wertingen"})
    monkeypatch.setattr(live_data, "_generated_at", lambda: "2026-08-31T18:35:00+02:00")
    monkeypatch.setattr(live_data, "JSON_REFRESH_CURRENT", 300)
    monkeypatch.setattr(live_data, "JSON_REFRESH_FORECAST", 1800)
    monkeypatch.setattr(bootstrap.server_035, "opts", lambda: {"weather_provider": "dwd"})
    monkeypatch.setattr(bootstrap.server_035, "selected_entity", lambda: "weather.wertingen")
    monkeypatch.setattr(bootstrap.server_035, "obtain_forecast", lambda force=False: ([], "cache", 0))
    monkeypatch.setattr(bootstrap.server_035, "service_forecast", lambda entity, kind: [])

    json_compat.refresh(force=True)
    payload = (tmp_path / "current.json").read_text(encoding="utf-8")
    assert '"dwd"' in payload
    assert '"current"' in payload
    assert '"location"' in payload
