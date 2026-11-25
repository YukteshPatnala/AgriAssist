"""Farm economics: cost, revenue, profit, ROI, break-even and loan EMI. All formulas are explicit."""
from __future__ import annotations


def emi(principal: float, annual_rate_pct: float, years: int) -> float:
    """Equated monthly instalment: P * r * (1+r)^n / ((1+r)^n - 1), with r = monthly rate."""
    if principal <= 0 or years <= 0:
        return 0.0
    months = years * 12
    r = annual_rate_pct / 12 / 100
    if r == 0:
        return principal / months
    factor = (1 + r) ** months
    return principal * r * factor / (factor - 1)


def crop_economics(
    area_acres: float,
    yield_per_acre: float,
    price_per_quintal: float,
    costs_per_acre: dict[str, float],
    lease_per_acre: float = 0.0,
    loan_amount: float = 0.0,
    loan_rate_pct: float = 0.0,
    loan_years: int = 0,
) -> dict:
    if area_acres <= 0 or yield_per_acre < 0 or price_per_quintal < 0:
        raise ValueError("Area must be positive; yield and price cannot be negative.")
    if any(v < 0 for v in costs_per_acre.values()) or lease_per_acre < 0:
        raise ValueError("Costs cannot be negative.")

    total_yield = area_acres * yield_per_acre                 # quintals
    revenue = total_yield * price_per_quintal                 # rupees
    cost_per_acre = sum(costs_per_acre.values()) + lease_per_acre
    total_cost = cost_per_acre * area_acres
    profit = revenue - total_cost
    roi_pct = (profit / total_cost * 100) if total_cost > 0 else 0.0

    monthly_emi = emi(loan_amount, loan_rate_pct, loan_years)
    total_repayment = monthly_emi * loan_years * 12
    loan_interest = max(total_repayment - loan_amount, 0.0) if loan_amount > 0 else 0.0

    breakdown = [{"name": k.replace("_", " "), "amount": round(v * area_acres, 2)} for k, v in costs_per_acre.items()]
    if lease_per_acre:
        breakdown.append({"name": "lease", "amount": round(lease_per_acre * area_acres, 2)})

    return {
        "total_yield_quintal": round(total_yield, 2),
        "gross_revenue": round(revenue, 2),
        "total_cost": round(total_cost, 2),
        "cost_breakdown": breakdown,
        "profit": round(profit, 2),
        "roi_pct": round(roi_pct, 2),
        "cost_per_quintal": round(total_cost / total_yield, 2) if total_yield > 0 else None,
        "break_even_price_per_quintal": round(total_cost / total_yield, 2) if total_yield > 0 else None,
        "break_even_yield_per_acre": round(cost_per_acre / price_per_quintal, 2) if price_per_quintal > 0 else None,
        "loan": {
            "monthly_emi": round(monthly_emi, 2),
            "total_repayment": round(total_repayment, 2),
            "total_interest": round(loan_interest, 2),
            "profit_covers_annual_emi": profit >= monthly_emi * 12 if loan_amount > 0 else None,
        },
    }
