import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "weather4lox-ha"))
import bootstrap

core = bootstrap.server_035


def test_format2_uses_station_metadata_plus_19_weather_columns(monkeypatch):
    monkeypatch.setattr(
        core,
        "opts",
        lambda: {
            "location_city": "Wertingen",
            "country": "Deutschland",
            "longitude": 10.681,
            "latitude": 48.56,
            "elevation_m": 450,
            "timezone": "Europe/Berlin",
        },
    )

    forecast = [
        {
            "datetime": "2026-08-31T18:00:00+02:00",
            "temperature": 23.1,
            "apparent_temperature": 23.1,
            "humidity": 50,
            "pressure": 1016,
            "wind_speed": 3.7,
            "wind_gust_speed": 0,
            "wind_bearing": 225,
            "cloud_coverage": 100,
            "precipitation": 0,
            "precipitation_probability": 0,
            "condition": "cloudy",
        }
    ]

    payload, validation = core.make_payload(forecast, {"coord": ["10.681,48.56"], "asl": ["450"]}, diagnostic=True)

    assert validation["ok"] is True
    assert validation["header_columns"] == 29
    assert validation["station_columns"] == 10
    assert validation["row_columns_min"] == 19
    assert validation["row_columns_max"] == 19

    station_block = payload.split("<station>\n", 1)[1].split("\n</station>", 1)[0]
    lines = station_block.splitlines()
    assert len(lines[0].rstrip(";").split(";")) == 10
    assert len(lines[1].rstrip(";").split(";")) == 19
    assert lines[1].split(";")[0] == "31.08.2026"
    assert lines[1].split(";")[1] == "Mon"
    assert lines[1].split(";")[2] == "18"
    assert lines[1].split(";")[17] == "1"


def test_format2_metadata_has_29_named_fields():
    header = core.metadata()
    fields = header.split(";")
    assert len(fields) == 29
    assert fields[0] == "id"
    assert fields[1] == "name"
    assert fields[13] == "temperature(C)"
    assert fields[27] == "picto-code"
    assert fields[28] == "radiation (W/m2)"
