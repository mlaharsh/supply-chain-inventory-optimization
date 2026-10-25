from datetime import date
from pathlib import Path

import pandas as pd

from inventory_opt.pipeline import run_pipeline


def test_pipeline_end_to_end_smoke(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    output_dir = tmp_path / "outputs"
    summary = run_pipeline(
        raw_dir=raw_dir,
        output_dir=output_dir,
        regenerate=True,
        seed=17,
        start_date=date(2025, 1, 1),
        end_date=date(2026, 9, 30),
        product_count=10,
        supplier_count=4,
    )

    assert summary["kpis"]["total_skus"] == 10
    assert summary["validation"]["skus_in_overview"] == 10
    assert summary["validation"]["probabilities_valid"]
    assert summary["validation"]["current_stock_matches_latest_snapshot"]
    for name in (
        "inventory_overview.csv",
        "supplier_performance.csv",
        "demand_forecast.csv",
        "inventory_snapshots.csv",
        "monthly_demand_forecast.csv",
        "purchase_order_lead_times.csv",
    ):
        assert (output_dir / "tableau" / name).exists()

    monthly = pd.read_csv(output_dir / "tableau" / "monthly_demand_forecast.csv")
    assert not any(column.endswith("_x") or column.endswith("_y") for column in monthly.columns)
    assert "sku" in monthly.columns
    assert set(monthly["record_type"]) == {"Actual", "Forecast"}

    overview = pd.read_csv(output_dir / "tableau" / "inventory_overview.csv")
    assert overview["stockout_probability"].between(0, 1).all()
    assert (overview["forecast_lead_time_units"] >= 0).all()
    assert "annual_holding_cost_52w_avg" in overview.columns
    assert "supplier_total_lead_time_exposure_value" in overview.columns

    snapshots = pd.read_csv(output_dir / "tableau" / "inventory_snapshots.csv")
    assert "historical_rop_target_units" in snapshots.columns
    assert snapshots["historical_rop_target_units"].notna().all()
    assert (snapshots["historical_rop_target_units"] >= 0).all()
