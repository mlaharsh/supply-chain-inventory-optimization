from datetime import date

import numpy as np
import pandas as pd
import pytest

from inventory_opt.forecasting import (
    forecast_daily_rate_for_horizon,
    run_forecasting,
)


def _sales_fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range("2024-10-01", "2026-09-30", freq="D")
    day_of_year = dates.dayofyear.to_numpy()
    quantity = np.maximum(
        1,
        np.round(8 + 3 * np.sin(2 * np.pi * day_of_year / 365.25)).astype(int),
    )
    sales = pd.DataFrame(
        {
            "product_id": 1,
            "sale_date": dates,
            "quantity_sold": quantity,
            "unit_price": 15.0,
        }
    )
    products = pd.DataFrame(
        {
            "product_id": [1],
            "sku": ["SKU-TEST"],
            "demand_pattern": ["seasonal"],
            "is_active": [True],
        }
    )
    return sales, products


def test_monthly_forecasting_and_backtest() -> None:
    sales, products = _sales_fixture()
    artifacts = run_forecasting(
        sales,
        products,
        start_date=date(2024, 10, 1),
        end_date=date(2026, 9, 30),
        horizon_months=3,
        holdout_months=3,
    )
    assert len(artifacts.forecasts) == 3
    assert len(artifacts.monthly_history) == 24
    assert artifacts.forecasts["forecast_month"].min() == pd.Timestamp("2026-10-01")
    assert (artifacts.forecasts["forecast_units"] >= 0).all()
    assert not artifacts.accuracy.empty
    assert np.isfinite(artifacts.accuracy_summary["weighted_wape"])
    assert artifacts.forecasts["model"].notna().all()
    assert {"final_model", "holdout_model"}.issubset(artifacts.accuracy.columns)
    assert artifacts.accuracy["final_model"].notna().all()
    assert artifacts.accuracy["holdout_model"].notna().all()


def test_forecast_horizon_conversion_is_prorated() -> None:
    forecasts = pd.DataFrame(
        {
            "forecast_month": pd.to_datetime(
                ["2026-10-01", "2026-11-01", "2026-12-01"]
            ),
            "forecast_units": [310.0, 300.0, 310.0],
            "forecast_rate_std_daily": [1.0, 1.0, 1.0],
        }
    )
    units, daily, rate_std = forecast_daily_rate_for_horizon(
        forecasts, "2026-09-30", 31
    )
    assert units == pytest.approx(310.0)
    assert daily == pytest.approx(10.0)
    assert rate_std == pytest.approx(1.0)

    units_30, daily_30, _ = forecast_daily_rate_for_horizon(
        forecasts, "2026-09-30", 30
    )
    assert units_30 == pytest.approx(300.0)
    assert daily_30 == pytest.approx(10.0)


def test_invalid_forecast_horizon() -> None:
    forecasts = pd.DataFrame(
        {
            "forecast_month": pd.to_datetime(["2026-10-01"]),
            "forecast_units": [100.0],
            "forecast_rate_std_daily": [1.0],
        }
    )
    with pytest.raises(ValueError):
        forecast_daily_rate_for_horizon(forecasts, "2026-09-30", 0)
