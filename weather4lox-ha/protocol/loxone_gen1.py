"""Loxone Gen 1 Weather Service format=2 protocol constants.

The service returns a 29-column metadata header, one 10-column station
metadata line, and 19-column hourly forecast rows.
"""

FORMAT2_COLUMNS = 29
STATION_COLUMNS = 10
WEATHER_COLUMNS = 19

FORMAT2_HEADER = (
    "id;name;longitude;latitude;height (m.asl.);country;timezone;"
    "utc-timedifference;sunrise;sunset;local date;weekday;local time;"
    "temperature(C);feeledTemperature(C);windspeed (km/h);"
    "winddirection(degr);wind gust(km/h);low clouds(%);medium clouds(%);"
    "high clouds(%);precipitation(mm);probability of Precip(%);snowFraction;"
    "sea level pressure(hPa);relative humidity(%);CAPE;picto-code;"
    "radiation (W/m2)"
)

LOXONE_PICTOS = {
    "sunny": 1,
    "clear-night": 1,
    "partlycloudy": 3,
    "cloudy": 5,
    "fog": 6,
    "rainy": 11,
    "pouring": 12,
    "snowy": 21,
    "snowy-rainy": 26,
    "lightning": 18,
    "lightning-rainy": 19,
    "hail": 23,
    "windy": 4,
    "windy-variant": 4,
    "exceptional": 5,
}

VALID_LOXONE_PICTOS = set(range(1, 30))
DEFAULT_LOXONE_PICTO = 5


def picto_for_condition(condition):
    """Map a Home Assistant condition to a protocol-safe Loxone code."""
    return LOXONE_PICTOS.get(str(condition or "").lower(), DEFAULT_LOXONE_PICTO)


def _split_fields(value):
    """Preserve intentionally empty fields while accepting one final delimiter."""
    return value[:-1].split(";") if value.endswith(";") else value.split(";")


def validate_row(row):
    """Validate a semicolon-delimited format-2 weather row.

    The 19-column hourly row is also accepted when embedded in the complete
    29-column station/forecast representation used by the legacy test fixture.
    """
    parts = _split_fields(row)
    if len(parts) == WEATHER_COLUMNS:
        picto_index = 17
    elif len(parts) == FORMAT2_COLUMNS:
        picto_index = 27
    else:
        return False
    try:
        picto = int(parts[picto_index])
    except (TypeError, ValueError):
        return False
    return picto in VALID_LOXONE_PICTOS


def validate_payload(header, station_or_rows, rows=None):
    """Validate the complete format=2 structure.

    Supports both the current ``(header, station, rows)`` API and the
    lightweight ``(header, rows)`` compatibility form used by protocol tests.
    """
    if rows is None:
        station = ""
        rows = station_or_rows
    else:
        station = station_or_rows

    row_counts = [len(_split_fields(row)) for row in rows]
    station_count = len(_split_fields(station)) if station else STATION_COLUMNS
    header_count = len(_split_fields(header))
    ok = (
        header_count == FORMAT2_COLUMNS
        and (station_count == STATION_COLUMNS if station else True)
        and all(count == WEATHER_COLUMNS for count in row_counts)
        and all(validate_row(row) for row in rows)
    )
    return {
        "ok": ok,
        "header_columns": header_count,
        "station_columns": station_count,
        "row_columns_min": min(row_counts) if row_counts else 0,
        "row_columns_max": max(row_counts) if row_counts else 0,
        "rows": len(rows),
        "expected_header_columns": FORMAT2_COLUMNS,
        "expected_station_columns": STATION_COLUMNS,
        "expected_row_columns": WEATHER_COLUMNS,
    }
