"""Loxone Gen-1 Weather Service format=2 protocol constants.

The local emulator described by SmartHome.Exposed uses the Weather4Loxone
CSV response: a 29-column metadata header followed by 29-column station
rows. Keep the protocol schema independent from Home Assistant/provider data.
"""

FORMAT2_COLUMNS = 29

FORMAT2_HEADER = (
    "id;name;longitude;latitude;height (m.asl.);country;timezone;"
    "utc-timedifference;sunrise;sunset;local date;weekday;local time;"
    "temperature(C);feeledTemperature(C);windspeed (km/h);"
    "winddirection(degr);wind gust(km/h);low clouds(%);medium clouds(%);"
    "high clouds(%);precipitation(mm);probability of Precip(%);snowFraction;"
    "sea level pressure(hPa);relative humidity(%);CAPE;picto-code;"
    "radiation (W/m2)"
)

# Documented Loxone Gen-1 weather-service codes used by the current
# compatibility layer. Do not mix these with Weather4Lox emulator codes.
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


def validate_row(row):
    """Validate one semicolon-delimited format=2 station row."""
    parts = row.split(";")
    if len(parts) != FORMAT2_COLUMNS:
        return False
    try:
        picto = int(parts[27])
    except (TypeError, ValueError):
        return False
    return picto in VALID_LOXONE_PICTOS


def validate_payload(header, rows):
    """Return a compact validation result for a format=2 payload."""
    row_counts = [len(row.split(";")) for row in rows]
    ok = (
        len(header.split(";")) == FORMAT2_COLUMNS
        and all(count == FORMAT2_COLUMNS for count in row_counts)
        and all(validate_row(row) for row in rows)
    )
    return {
        "ok": ok,
        "header_columns": len(header.split(";")),
        "row_columns_min": min(row_counts) if row_counts else 0,
        "row_columns_max": max(row_counts) if row_counts else 0,
        "rows": len(rows),
        "expected_columns": FORMAT2_COLUMNS,
    }
