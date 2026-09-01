from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "weather4lox-ha"))

from protocol.loxone_gen1 import (
    FORMAT2_COLUMNS,
    FORMAT2_HEADER,
    DEFAULT_LOXONE_PICTO,
    WEATHER_COLUMNS,
    picto_for_condition,
    validate_payload,
    validate_row,
)


def test_format2_header_has_29_columns():
    assert FORMAT2_COLUMNS == 29
    assert len(FORMAT2_HEADER.split(";")) == FORMAT2_COLUMNS


def test_hourly_row_has_19_columns():
    row = ";".join([
        "31.08.2026", "Mon", "18", "23.1", "23.1", "3.7", "225", "0",
        "80", "0", "0", "0.0", "0", "0.0", "1016", "50", "0", "5", "0",
    ])
    assert validate_row(row)
    assert len(row.split(";")) == WEATHER_COLUMNS
    assert row.split(";")[0:3] == ["31.08.2026", "Mon", "18"]


def test_unknown_condition_uses_safe_default_picto():
    assert picto_for_condition("not-a-real-condition") == DEFAULT_LOXONE_PICTO


def test_payload_validator_rejects_wrong_column_count():
    result = validate_payload(FORMAT2_HEADER, ["0;1;2"])
    assert result["ok"] is False
    assert result["row_columns_min"] == 3
