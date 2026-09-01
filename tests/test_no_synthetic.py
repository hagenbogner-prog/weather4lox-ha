from pathlib import Path


def test_server_no_longer_contains_synthetic_forecast_function():
    source = Path("weather4lox-ha/server.py").read_text(encoding="utf-8")
    assert "def synthetic(" not in source
    assert "synthetic_fallback" not in source
