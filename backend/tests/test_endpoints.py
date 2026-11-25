"""End-to-end API checks for each farmer workflow. External services (weather, market) are mocked."""
import dataclasses

import pytest

from app import main as main_module
from app.services import weather
from conftest import PLANTVILLAGE


def test_crop_endpoint(client, auth_headers):
    r = client.post("/api/crops/recommend", headers=auth_headers, json={
        "N": 90, "P": 42, "K": 43, "temperature": 23, "humidity": 82, "ph": 6.5, "rainfall": 220})
    assert r.status_code == 200
    assert r.json()["top_crop"] == "rice"


def test_crop_endpoint_validates_ranges(client, auth_headers):
    r = client.post("/api/crops/recommend", headers=auth_headers, json={
        "N": 90, "P": 42, "K": 43, "temperature": 23, "humidity": 120, "ph": 6.5, "rainfall": 220})
    assert r.status_code == 422


def test_soil_endpoint(client, auth_headers):
    r = client.post("/api/soil/analyze", headers=auth_headers, json={
        "nitrogen": 400, "phosphorus": 15, "potassium": 200, "ph": 7.0, "organic_carbon": 0.9})
    assert r.status_code == 200 and r.json()["overall"] == "Good"


def test_finance_endpoint_matches_hand_calculation(client, auth_headers):
    r = client.post("/api/finance/calculate", headers=auth_headers, json={
        "area_acres": 2, "yield_per_acre": 20, "price_per_quintal": 2000,
        "seed_cost": 3000, "labour_cost": 5000})
    body = r.json()
    assert r.status_code == 200
    assert body["gross_revenue"] == 80000 and body["total_cost"] == 16000 and body["profit"] == 64000


def test_finance_endpoint_rejects_zero_area(client, auth_headers):
    r = client.post("/api/finance/calculate", headers=auth_headers, json={
        "area_acres": 0, "yield_per_acre": 20, "price_per_quintal": 2000})
    assert r.status_code == 422


@pytest.mark.skipif(not PLANTVILLAGE.exists(), reason="PlantVillage images not available on this machine")
def test_disease_upload_endpoint_with_real_photo(client, auth_headers):
    image = sorted((PLANTVILLAGE / "Potato___Early_blight").iterdir())[0]
    with open(image, "rb") as fh:
        r = client.post("/api/disease/predict", headers=auth_headers,
                        files={"file": (image.name, fh, "image/jpeg")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["predictions"]) == 3
    assert body["predictions"][0]["crop"] == "Potato"
    assert body["model_test_accuracy"] is not None
    assert "not a diagnosis" in body["disclaimer"]


def test_disease_upload_rejects_non_image(client, auth_headers):
    r = client.post("/api/disease/predict", headers=auth_headers,
                    files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_disease_upload_rejects_corrupt_image(client, auth_headers):
    r = client.post("/api/disease/predict", headers=auth_headers,
                    files={"file": ("leaf.jpg", b"not really a jpeg", "image/jpeg")})
    assert r.status_code == 400


def test_weather_endpoint_creates_alert_notifications(client, auth_headers, monkeypatch):
    raw = {
        "current": {"temperature_2m": 27.5},
        "daily": {
            "time": ["2026-11-25", "2026-11-26", "2026-11-27"],
            "precipitation_sum": [12, 10, 4],
            "temperature_2m_max": [30, 31, 29],
            "temperature_2m_min": [18, 17, 16],
        },
    }
    monkeypatch.setattr(weather, "fetch_forecast", lambda *a, **k: raw)
    r = client.get("/api/weather?lat=12.97&lon=77.59", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["current"]["temperature_2m"] == 27.5
    assert [a["kind"] for a in body["alerts"]] == ["heavy_rain"]
    notes = client.get("/api/notifications", headers=auth_headers).json()
    assert any(n["kind"] == "heavy_rain" for n in notes["items"])
    # the same alert is not duplicated while unread
    client.get("/api/weather?lat=12.97&lon=77.59", headers=auth_headers)
    again = client.get("/api/notifications", headers=auth_headers).json()
    assert sum(1 for n in again["items"] if n["kind"] == "heavy_rain") == 1


def test_weather_endpoint_reports_service_outage(client, auth_headers, monkeypatch):
    def down(*a, **k):
        raise weather.WeatherError("The weather service could not be reached.")
    monkeypatch.setattr(weather, "fetch_forecast", down)
    r = client.get("/api/weather?lat=12.97&lon=77.59", headers=auth_headers)
    assert r.status_code == 502 and "could not be reached" in r.json()["detail"]


def test_weather_rejects_bad_coordinates(client, auth_headers):
    assert client.get("/api/weather?lat=200&lon=10", headers=auth_headers).status_code == 400


def test_market_needs_api_key(client, auth_headers):
    r = client.get("/api/market?commodity=Tomato", headers=auth_headers)
    assert r.status_code == 503 and "DATAGOV_API_KEY" in r.json()["detail"]


def test_market_prices_and_price_alert(client, auth_headers, monkeypatch):
    monkeypatch.setattr(main_module, "settings",
                        dataclasses.replace(main_module.settings, datagov_api_key="TEST-KEY"))
    rows = [
        {"market": "Kolar", "state": "Karnataka", "date": "25/11/2026", "min": 1200.0, "max": 1600.0, "modal": 1400.0},
        {"market": "Hosur", "state": "Tamil Nadu", "date": "25/11/2026", "min": 1500.0, "max": 2100.0, "modal": 1900.0},
    ]
    monkeypatch.setattr(main_module, "fetch_prices", lambda *a, **k: rows)
    assert client.post("/api/market/watch", headers=auth_headers,
                       json={"commodity": "Tomato", "threshold": 1800}).status_code == 201
    r = client.get("/api/market?commodity=Tomato", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["max_modal"] == 1900.0 and body["summary"]["markets"] == 2
    assert body["records"][0]["market"] == "Hosur"          # sorted by modal price, highest first
    notes = client.get("/api/notifications", headers=auth_headers).json()
    assert any(n["kind"] == "price_alert" for n in notes["items"])


def test_notifications_mark_read(client, auth_headers):
    items = client.get("/api/notifications", headers=auth_headers).json()["items"]
    assert items, "earlier tests should have created notifications"
    assert client.post(f"/api/notifications/{items[0]['id']}/read", headers=auth_headers).status_code == 200
    assert client.post("/api/notifications/read-all", headers=auth_headers).status_code == 200
    assert client.get("/api/notifications", headers=auth_headers).json()["unread"] == 0


def test_models_endpoint_exposes_measured_metrics(client):
    body = client.get("/api/models").json()
    assert body["disease_metrics"]["test_accuracy"] > 0.5
    assert body["crop_metrics"]["data_source"]
