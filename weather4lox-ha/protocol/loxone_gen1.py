"""Loxone Gen 1 Weather Service format=2 protocol constants."""

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

# Weather4Loxone / SmartHome.Exposed format-2 examples use these stable codes.
LOXONE_PICTOS = {
    "sunny": 1,
    "clear-night": 2,
    "partlycloudy": 14,
    "cloudy": 22,
    "fog": 22,
    "rainy": 23,
    "pouring": 23,
    "snowy": 24,
    "snowy-rainy": 24,
    "lightning": 23,
    "lightning-rainy": 23,
    "hail": 23,
    "windy": 22,
    "windy-variant": 22,
    "exceptional": 22,
    "unknown": 22,
}

VALID_LOXONE_PICTOS = set(range(1, 36))
DEFAULT_LOXONE_PICTO = 22


def picto_for_condition(condition):
    """Map a Home Assistant condition to a protocol-safe Loxone code."""
    return LOXONE_PICTOS.get(str(condition or "unknown").lower(), DEFAULT_LOXONE_PICTO)


def _split_fields(value):
    return value[:-1].split(";") if value.endswith(";") else value.split(";")


def validate_row(row):
    parts = _split_fields(row)
    if len(parts) != WEATHER_COLUMNS:
        return False
    try:
        picto = int(parts[17])
    except (TypeError, ValueError):
        return False
    return picto in VALID_LOXONE_PICTOS


def validate_payload(header, station_or_rows, rows=None):
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
