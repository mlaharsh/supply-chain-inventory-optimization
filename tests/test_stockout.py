import pytest

from inventory_opt.stockout import classify_risk_tier, estimate_stockout_risk


def test_stockout_probability_monotonic_in_inventory() -> None:
    common = {
        "mean_daily_demand": 5.0,
        "daily_demand_std": 2.0,
        "mean_lead_time_days": 10.0,
        "lead_time_std_days": 2.0,
        "forecast_rate_std_daily": 0.5,
        "n_simulations": 6_000,
        "random_seed": 11,
    }
    empty = estimate_stockout_risk(available_units=0, **common)
    low_stock = estimate_stockout_risk(available_units=20, **common)
    high_stock = estimate_stockout_risk(available_units=300, **common)
    assert 0 <= empty.stockout_probability <= 1
    assert empty.stockout_probability > low_stock.stockout_probability
    assert low_stock.stockout_probability >= high_stock.stockout_probability
    assert high_stock.stockout_probability == pytest.approx(0.0, abs=0.01)
    assert empty.risk_tier == "Critical"
    assert high_stock.risk_tier == "Low"


def test_risk_with_zero_demand_has_no_stockout() -> None:
    risk = estimate_stockout_risk(
        available_units=0,
        mean_daily_demand=0,
        daily_demand_std=0,
        mean_lead_time_days=10,
        lead_time_std_days=0,
        n_simulations=2_000,
    )
    assert risk.stockout_probability == 0
    assert risk.projected_ending_inventory_units == 0


def test_risk_tiers() -> None:
    assert classify_risk_tier(0.75) == "Critical"
    assert classify_risk_tier(0.30) == "High"
    assert classify_risk_tier(0.12) == "Watch"
    assert classify_risk_tier(0.01) == "Low"


def test_invalid_simulation_count() -> None:
    with pytest.raises(ValueError):
        estimate_stockout_risk(10, 1, 1, 5, 1, n_simulations=100)
