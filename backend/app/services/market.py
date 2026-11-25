"""Mandi (market) prices from data.gov.in (Agmarknet). Requires a free API key from data.gov.in."""
from __future__ import annotations

import httpx


class MarketError(RuntimeError):
    pass


def _number(value) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def fetch_prices(commodity: str, api_key: str, resource_id: str,
                 base_url: str = "https://api.data.gov.in", timeout: float = 15.0) -> list[dict]:
    params = {"api-key": api_key, "format": "json", "limit": 200, "filters[commodity]": commodity}
    try:
        response = httpx.get(f"{base_url}/resource/{resource_id}", params=params, timeout=timeout)
    except httpx.HTTPError as exc:
        raise MarketError("The price service could not be reached. Check the internet connection.") from exc
    if response.status_code in (401, 403):
        raise MarketError("The price service rejected the API key. Check DATAGOV_API_KEY.")
    if response.status_code != 200:
        raise MarketError(f"The price service returned HTTP {response.status_code}.")
    try:
        records = response.json().get("records", [])
    except (ValueError, AttributeError) as exc:
        raise MarketError("The price service returned an unreadable response.") from exc

    rows = []
    for record in records:
        modal = _number(record.get("modal_price"))
        if modal is None:
            continue
        rows.append({
            "market": record.get("market", ""),
            "state": record.get("state", ""),
            "date": record.get("arrival_date", ""),
            "min": _number(record.get("min_price")),
            "max": _number(record.get("max_price")),
            "modal": modal,
        })
    return rows


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {"markets": 0, "avg_modal": None, "min_modal": None, "max_modal": None}
    modal = [r["modal"] for r in rows]
    return {
        "markets": len(rows),
        "avg_modal": round(sum(modal) / len(modal), 2),
        "min_modal": min(modal),
        "max_modal": max(modal),
    }
