from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "weather4lox-ha"))

import loxone_format2


class Core:
    DIAGNOSTIC_PICTO = 1
    VALID_PICTOS = set(range(1, 30))

    @staticmethod
    def fmt(value, digits=2, default="0"):
        if value is None:
            return default
        return str(int(round(float(value)))) if digits == 0 else f"{float(value):.{digits}f}"

    @staticmethod
    def safe_float(value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def clamp(value, low, high):
        return max(low, min(high, value))

    @staticmethod
    def local_dt(value):
        from datetime import datetime
        return datetime.fromisoformat(value)

    @staticmethod
    def picto(item):
        return 22

    @staticmethod
    def snapshot():
        return {}

    @staticmethod
    def opts():
        return {
            "location_city": "Wertingen",
            "country": "Deutschland",
            "longitude": 10.681,
            "latitude": 48.56,
            "elevation_m": 450,
            "timezone": "Europe/Berlin",
        }


def test_format2_has_29_header_10_station_and_19_hourly_columns():
    forecast = [{
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
    }]
    payload, validation = loxone_format2.make_payload(
        Core(), forecast, {"coord": ["10.681,48.56"], "asl": ["450"]}, diagnostic=True
    )

    assert validation["ok"] is True
    assert validation["header_columns"] == 29
    assert validation["station_columns"] == 10
    assert validation["row_columns_min"] == 19
    assert validation["row_columns_max"] == 19

    station_block = payload.split("<station>\n", 1)[1].split("\n</station>", 1)[0]
    lines = station_block.splitlines()
    # The payload terminates the station metadata line with one delimiter;
    # keep the two intentional empty sunrise/sunset fields when counting.
    assert len(lines[0].split(";")[:-1]) == 10
    assert len(lines[1].rstrip(";").split(";")) == 19
    assert lines[1].split(";")[0] == "31.08.2026"
    assert lines[1].split(";")[1] == "Mon"
    assert lines[1].split(";")[2] == "18"
    assert lines[1].split(";")[17] == "1"


def test_metadata_matches_documented_field_order():
    fields = loxone_format2.metadata().split(";")
    assert len(fields) == 29
    assert fields[0] == "id"
    assert fields[13] == "temperature(C)"
    assert fields[27] == "picto-code"
    assert fields[28] == "radiation (W/m2)"
