"""End-to-end orchestration: generation -> analytics -> forecast -> Tableau exports."""

from __future__ import annotations

import argparse
import json
import logging
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

from inventory_opt.analytics import (
    abc_xyz_summary,
    aggregate_supplier_performance,
    build_abc_xyz,
    build_daily_demand,
    build_inventory_policy,
    build_inventory_position,
    build_snapshot_planning_history,
    build_weekly_demand,
    demand_statistics,
    load_core_data,
    prepare_purchase_orders,
    supplier_lead_time_stats,
    write_csv,
)
from inventory_opt.config import (
    DEFAULT_END_DATE,
    DEFAULT_PRODUCT_COUNT,
    DEFAULT_SEED,
    DEFAULT_START_DATE,
    DEFAULT_SUPPLIER_COUNT,
    ProjectPaths,
)
from inventory_opt.forecasting import run_forecasting
from inventory_opt.generation import GeneratorConfig, generate_dataset
from inventory_opt.optimization import build_dynamic_replenishment

LOGGER = logging.getLogger(__name__)

REQUIRED_RAW_FILES = (
    "suppliers.csv",
    "products.csv",
    "sales_transactions.csv",
    "purchase_orders.csv",
    "inventory_snapshots.csv",
)


def run_pipeline(
    raw_dir: Path | str | None = None,
    output_dir: Path | str | None = None,
    regenerate: bool = False,
    seed: int = DEFAULT_SEED,
    start_date: date | None = None,
    end_date: date | None = None,
    product_count: int = DEFAULT_PRODUCT_COUNT,
    supplier_count: int = DEFAULT_SUPPLIER_COUNT,
) -> dict[str, Any]:
    """Run the full project and return a JSON-serializable run summary."""

    root = Path(__file__).resolve().parent.parent
    raw_path = _resolve_path(raw_dir, root / "data" / "raw")
    output_path = _resolve_path(output_dir, root / "outputs")
    paths = ProjectPaths(
        root=root,
        raw=raw_path,
        outputs=output_path,
        analytics=output_path / "analytics",
        tableau=output_path / "tableau",
    )
    paths.ensure()

    raw_complete = all((paths.raw / name).exists() for name in REQUIRED_RAW_FILES)
    manifest: dict[str, Any]
    generated_now = False

    if regenerate or not raw_complete:
        cfg = GeneratorConfig(
            start_date=start_date or DEFAULT_START_DATE,
            end_date=end_date or DEFAULT_END_DATE,
            n_products=product_count,
            n_suppliers=supplier_count,
            seed=seed,
        )
        LOGGER.info("Generating synthetic dataset: seed=%s, SKUs=%s", seed, product_count)
        dataset = generate_dataset(cfg)
        dataset.write(paths.raw)
        manifest = dataset.manifest
        generated_now = True
    else:
        manifest_path = paths.raw / "generation_manifest.json"
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.exists()
            else {}
        )
        if start_date or end_date:
            LOGGER.warning(
                "Using the existing dataset's date range. Pass --regenerate to rebuild raw data."
            )

    data = load_core_data(paths.raw)
    suppliers = data["suppliers"]
    products = data["products"]
    sales = data["sales"]
    purchase_orders = data["purchase_orders"]
    snapshots = data["inventory_snapshots"]

    start = pd.Timestamp(manifest.get("start_date", sales["sale_date"].min())).normalize()
    end = pd.Timestamp(manifest.get("end_date", sales["sale_date"].max())).normalize()
    if start > end:
        raise ValueError("Invalid analysis horizon")
    as_of = end

    LOGGER.info("Running analytics for %s through %s", start.date(), end.date())
    daily = build_daily_demand(sales, products, start, end)
    weekly = build_weekly_demand(daily)
    abc_xyz, weekly_stats = build_abc_xyz(products, sales, weekly, as_of)
    daily_stats = demand_statistics(daily, as_of)
    po_performance = prepare_purchase_orders(purchase_orders, products, suppliers, as_of)
    supplier_stats = supplier_lead_time_stats(po_performance, suppliers)
    inventory_position = build_inventory_position(snapshots, products, po_performance, as_of)
    policy = build_inventory_policy(abc_xyz, daily_stats, supplier_stats, inventory_position)
    snapshot_planning = build_snapshot_planning_history(snapshots, daily, policy, as_of)
    supplier_performance = aggregate_supplier_performance(supplier_stats, policy)

    LOGGER.info("Fitting demand forecasts and holdout backtests")
    forecast_artifacts = run_forecasting(sales, products, start, end)
    overview = build_dynamic_replenishment(
        policy=policy,
        forecasts=forecast_artifacts.forecasts,
        po_performance=po_performance,
        forecast_accuracy=forecast_artifacts.accuracy,
        as_of=as_of,
    )

    supplier_exposure_cols = supplier_performance[
        ["supplier_id", "lead_time_exposure_value", "lead_time_exposure_units", "on_time_rate"]
    ].rename(
        columns={
            "lead_time_exposure_value": "supplier_total_lead_time_exposure_value",
            "lead_time_exposure_units": "supplier_total_lead_time_exposure_units",
            "on_time_rate": "supplier_on_time_rate",
        }
    )
    overview = overview.merge(
        supplier_exposure_cols, on="supplier_id", how="left", validate="many_to_one"
    )
    overview = overview.sort_values(
        ["risk_rank", "stockout_probability", "projected_lost_revenue_value"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    segment_summary = abc_xyz_summary(overview)

    _validate_outputs(overview, forecast_artifacts.forecasts, as_of)
    latest_snapshot_stock = (
        snapshots[snapshots["snapshot_date"] <= as_of]
        .sort_values(["product_id", "snapshot_date"])
        .groupby("product_id")
        .tail(1)
        .set_index("product_id")["on_hand_units"]
        .reindex(overview["product_id"])
        .to_numpy()
    )
    snapshot_stock_matches = bool(
        np.array_equal(
            latest_snapshot_stock,
            overview["current_stock_units"].to_numpy(dtype=float),
        )
    )
    _write_outputs(
        paths=paths,
        overview=overview,
        policy=policy,
        supplier_performance=supplier_performance,
        po_performance=po_performance,
        daily=daily,
        weekly=weekly,
        monthly=forecast_artifacts.monthly_history,
        forecasts=forecast_artifacts.forecasts,
        accuracy=forecast_artifacts.accuracy,
        snapshots=snapshots,
        snapshot_planning=snapshot_planning,
        products=products,
        segment_summary=segment_summary,
    )

    kpis = _build_kpis(
        overview,
        supplier_performance,
        forecast_artifacts.accuracy_summary,
        manifest,
        forecast_artifacts.forecasts,
        po_performance,
    )
    selected_forecasts = forecast_artifacts.forecasts.drop_duplicates("product_id")
    model_counts = selected_forecasts["model"].value_counts().to_dict()
    holdout_model_counts = (
        forecast_artifacts.accuracy["holdout_model"].value_counts().to_dict()
        if not forecast_artifacts.accuracy.empty
        else {}
    )
    seasonal_holtwinters_skus = int(
        (
            (selected_forecasts["demand_pattern"] == "seasonal")
            & selected_forecasts["model"].str.startswith("Holt-Winters")
        ).sum()
    )
    summary = {
        "project": "Supply Chain Inventory Optimization & Reorder Forecasting",
        "as_of_date": as_of.date().isoformat(),
        "analysis_start": start.date().isoformat(),
        "analysis_end": end.date().isoformat(),
        "generated_now": generated_now,
        "seed": int(manifest.get("seed", seed)),
        "row_counts": {
            "suppliers": int(len(suppliers)),
            "products": int(len(products)),
            "sales_transactions": int(len(sales)),
            "purchase_orders": int(len(purchase_orders)),
            "inventory_snapshots": int(len(snapshots)),
            "weekly_demand_rows": int(len(weekly)),
            "forecast_rows": int(len(forecast_artifacts.forecasts)),
        },
        "kpis": kpis,
        "forecast_accuracy": forecast_artifacts.accuracy_summary,
        "model_counts": model_counts,
        "holdout_model_counts": holdout_model_counts,
        "seasonal_skus_using_holtwinters": seasonal_holtwinters_skus,
        "validation": {
            "skus_in_overview": int(overview["product_id"].nunique()),
            "probabilities_valid": bool(
                overview["stockout_probability"].between(0, 1).all()
            ),
            "non_negative_forecasts": bool(
                (forecast_artifacts.forecasts["forecast_units"] >= 0).all()
            ),
            "current_stock_matches_latest_snapshot": snapshot_stock_matches,
        },
        "paths": {
            "raw_data": str(paths.raw),
            "analytics": str(paths.analytics),
            "tableau_exports": str(paths.tableau),
        },
    }

    with (paths.outputs / "run_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(_json_safe(summary), handle, indent=2)
    _write_executive_summary(paths.outputs / "executive_summary.md", summary, overview, supplier_performance)
    LOGGER.info(
        "Pipeline complete. Current inventory $%s; %s SKUs at risk; weighted WAPE %.1f%%",
        f"{kpis['total_current_inventory_value']:,.0f}",
        kpis["stockout_risk_skus"],
        kpis["forecast_weighted_wape"] * 100,
    )
    return summary


def _build_kpis(
    overview: pd.DataFrame,
    supplier_performance: pd.DataFrame,
    forecast_summary: dict[str, float],
    manifest: dict[str, Any],
    forecasts: pd.DataFrame,
    po_performance: pd.DataFrame,
) -> dict[str, Any]:
    statuses = overview["reorder_status"].value_counts().to_dict()
    received_po_total = float(supplier_performance["received_po_count"].sum())
    weighted_on_time = (
        float(
            (
                supplier_performance["on_time_rate"]
                * supplier_performance["received_po_count"]
            ).sum()
            / received_po_total
        )
        if received_po_total
        else float("nan")
    )
    weighted_variance = (
        float(
            (
                supplier_performance["avg_variance_days"]
                * supplier_performance["received_po_count"]
            ).sum()
            / received_po_total
        )
        if received_po_total
        else float("nan")
    )
    risk_flagged = overview[overview["stockout_risk_flag"]]
    open_pos = po_performance[po_performance["is_open"]]
    return {
        "total_skus": int(overview["product_id"].nunique()),
        "total_current_inventory_value": round(
            float(overview["current_inventory_value"].sum()), 2
        ),
        "annualized_holding_cost": round(
            float(overview["annual_holding_cost_52w_avg"].sum()), 2
        ),
        "annual_consumption_value": round(
            float(overview["annual_consumption_value"].sum()), 2
        ),
        "stockout_risk_skus": int(overview["stockout_risk_flag"].sum()),
        "critical_risk_skus": int((overview["risk_tier"] == "Critical").sum()),
        "watchlist_skus": int(overview["watchlist_flag"].sum()),
        "stocked_out_skus": int(statuses.get("Stocked Out", 0)),
        "reorder_now_skus": int(statuses.get("Reorder Now", 0)),
        "reorder_actions_total": int(
            statuses.get("Stocked Out", 0)
            + statuses.get("Reorder Now", 0)
            + statuses.get("Expedite", 0)
        ),
        "inbound_pending_skus": int(statuses.get("Inbound Pending", 0)),
        "at_risk_inventory_value": round(
            float(risk_flagged["current_inventory_value"].sum()), 2
        ),
        "projected_lost_revenue_exposure": round(
            float(risk_flagged["projected_lost_revenue_value"].sum()), 2
        ),
        "open_purchase_orders": int(len(open_pos)),
        "open_inbound_units": int(open_pos["open_units"].sum()),
        "overdue_purchase_orders": int(open_pos["is_overdue"].sum()),
        "weighted_supplier_on_time_rate": round(weighted_on_time, 4),
        "weighted_avg_lead_time_variance_days": round(weighted_variance, 2),
        "forecast_weighted_wape": float(forecast_summary.get("weighted_wape", float("nan"))),
        "forecast_bias_pct": float(forecast_summary.get("weighted_bias_pct", float("nan"))),
        "forecast_horizon_months": int(forecasts["forecast_month"].nunique())
        if not forecasts.empty
        else 0,
        "lost_sales_units_in_history": int(manifest.get("lost_sales_units", 0)),
        "status_counts": statuses,
        "abc_counts": overview["abc_class"].value_counts().to_dict(),
        "xyz_counts": overview["xyz_class"].value_counts().to_dict(),
        "demand_pattern_counts": overview["demand_pattern"].value_counts().to_dict(),
    }


def _write_outputs(
    *,
    paths: ProjectPaths,
    overview: pd.DataFrame,
    policy: pd.DataFrame,
    supplier_performance: pd.DataFrame,
    po_performance: pd.DataFrame,
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    monthly: pd.DataFrame,
    forecasts: pd.DataFrame,
    accuracy: pd.DataFrame,
    snapshots: pd.DataFrame,
    snapshot_planning: pd.DataFrame,
    products: pd.DataFrame,
    segment_summary: pd.DataFrame,
) -> None:
    # ---- Detailed analytics layer -----------------------------------------
    write_csv(overview, paths.analytics / "inventory_overview.csv")
    write_csv(policy, paths.analytics / "inventory_policy.csv")
    write_csv(segment_summary, paths.analytics / "abc_xyz_summary.csv")
    write_csv(
        _select_columns(
            overview,
            [
                "product_id",
                "sku",
                "product_name",
                "category",
                "supplier_name",
                "demand_pattern",
                "annual_units",
                "annual_consumption_value",
                "abc_class",
                "xyz_class",
                "abc_xyz_segment",
                "current_stock_units",
                "stockout_probability",
                "risk_tier",
                "reorder_status",
            ],
        ),
        paths.analytics / "abc_xyz.csv",
    )
    write_csv(
        _select_columns(
            overview,
            [
                "product_id",
                "sku",
                "product_name",
                "category",
                "abc_class",
                "xyz_class",
                "current_stock_units",
                "inventory_position_units",
                "inbound_open_units",
                "avg_actual_lead_time_days",
                "planning_lead_time_std_days",
                "forecast_daily_demand_30d",
                "stockout_probability",
                "risk_tier",
                "reorder_status",
            ],
        ),
        paths.analytics / "stockout_risk.csv",
    )
    actionable_statuses = ["Stocked Out", "Reorder Now", "Expedite", "At Risk", "Watch"]
    alerts = overview[overview["reorder_status"].isin(actionable_statuses)].copy()
    write_csv(alerts, paths.analytics / "reorder_alerts.csv")
    write_csv(supplier_performance, paths.analytics / "supplier_performance.csv")
    write_csv(po_performance, paths.analytics / "purchase_order_performance.csv")
    write_csv(daily, paths.analytics / "daily_demand.csv")
    write_csv(weekly, paths.analytics / "weekly_demand.csv")
    write_csv(monthly, paths.analytics / "monthly_demand.csv")
    write_csv(forecasts, paths.analytics / "demand_forecasts.csv")
    write_csv(accuracy, paths.analytics / "forecast_accuracy.csv")

    # ---- Curated Tableau layer --------------------------------------------
    write_csv(overview, paths.tableau / "inventory_overview.csv")
    write_csv(segment_summary, paths.tableau / "abc_xyz_summary.csv")
    write_csv(alerts, paths.tableau / "reorder_alerts.csv")
    write_csv(supplier_performance, paths.tableau / "supplier_performance.csv")
    write_csv(accuracy, paths.tableau / "forecast_accuracy.csv")

    product_attrs = overview[
        [
            "product_id",
            "sku",
            "product_name",
            "category",
            "abc_class",
            "xyz_class",
            "abc_xyz_segment",
            "supplier_name",
        ]
    ]
    weekly_tableau = weekly.merge(product_attrs, on="product_id", how="left", validate="many_to_one")
    write_csv(weekly_tableau, paths.tableau / "weekly_demand.csv")

    monthly_tableau = _build_monthly_timeseries(monthly, forecasts, product_attrs)
    write_csv(monthly_tableau, paths.tableau / "monthly_demand_forecast.csv")
    write_csv(forecasts, paths.tableau / "demand_forecast.csv")

    po_tableau = _select_columns(
        po_performance,
        [
            "po_id",
            "po_number",
            "sku",
            "product_name",
            "supplier_name",
            "order_date",
            "promised_date",
            "received_date",
            "quoted_lead_time_days",
            "actual_lead_time_days",
            "variance_days",
            "days_late",
            "on_time_flag",
            "quantity_ordered",
            "quantity_received",
            "open_units",
            "is_open",
            "is_overdue",
            "status",
        ],
    )
    write_csv(po_tableau, paths.tableau / "purchase_order_lead_times.csv")

    snapshot_export = snapshots.copy()
    snapshot_export["snapshot_date"] = pd.to_datetime(snapshot_export["snapshot_date"]).dt.normalize()
    snapshot_export = snapshot_export.merge(
        products[["product_id", "sku", "product_name", "category", "unit_cost"]],
        on="product_id",
        how="left",
        validate="many_to_one",
    )
    snapshot_export = snapshot_export.merge(
        overview[["product_id", "abc_class", "xyz_class", "abc_xyz_segment"]],
        on="product_id",
        how="left",
        validate="many_to_one",
    )
    snapshot_export = snapshot_export.merge(
        snapshot_planning,
        on=["snapshot_date", "product_id"],
        how="left",
        validate="one_to_one",
    )
    snapshot_export["inventory_value"] = (
        snapshot_export["on_hand_units"] * snapshot_export["unit_cost"]
    ).round(2)
    snapshot_export["inventory_position_units"] = (
        snapshot_export["on_hand_units"] + snapshot_export["inbound_units"]
    )
    write_csv(snapshot_export, paths.tableau / "inventory_snapshots.csv")

    quality_report = {
        "overview_rows": int(len(overview)),
        "overview_unique_skus": int(overview["sku"].nunique()),
        "policy_rows": int(len(policy)),
        "supplier_rows": int(len(supplier_performance)),
        "po_rows": int(len(po_performance)),
        "snapshot_rows": int(len(snapshot_export)),
        "weekly_rows": int(len(weekly_tableau)),
        "monthly_timeseries_rows": int(len(monthly_tableau)),
        "forecast_rows": int(len(forecasts)),
        "accuracy_rows": int(len(accuracy)),
        "alerts_rows": int(len(alerts)),
    }
    with (paths.outputs / "data_quality_report.json").open("w", encoding="utf-8") as handle:
        json.dump(quality_report, handle, indent=2)


def _build_monthly_timeseries(
    monthly: pd.DataFrame,
    forecasts: pd.DataFrame,
    product_attrs: pd.DataFrame,
) -> pd.DataFrame:
    actuals = monthly.copy()
    actuals["record_type"] = "Actual"
    actuals["forecast_units"] = np.nan
    actuals["lower_95_units"] = np.nan
    actuals["upper_95_units"] = np.nan
    actuals["forecast_month"] = pd.NaT

    future = forecasts.copy()
    future["record_type"] = "Forecast"
    future["month_start"] = pd.to_datetime(future["forecast_month"]).dt.normalize()
    future["actual_units"] = np.nan

    common_cols = [
        "product_id",
        "month_start",
        "actual_units",
        "forecast_units",
        "lower_95_units",
        "upper_95_units",
        "record_type",
        "forecast_month",
        "demand_pattern",
        "model",
    ]
    actual_common = actuals.reindex(columns=common_cols)
    future_common = future.reindex(columns=common_cols)
    combined = pd.concat([actual_common, future_common], ignore_index=True)
    combined = combined.merge(product_attrs, on="product_id", how="left", validate="many_to_one")
    return combined.sort_values(["product_id", "month_start", "record_type"]).reset_index(drop=True)


def _select_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise KeyError(f"Expected columns are missing: {missing}")
    return frame[columns].copy()


def _validate_outputs(
    overview: pd.DataFrame,
    forecasts: pd.DataFrame,
    as_of: pd.Timestamp,
) -> None:
    if overview["product_id"].duplicated().any():
        raise ValueError("Inventory overview has duplicate SKUs")
    if not overview["stockout_probability"].between(0, 1).all():
        raise ValueError("Stockout probabilities fall outside [0, 1]")
    if (overview["current_stock_units"] < 0).any():
        raise ValueError("Negative current stock found")
    if (overview["inventory_position_units"] < overview["current_stock_units"]).any():
        raise ValueError("Inventory position is below on-hand stock")
    if (forecasts["forecast_units"] < 0).any():
        raise ValueError("Negative demand forecast found")
    if not forecasts["forecast_month"].max() > as_of:
        raise ValueError("Forecast horizon does not extend beyond the analysis date")
    if not np.isfinite(overview["dynamic_rop_target_units"]).all():
        raise ValueError("Non-finite dynamic ROP found")


def _write_executive_summary(
    path: Path,
    summary: dict[str, Any],
    overview: pd.DataFrame,
    supplier_performance: pd.DataFrame,
) -> None:
    kpis = summary["kpis"]
    top_risk = overview.sort_values(
        ["stockout_probability", "projected_lost_revenue_value"], ascending=False
    ).head(6)
    top_suppliers = supplier_performance.sort_values(
        ["lead_time_exposure_value", "overdue_inbound_units"], ascending=False
    ).head(5)

    lines = [
        "# Executive Summary — Supply Chain Inventory Optimization",
        "",
        f"**Analysis date:** {summary['as_of_date']}  ",
        f"**Scope:** {kpis['total_skus']} active SKUs, "
        f"${kpis['annual_consumption_value']:,.0f} annual consumption value  ",
        "**Data:** deterministic synthetic portfolio dataset",
        "",
        "## KPI snapshot",
        "",
        "| KPI | Result |",
        "|---|---:|",
        f"| Current on-hand inventory value | ${kpis['total_current_inventory_value']:,.0f} |",
        f"| Annualized holding cost (52-week average inventory) | ${kpis['annualized_holding_cost']:,.0f} |",
        f"| SKUs below dynamic ROP / stocked out | {kpis['reorder_now_skus'] + kpis['stocked_out_skus']} |",
        f"| High/critical stockout-risk SKUs | {kpis['stockout_risk_skus']} |",
        f"| Projected lost-revenue exposure | ${kpis['projected_lost_revenue_exposure']:,.0f} |",
        f"| Open / overdue purchase orders | {kpis['open_purchase_orders']} / {kpis['overdue_purchase_orders']} |",
        f"| Weighted supplier on-time rate | {kpis['weighted_supplier_on_time_rate']:.1%} |",
        f"| Forecast holdout WAPE | {kpis['forecast_weighted_wape']:.1%} |",
        "",
        "## Priority stockout exposures",
        "",
        "| SKU | Pattern | Stock | Lead time (d) | Stockout probability | Risk | Action |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for row in top_risk.itertuples(index=False):
        lines.append(
            f"| {row.sku} | {row.demand_pattern} | {row.current_stock_units:,.0f} | "
            f"{row.avg_actual_lead_time_days:.1f} | {row.stockout_probability:.0%} | "
            f"{row.risk_tier} | {row.risk_action} |"
        )
    lines.extend(
        [
            "",
            "## Supplier watchlist",
            "",
            "| Supplier | Actual vs promised LT (d) | On-time | Overdue inbound units | Lead-time exposure value |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for row in top_suppliers.itertuples(index=False):
        lines.append(
            f"| {row.supplier_name} | {row.avg_actual_lead_time_days:.1f} vs "
            f"{row.promised_lead_time_days:.0f} | {row.on_time_rate:.0%} | "
            f"{row.overdue_inbound_units:,.0f} | ${row.lead_time_exposure_value:,.0f} |"
        )
    model_text = ", ".join(
        f"{name}: {count}" for name, count in summary.get("model_counts", {}).items()
    )
    holdout_model_text = ", ".join(
        f"{name}: {count}"
        for name, count in summary.get("holdout_model_counts", {}).items()
    )
    lines.extend(
        [
            "",
            "## Forecast model mix",
            "",
            f"- Final model fit on all 24 months, selected per SKU by AIC: {model_text}",
            f"- Holdout refit on the first 21 months: {holdout_model_text}",
            f"- Seasonal SKUs using Holt-Winters in the final model: {summary.get('seasonal_skus_using_holtwinters', 0)}",
            "- The 3-month holdout is used only for reported accuracy, never for model selection.",
            "- The final and holdout models can differ because AIC is re-evaluated on the shorter training window. `forecast_accuracy.csv` reports both.",
            "",
            "## How to read this output",
            "",
            "- Current stock is the latest inventory snapshot; inventory position adds all open inbound POs.",
            "- Dynamic ROP uses forecast demand and historical demand/lead-time variability.",
            "- Stockout probability is a 20,000-path Monte Carlo over variable lead time and demand.",
            "- Reorder actions are decision support, not automated purchasing. Confirm MOQ, cash, and supplier capacity before ordering.",
            "",
            "See `docs/methodology.md` for formula assumptions and `docs/tableau_dashboard_spec.md` for the dashboard build.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if value is pd.NA or (
        isinstance(value, (float, np.floating)) and math.isnan(float(value))
    ):
        return None
    return value


def _resolve_path(value: Path | str | None, default: Path) -> Path:
    if value is None:
        return default.resolve()
    path = Path(value)
    return path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Supply Chain Inventory Optimization portfolio pipeline."
    )
    parser.add_argument("--raw-dir", type=Path, default=None, help="Raw CSV directory")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory")
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Rebuild the synthetic core dataset before analysis",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--start", type=date.fromisoformat, default=None)
    parser.add_argument("--end", type=date.fromisoformat, default=None)
    parser.add_argument("--products", type=int, default=DEFAULT_PRODUCT_COUNT)
    parser.add_argument("--suppliers", type=int, default=DEFAULT_SUPPLIER_COUNT)
    parser.add_argument("--log-level", default="INFO")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    run_pipeline(
        raw_dir=args.raw_dir,
        output_dir=args.output_dir,
        regenerate=args.regenerate,
        seed=args.seed,
        start_date=args.start,
        end_date=args.end,
        product_count=args.products,
        supplier_count=args.suppliers,
    )


if __name__ == "__main__":
    main()
