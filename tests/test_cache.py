import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "weather4lox-ha"))

import server


def cache_with_end(value):
    return {
        "forecast_end": value.isoformat(),
        "forecast": [{"datetime": value.isoformat()}],
    }


def test_forecast_must_end_strictly_after_current_instant():
    now = datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc)

    assert not server.cache_has_current_forecast(cache_with_end(now), now=now)
    assert not server.cache_has_current_forecast(
        cache_with_end(now - timedelta(microseconds=1)),
        now=now,
    )
    assert server.cache_has_current_forecast(
        cache_with_end(now + timedelta(microseconds=1)),
        now=now,
    )


def test_same_day_forecast_that_ended_hours_ago_is_expired():
    now = datetime(2026, 9, 13, 22, 0, tzinfo=timezone.utc)
    ended_at = datetime(2026, 9, 13, 3, 0, tzinfo=timezone.utc)

    assert not server.cache_has_current_forecast(cache_with_end(ended_at), now=now)


def test_forecast_end_comparison_normalizes_timezone_offsets():
    now = datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc)
    same_instant = datetime(2026, 9, 13, 22, 0, tzinfo=timezone(timedelta(hours=2)))
    later = same_instant + timedelta(minutes=1)

    assert not server.cache_has_current_forecast(cache_with_end(same_instant), now=now)
    assert server.cache_has_current_forecast(cache_with_end(later), now=now)


def test_forecast_rows_are_used_when_cached_end_is_missing():
    now = datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc)
    cache = {
        "forecast": [
            {"datetime": (now - timedelta(hours=1)).isoformat()},
            {"datetime": (now + timedelta(hours=1)).isoformat()},
        ]
    }

    assert server.cache_has_current_forecast(cache, now=now)
