"""Unit tests for soil analysis, finance formulas, weather alerts and market parsing (external calls mocked)."""
import httpx
import pytest

from app.services import finance, soil, weather
from app.services import market


# ---------- soil ----------

def test_soil_bands_and_overall_rating():
    result = soil.analyze(nitrogen=200, phosphorus=30, potassium=150, ph=5.9, organic_carbon=0.4)
    ratings = {n["name"]: n["rating"] for n in result["nutrients"]}
    assert ratings == {"nitrogen": "low", "phosphorus": "high", "potassium": "medium"}
    assert result["ph"]["rating"] == "acidic"
    assert result["organic_carbon"]["rating"] == "low"
    assert result["overall"] == "Poor"          # nitrogen low + acidic pH + low organic carbon = 3 concerns


def test_soil_good_fertility():
    result = soil.analyze(nitrogen=400, phosphorus=15, potassium=200, ph=7.0, organic_carbon=0.9)
    assert result["overall"] == "Good"
    assert all(n["rating"] in ("medium", "high") for n in result["nutrients"])


@pytest.mark.parametrize("value,expected", [(279.9, "low"), (280, "medium"), (560, "medium"), (560.1, "high")])
def test_nitrogen_boundaries(value, expected):
    assert soil.analyze(value, 15, 200, 7, 0.9)["nutrients"][0]["rating"] == expected


# ---------- finance ----------

def test_emi_matches_standard_example():
    # Rs 1,00,000 at 12% a year for 1 year is the well-known EMI of 8,884.88.
    assert round(finance.emi(100000, 12, 1), 2) == 8884.88


def test_emi_zero_rate_is_principal_over_months():
    assert finance.emi(120000, 0, 2) == pytest.approx(5000)


def test_crop_economics_hand_checked():
    # 2 acres x 20 quintal/acre x Rs 2,000 = Rs 80,000 revenue.
    # Costs per acre: seed 3,000 + labour 5,000 = 8,000, so total cost is 16,000 for 2 acres.
    result = finance.crop_economics(2, 20, 2000, {"seed": 3000, "labour": 5000})
    assert result["gross_revenue"] == 80000
    assert result["total_cost"] == 16000
    assert result["profit"] == 64000
    assert result["roi_pct"] == 400.0
    assert result["break_even_price_per_quintal"] == 400.0      # 16,000 / 40 quintal
    assert result["break_even_yield_per_acre"] == 4.0          # 8,000 per acre / Rs 2,000 per quintal


def test_crop_economics_loan_and_lease():
    result = finance.crop_economics(1, 10, 1000, {"seed": 1000}, lease_per_acre=2000,
                                    loan_amount=100000, loan_rate_pct=12, loan_years=1)
    assert result["total_cost"] == 3000
    assert result["loan"]["monthly_emi"] == pytest.approx(8884.88, abs=0.01)
    assert result["loan"]["profit_covers_annual_emi"] is False


def test_crop_economics_rejects_negative_inputs():
    with pytest.raises(ValueError):
        finance.crop_economics(0, 10, 1000, {})
    with pytest.raises(ValueError):
        finance.crop_economics(1, 10, 1000, {"seed": -5})


# ---------- weather ----------

def test_weather_alerts_for_rain_heat_and_cold():
    days = [
        {"date": "d1", "rain_mm": 9, "tmax": 39, "tmin": 22},
        {"date": "d2", "rain_mm": 8, "tmax": 33, "tmin": 4},
        {"date": "d3", "rain_mm": 6, "tmax": 30, "tmin": 12},
    ]
    kinds = {a["kind"] for a in weather.build_alerts(days)}
    assert kinds == {"heavy_rain", "heat", "cold"}


def test_no_alerts_for_mild_weather():
    days = [{"date": f"d{i}", "rain_mm": 1, "tmax": 29, "tmin": 15} for i in range(7)]
    assert weather.build_alerts(days) == []


def test_parse_days_handles_missing_values():
    data = {"daily": {"time": ["2026-11-25"], "precipitation_sum": [None],
                      "temperature_2m_max": [31.5], "temperature_2m_min": [18.0]}}
    assert weather.parse_days(data) == [{"date": "2026-11-25", "rain_mm": 0.0, "tmax": 31.5, "tmin": 18.0}]


def test_fetch_forecast_reports_network_failure(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(weather.httpx, "get", boom)
    with pytest.raises(weather.WeatherError, match="could not be reached"):
        weather.fetch_forecast(12.97, 77.59, "https://example.invalid")


def test_fetch_forecast_parses_success(monkeypatch):
    class Resp:
        status_code = 200
        def json(self):
            return {"current": {"temperature_2m": 26.1}, "daily": {"time": []}}
    monkeypatch.setattr(weather.httpx, "get", lambda *a, **k: Resp())
    assert weather.fetch_forecast(12.97, 77.59, "https://x")["current"]["temperature_2m"] == 26.1


# ---------- market ----------

def test_market_parsing_skips_bad_rows(monkeypatch):
    payload = {"records": [
        {"market": "Kolar", "state": "Karnataka", "arrival_date": "25/11/2026",
         "min_price": "1,200", "max_price": "1,600", "modal_price": "1,400"},
        {"market": "Broken", "state": "X", "arrival_date": "25/11/2026", "min_price": "", "max_price": "", "modal_price": "n/a"},
    ]}
    class Resp:
        status_code = 200
        def json(self):
            return payload
    monkeypatch.setattr(market.httpx, "get", lambda *a, **k: Resp())
    rows = market.fetch_prices("Tomato", "KEY", "RES")
    assert len(rows) == 1 and rows[0]["modal"] == 1400.0 and rows[0]["min"] == 1200.0
    assert market.summarize(rows) == {"markets": 1, "avg_modal": 1400.0, "min_modal": 1400.0, "max_modal": 1400.0}


def test_market_rejected_key_message(monkeypatch):
    class Resp:
        status_code = 403
    monkeypatch.setattr(market.httpx, "get", lambda *a, **k: Resp())
    with pytest.raises(market.MarketError, match="rejected the API key"):
        market.fetch_prices("Tomato", "BAD", "RES")
