"""Rule-based soil fertility analysis from soil test values.

Rating bands follow commonly used soil-fertility ratings for India. Check them against your
state's Soil Health Card guidance before relying on them for real decisions.
"""
from __future__ import annotations

NUTRIENT_BANDS = {
    # name: (low_upper_limit, medium_upper_limit) in kg/ha. Below low = low; up to medium = medium; above = high.
    "nitrogen": (280.0, 560.0),
    "phosphorus": (10.0, 25.0),
    "potassium": (110.0, 280.0),
}

ADVICE = {
    "nitrogen": {
        "low": "Nitrogen is low. Add well-decomposed farmyard manure or compost and apply nitrogen fertilizer in split doses, following your local agriculture office advice.",
        "medium": "Nitrogen is adequate. Maintain it with split doses matched to the crop's growth stages.",
        "high": "Nitrogen is high. Avoid extra nitrogen, which encourages lush growth and pest or disease problems.",
    },
    "phosphorus": {
        "low": "Phosphorus is low. Apply a phosphatic fertilizer at sowing, at the dose recommended for your soil test.",
        "medium": "Phosphorus is adequate. Apply a maintenance dose as recommended for the crop.",
        "high": "Phosphorus is high. Skip phosphatic fertilizer this season and re-test after harvest.",
    },
    "potassium": {
        "low": "Potassium is low. Apply a potassic fertilizer, which supports fruit quality and stress tolerance.",
        "medium": "Potassium is adequate. Maintain with the recommended dose for the crop.",
        "high": "Potassium is high. No extra potassium is needed this season.",
    },
}

OC_BANDS = (0.5, 0.75)  # organic carbon %: below 0.5 low, 0.5 to 0.75 medium, above 0.75 high


def _band(value: float, low: float, high: float) -> str:
    if value < low:
        return "low"
    if value <= high:
        return "medium"
    return "high"


def analyze(nitrogen: float, phosphorus: float, potassium: float, ph: float, organic_carbon: float) -> dict:
    nutrients = []
    for name, value in (("nitrogen", nitrogen), ("phosphorus", phosphorus), ("potassium", potassium)):
        low, high = NUTRIENT_BANDS[name]
        rating = _band(value, low, high)
        nutrients.append({
            "name": name,
            "value": value,
            "unit": "kg/ha",
            "rating": rating,
            "advice": ADVICE[name][rating],
        })

    if ph < 6.5:
        ph_rating = "acidic"
        ph_advice = "Acidic soil can lock up phosphorus and reduce some nutrients. Consider liming as advised by a soil test."
    elif ph > 7.5:
        ph_rating = "alkaline"
        ph_advice = "Alkaline soil can reduce zinc and iron availability. Add organic matter and check micronutrients."
    else:
        ph_rating = "neutral"
        ph_advice = "pH is in the range suited to most crops."

    oc_rating = _band(organic_carbon, *OC_BANDS)
    oc_advice = {
        "low": "Organic carbon is low. Add farmyard manure, compost or crop residues to improve soil structure and water holding.",
        "medium": "Organic carbon is moderate. Continue adding organic matter each season.",
        "high": "Organic carbon is good. Keep up the practice that built it.",
    }[oc_rating]

    concerns = sum(1 for n in nutrients if n["rating"] == "low")
    concerns += 1 if ph_rating != "neutral" else 0
    concerns += 1 if oc_rating == "low" else 0
    overall = "Good" if concerns == 0 else ("Needs attention" if concerns <= 2 else "Poor")

    return {
        "overall": overall,
        "nutrients": nutrients,
        "ph": {"value": ph, "rating": ph_rating, "advice": ph_advice},
        "organic_carbon": {"value": organic_carbon, "unit": "%", "rating": oc_rating, "advice": oc_advice},
        "note": "Advice is general. Confirm fertilizer doses with a soil testing laboratory or your local agriculture office.",
    }
