"""Weather forecast from Open-Meteo (free, no API key) and rule-based farm alerts."""
from __future__ import annotations

import httpx


class WeatherError(RuntimeError):
    pass


def fetch_forecast(latitude: float, longitude: float, base_url: str, timeout: float = 10.0) -> dict:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
        "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
        "timezone": "auto",
        "forecast_days": 7,
    }
    try:
        response = httpx.get(f"{base_url}/v1/forecast", params=params, timeout=timeout)
    except httpx.HTTPError as exc:
        raise WeatherError("The weather service could not be reached. Check the internet connection.") from exc
    if response.status_code != 200:
        raise WeatherError(f"The weather service returned HTTP {response.status_code}.")
    try:
        return response.json()
    except ValueError as exc:
        raise WeatherError("The weather service returned an unreadable response.") from exc


def parse_days(data: dict) -> list[dict]:
    daily = data.get("daily", {})
    rows = zip(
        daily.get("time", []),
        daily.get("precipitation_sum", []),
        daily.get("temperature_2m_max", []),
        daily.get("temperature_2m_min", []),
    )
    return [
        {"date": d, "rain_mm": p or 0.0, "tmax": tx, "tmin": tn}
        for d, p, tx, tn in rows
    ]


def build_alerts(days: list[dict], rain_mm_3day: float = 20.0, heat_c: float = 38.0, cold_c: float = 5.0) -> list[dict]:
    alerts = []
    three_day_rain = sum(d["rain_mm"] for d in days[:3])
    if three_day_rain >= rain_mm_3day:
        alerts.append({
            "kind": "heavy_rain",
            "title": "Heavy rain expected",
            "body": f"About {three_day_rain:.0f} mm of rain is forecast in the next 3 days. Delay spraying and check field drainage.",
        })
    hot = [d for d in days if d["tmax"] is not None and d["tmax"] >= heat_c]
    if hot:
        alerts.append({
            "kind": "heat",
            "title": "Heat stress warning",
            "body": f"Maximum temperature of {max(d['tmax'] for d in hot):.0f} °C is forecast. Irrigate in the early morning and mulch the soil.",
        })
    cold = [d for d in days if d["tmin"] is not None and d["tmin"] <= cold_c]
    if cold:
        alerts.append({
            "kind": "cold",
            "title": "Cold night warning",
            "body": f"Minimum temperature of {min(d['tmin'] for d in cold):.0f} °C is forecast. Protect young seedlings from cold.",
        })
    return alerts
