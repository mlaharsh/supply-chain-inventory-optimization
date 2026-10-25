"""Inventory analytics: calendarization, ABC-XYZ, policy, and supplier KPIs."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from inventory_opt.config import SERVICE_LEVELS
from inventory_opt.inventory import (
    annual_holding_cost_per_unit,
    assign_abc_classes,
    assign_xyz_classes,
    economic_order_quantity,
    reorder_point_units,
    safety_stock_units,
    service_level_z,
    weekly_demand_cv,
)


def load_core_data(raw_dir: Path) -> dict[str, pd.DataFrame]:
    """Load and lightly normalize the five core CSVs."""

    def read(name: str, date_columns: Iterable[str] = ()) -> pd.DataFrame:
        path = raw_dir / f"{name}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing {path}; run the generator first.")
        return pd.read_csv(path, parse_dates=list(date_columns))

    suppliers = read("suppliers")
    products = read("products")
    sales = read("sales_transactions", ["sale_date"])
    purchase_orders = read(
        "purchase_orders", ["order_date", "promised_date", "received_date"]
    )
    snapshots = read("inventory_snapshots", ["snapshot_date"])

    _validate_core_data(suppliers, products, sales, purchase_orders, snapshots)
    return {
        "suppliers": suppliers,
        "products": products,
        "sales": sales,
        "purchase_orders": purchase_orders,
        "inventory_snapshots": snapshots,
    }


def _validate_core_data(
    suppliers: pd.DataFrame,
    products: pd.DataFrame,
    sales: pd.DataFrame,
    purchase_orders: pd.DataFrame,
    snapshots: pd.DataFrame,
) -> None:
    if products["sku"].duplicated().any():
        raise ValueError("products contains duplicate SKUs")
    if (sales["quantity_sold"] <= 0).any():
        raise ValueError("sales_transactions contains non-positive quantities")
    if set(sales["product_id"]) - set(products["product_id"]):
        raise ValueError("sales_transactions contains unknown product_id values")
    if set(purchase_orders["product_id"]) - set(products["product_id"]):
        raise ValueError("purchase_orders contains unknown product_id values")
    if set(purchase_orders["supplier_id"]) - set(suppliers["supplier_id"]):
        raise ValueError("purchase_orders contains unknown supplier_id values")
    if snapshots.duplicated(["snapshot_date", "product_id"]).any():
        raise ValueError("inventory_snapshots has duplicate product/date rows")
    received = purchase_orders["received_date"].notna()
    if (
        purchase_orders.loc[received, "received_date"]
        < purchase_orders.loc[received, "order_date"]
    ).any():
        raise ValueError("A purchase order was received before it was ordered")


def build_daily_demand(
    sales: pd.DataFrame,
    products: pd.DataFrame,
    start_date: pd.Timestamp | str,
    end_date: pd.Timestamp | str,
) -> pd.DataFrame:
    """Create a calendar-complete product-day demand table with zero-sale days."""

    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if start > end:
        raise ValueError("start_date must be on or before end_date")

    sales = sales.copy()
    sales["sale_date"] = pd.to_datetime(sales["sale_date"]).dt.normalize()
    active_ids = products.loc[products["is_active"], "product_id"].astype(int).tolist()
    dates = pd.date_range(start, end, freq="D", name="demand_date")
    grid = pd.MultiIndex.from_product(
        [active_ids, dates], names=["product_id", "demand_date"]
    ).to_frame(index=False)

    sales_work = sales.rename(columns={"sale_date": "demand_date"}).copy()
    sales_work["demand_date"] = pd.to_datetime(sales_work["demand_date"]).dt.normalize()
    sales_work["line_revenue"] = sales_work["quantity_sold"] * sales_work["unit_price"]
    daily_sales = (
        sales_work.groupby(["product_id", "demand_date"], as_index=False)
        .agg(units_sold=("quantity_sold", "sum"), revenue=("line_revenue", "sum"))
    )

    daily = grid.merge(
        daily_sales,
        on=["product_id", "demand_date"],
        how="left",
        validate="one_to_one",
    )
    daily["units_sold"] = daily["units_sold"].fillna(0).astype(int)
    daily["revenue"] = daily["revenue"].fillna(0.0).round(2)
    return daily.sort_values(["product_id", "demand_date"]).reset_index(drop=True)


def build_weekly_demand(daily_demand: pd.DataFrame) -> pd.DataFrame:
    """Aggregate the calendar-complete daily table to Monday-start weeks."""

    work = daily_demand.copy()
    work["week_start"] = work["demand_date"] - pd.to_timedelta(
        work["demand_date"].dt.weekday, unit="D"
    )
    weekly = (
        work.groupby(["product_id", "week_start"], as_index=False)
        .agg(units_sold=("units_sold", "sum"), revenue=("revenue", "sum"))
        .sort_values(["product_id", "week_start"])
        .reset_index(drop=True)
    )
    weekly["week_end"] = weekly["week_start"] + pd.Timedelta(days=6)
    weekly["units_sold"] = weekly["units_sold"].astype(int)
    weekly["revenue"] = weekly["revenue"].round(2)
    return weekly


def demand_statistics(
    daily_demand: pd.DataFrame,
    as_of: pd.Timestamp | str,
    window_days: int = 365,
) -> pd.DataFrame:
    """Daily demand mean/std over the trailing window, including zeros."""

    as_of_ts = pd.Timestamp(as_of).normalize()
    window_start = as_of_ts - pd.Timedelta(days=window_days)
    window = daily_demand[
        (daily_demand["demand_date"] > window_start)
        & (daily_demand["demand_date"] <= as_of_ts)
    ]
    stats = (
        window.groupby("product_id", as_index=False)
        .agg(
            days_observed=("demand_date", "count"),
            avg_daily_demand=("units_sold", "mean"),
            daily_demand_std=("units_sold", "std"),
            annual_units_365d=("units_sold", "sum"),
        )
        .fillna({"daily_demand_std": 0.0})
    )
    return stats


def weekly_demand_statistics(
    weekly_demand: pd.DataFrame,
    as_of: pd.Timestamp | str,
    weeks: int = 52,
) -> pd.DataFrame:
    """Trailing complete-week statistics used for XYZ classification."""

    as_of_ts = pd.Timestamp(as_of).normalize()
    work = weekly_demand[weekly_demand["week_end"] <= as_of_ts].copy()
    work = work.sort_values(["product_id", "week_start"], ascending=[True, False])
    work["week_rank"] = work.groupby("product_id").cumcount() + 1
    work = work[work["week_rank"] <= weeks]

    stats = (
        work.groupby("product_id", as_index=False)
        .agg(
            weeks_observed=("week_start", "count"),
            weekly_mean_units=("units_sold", "mean"),
            weekly_std_units=("units_sold", "std"),
        )
        .fillna({"weekly_std_units": 0.0})
    )
    stats["weekly_cv"] = [
        weekly_demand_cv(mean, std)
        for mean, std in zip(stats["weekly_mean_units"], stats["weekly_std_units"])
    ]
    return stats


def abc_analysis(
    products: pd.DataFrame,
    sales: pd.DataFrame,
    as_of: pd.Timestamp | str,
) -> pd.DataFrame:
    """ABC by trailing annual consumption value at standard cost."""

    as_of_ts = pd.Timestamp(as_of).normalize()
    start = as_of_ts - pd.Timedelta(days=365)
    sales = sales.copy()
    sales["sale_date"] = pd.to_datetime(sales["sale_date"]).dt.normalize()
    window = sales[
        (sales["sale_date"] > start) & (sales["sale_date"] <= as_of_ts)
    ].copy()
    window["line_revenue"] = window["quantity_sold"] * window["unit_price"]
    units = window.groupby("product_id", as_index=False).agg(
        annual_units=("quantity_sold", "sum"),
        annual_revenue=("line_revenue", "sum"),
    )

    out = products[
        [
            "product_id",
            "sku",
            "product_name",
            "category",
            "demand_pattern",
            "supplier_id",
            "unit_cost",
        ]
    ].copy()
    out = out.merge(units, on="product_id", how="left", validate="one_to_one")
    out["annual_units"] = out["annual_units"].fillna(0).astype(int)
    out["annual_revenue"] = out["annual_revenue"].fillna(0.0)
    out["annual_consumption_value"] = (out["annual_units"] * out["unit_cost"]).round(2)
    out["abc_class"] = assign_abc_classes(out["annual_consumption_value"]).to_numpy()

    total_value = out["annual_consumption_value"].sum()
    out["value_share"] = (
        out["annual_consumption_value"] / total_value if total_value > 0 else 0.0
    )
    out = out.sort_values("annual_consumption_value", ascending=False).reset_index(drop=True)
    out["cumulative_value_share"] = (
        out["annual_consumption_value"].cumsum() / total_value
        if total_value > 0
        else 0.0
    )
    return out


def xyz_analysis(weekly_stats: pd.DataFrame) -> pd.DataFrame:
    """XYZ classification from 52 complete weeks of demand volatility."""

    out = weekly_stats.copy()
    out["xyz_class"] = assign_xyz_classes(out["weekly_cv"]).to_numpy()
    return out


def build_abc_xyz(
    products: pd.DataFrame,
    sales: pd.DataFrame,
    weekly_demand: pd.DataFrame,
    as_of: pd.Timestamp | str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the SKU-level ABC-XYZ table and weekly statistics."""

    abc = abc_analysis(products, sales, as_of)
    weekly_stats = weekly_demand_statistics(weekly_demand, as_of)
    xyz = xyz_analysis(weekly_stats)

    abc_cols = [
        "product_id",
        "annual_units",
        "annual_revenue",
        "annual_consumption_value",
        "abc_class",
        "value_share",
        "cumulative_value_share",
    ]
    xyz_cols = [
        "product_id",
        "weeks_observed",
        "weekly_mean_units",
        "weekly_std_units",
        "weekly_cv",
        "xyz_class",
    ]
    combined = products[
        [
            "product_id",
            "sku",
            "product_name",
            "category",
            "demand_pattern",
            "supplier_id",
            "unit_cost",
            "unit_price",
            "holding_cost_pct",
            "ordering_cost",
            "min_order_qty",
            "target_service_level",
        ]
    ].merge(abc[abc_cols], on="product_id", how="left", validate="one_to_one")
    combined = combined.merge(xyz[xyz_cols], on="product_id", how="left", validate="one_to_one")
    combined["weekly_cv"] = combined["weekly_cv"].fillna(0.0)
    combined["abc_xyz_segment"] = combined["abc_class"] + combined["xyz_class"]
    return combined, weekly_stats


def prepare_purchase_orders(
    purchase_orders: pd.DataFrame,
    products: pd.DataFrame,
    suppliers: pd.DataFrame,
    as_of: pd.Timestamp | str,
) -> pd.DataFrame:
    """Add lead-time performance and open-order status at the analysis date."""

    as_of_ts = pd.Timestamp(as_of).normalize()
    out = purchase_orders.copy()
    for column in ("order_date", "promised_date", "received_date"):
        out[column] = pd.to_datetime(out[column]).dt.normalize()

    out["actual_lead_time_days"] = (out["received_date"] - out["order_date"]).dt.days
    out["promised_lead_time_days"] = (out["promised_date"] - out["order_date"]).dt.days
    out["variance_days"] = (out["received_date"] - out["promised_date"]).dt.days
    out["on_time_flag"] = np.where(
        out["received_date"].notna(),
        (out["received_date"] <= out["promised_date"]).astype(float),
        np.nan,
    )
    out["days_late"] = np.where(
        out["variance_days"].notna(),
        np.maximum(out["variance_days"].fillna(0), 0),
        np.nan,
    )
    out["is_received"] = out["received_date"].notna()
    out["is_open"] = out["status"].isin(["OPEN", "PARTIALLY_RECEIVED"])
    out["open_units"] = out["quantity_ordered"] - out["quantity_received"]
    out["is_overdue"] = out["is_open"] & (out["promised_date"] < as_of_ts)
    out["open_overdue_units"] = np.where(
        out["is_overdue"],
        out["open_units"],
        0,
    )
    out["as_of_date"] = as_of_ts

    product_cols = products[["product_id", "sku", "product_name"]]
    supplier_cols = suppliers[["supplier_id", "supplier_name"]]
    out = out.merge(product_cols, on="product_id", how="left", validate="many_to_one")
    out = out.merge(supplier_cols, on="supplier_id", how="left", validate="many_to_one")
    return out.sort_values(["order_date", "po_id"]).reset_index(drop=True)


def supplier_lead_time_stats(
    po_performance: pd.DataFrame,
    suppliers: pd.DataFrame,
) -> pd.DataFrame:
    """Supplier scorecard using received POs, with contractual fallback."""

    received = po_performance[po_performance["is_received"]].copy()
    if received.empty:
        raise ValueError("No received POs are available for lead-time analysis")

    stats = (
        received.groupby("supplier_id", as_index=False)
        .agg(
            received_po_count=("po_id", "count"),
            avg_actual_lead_time_days=("actual_lead_time_days", "mean"),
            lead_time_std_days=("actual_lead_time_days", "std"),
            median_lead_time_days=("actual_lead_time_days", "median"),
            p90_lead_time_days=("actual_lead_time_days", lambda series: series.quantile(0.90)),
            avg_variance_days=("variance_days", "mean"),
            avg_days_late=("days_late", "mean"),
            on_time_rate=("on_time_flag", "mean"),
        )
    )
    open_stats = (
        po_performance[po_performance["is_open"]]
        .groupby("supplier_id", as_index=False)
        .agg(
            open_po_count=("po_id", "count"),
            open_inbound_units=("open_units", "sum"),
            overdue_open_po_count=("is_overdue", "sum"),
            overdue_inbound_units=("open_overdue_units", "sum"),
        )
    )

    out = suppliers.copy()
    out = out.merge(stats, on="supplier_id", how="left", validate="one_to_one")
    out = out.merge(open_stats, on="supplier_id", how="left", validate="one_to_one")
    out["received_po_count"] = out["received_po_count"].fillna(0).astype(int)
    out["open_po_count"] = out["open_po_count"].fillna(0).astype(int)
    out["open_inbound_units"] = out["open_inbound_units"].fillna(0).astype(int)
    out["overdue_open_po_count"] = out["overdue_open_po_count"].fillna(0).astype(int)
    out["overdue_inbound_units"] = out["overdue_inbound_units"].fillna(0).astype(int)
    out["avg_actual_lead_time_days"] = out["avg_actual_lead_time_days"].fillna(
        out["promised_lead_time_days"]
    )
    out["planning_lead_time_std_days"] = out["lead_time_std_days"].where(
        out["lead_time_std_days"].notna() & (out["lead_time_std_days"] > 0),
        out["lead_time_sigma_days"],
    )
    out["lead_time_variance_days"] = (
        out["avg_actual_lead_time_days"] - out["promised_lead_time_days"]
    )
    out["on_time_rate"] = out["on_time_rate"].fillna(0.0)
    out["avg_variance_days"] = out["avg_variance_days"].fillna(0.0)
    out["avg_days_late"] = out["avg_days_late"].fillna(0.0)
    return out.sort_values("supplier_name").reset_index(drop=True)


def build_inventory_position(
    inventory_snapshots: pd.DataFrame,
    products: pd.DataFrame,
    po_performance: pd.DataFrame,
    as_of: pd.Timestamp | str,
) -> pd.DataFrame:
    """Latest on-hand position, open inbound, and average inventory holding."""

    as_of_ts = pd.Timestamp(as_of).normalize()
    snapshots = inventory_snapshots.copy()
    snapshots["snapshot_date"] = pd.to_datetime(snapshots["snapshot_date"]).dt.normalize()
    snapshots = snapshots[snapshots["snapshot_date"] <= as_of_ts]

    latest = (
        snapshots.sort_values(["product_id", "snapshot_date"])
        .groupby("product_id", as_index=False)
        .tail(1)
        .rename(
            columns={
                "snapshot_date": "inventory_as_of_date",
                "on_hand_units": "current_stock_units",
                "inbound_units": "snapshot_inbound_units",
            }
        )
    )

    recent = snapshots.sort_values(["product_id", "snapshot_date"], ascending=[True, False])
    recent["snapshot_rank"] = recent.groupby("product_id").cumcount() + 1
    recent = recent[recent["snapshot_rank"] <= 52]
    averages = recent.groupby("product_id", as_index=False).agg(
        avg_inventory_units_52w=("on_hand_units", "mean"),
        average_inbound_units_52w=("inbound_units", "mean"),
    )

    open_pos = po_performance[po_performance["is_open"]].copy()
    open_pos["open_units"] = open_pos["quantity_ordered"] - open_pos["quantity_received"]
    open_inbound = (
        open_pos.groupby("product_id", as_index=False)
        .agg(
            inbound_open_units=("open_units", "sum"),
            open_po_count=("po_id", "count"),
            next_po_promised_date=("promised_date", "min"),
            overdue_inbound_units=("open_overdue_units", "sum"),
            overdue_po_count=("is_overdue", "sum"),
        )
    )

    out = products[
        [
            "product_id",
            "sku",
            "product_name",
            "category",
            "demand_pattern",
            "supplier_id",
            "unit_cost",
            "holding_cost_pct",
        ]
    ].merge(latest, on="product_id", how="left", validate="one_to_one")
    out = out.merge(averages, on="product_id", how="left", validate="one_to_one")
    out = out.merge(open_inbound, on="product_id", how="left", validate="many_to_one")
    for column in (
        "current_stock_units",
        "snapshot_inbound_units",
        "inbound_open_units",
        "open_po_count",
        "overdue_inbound_units",
        "overdue_po_count",
        "avg_inventory_units_52w",
    ):
        out[column] = out[column].fillna(0)

    out["inventory_position_units"] = out["current_stock_units"] + out["inbound_open_units"]
    out["current_inventory_value"] = (out["current_stock_units"] * out["unit_cost"]).round(2)
    out["avg_inventory_value_52w"] = (out["avg_inventory_units_52w"] * out["unit_cost"]).round(2)
    out["annual_holding_cost_52w_avg"] = (
        out["avg_inventory_value_52w"] * out["holding_cost_pct"]
    ).round(2)
    out["current_inventory_value"] = out["current_inventory_value"].fillna(0.0)
    out["avg_inventory_value_52w"] = out["avg_inventory_value_52w"].fillna(0.0)
    out["annual_holding_cost_52w_avg"] = out[
        "annual_holding_cost_52w_avg"
    ].fillna(0.0)
    return out


def build_inventory_policy(
    abc_xyz: pd.DataFrame,
    daily_stats: pd.DataFrame,
    supplier_stats: pd.DataFrame,
    inventory: pd.DataFrame,
    service_levels: tuple[float, ...] = SERVICE_LEVELS,
) -> pd.DataFrame:
    """Calculate EOQ, safety stock, and ROP at every target service level."""

    product_info = abc_xyz[
        [
            "product_id",
            "sku",
            "product_name",
            "category",
            "demand_pattern",
            "supplier_id",
            "unit_cost",
            "unit_price",
            "holding_cost_pct",
            "ordering_cost",
            "min_order_qty",
            "target_service_level",
            "annual_units",
            "annual_consumption_value",
            "weekly_mean_units",
            "weekly_std_units",
            "weekly_cv",
            "abc_class",
            "xyz_class",
            "abc_xyz_segment",
        ]
    ].copy()
    lead_cols = supplier_stats[
        [
            "supplier_id",
            "supplier_name",
            "promised_lead_time_days",
            "lead_time_sigma_days",
            "avg_actual_lead_time_days",
            "planning_lead_time_std_days",
            "received_po_count",
            "on_time_rate",
            "avg_variance_days",
            "open_inbound_units",
            "overdue_inbound_units",
        ]
    ].rename(
        columns={
            "open_inbound_units": "supplier_open_inbound_units",
            "overdue_inbound_units": "supplier_overdue_inbound_units",
        }
    )
    inv_cols = inventory[
        [
            "product_id",
            "current_stock_units",
            "inbound_open_units",
            "inventory_position_units",
            "current_inventory_value",
            "avg_inventory_value_52w",
            "annual_holding_cost_52w_avg",
            "next_po_promised_date",
            "overdue_inbound_units",
        ]
    ].rename(columns={"overdue_inbound_units": "product_overdue_inbound_units"})
    daily_cols = daily_stats[
        [
            "product_id",
            "avg_daily_demand",
            "daily_demand_std",
            "days_observed",
        ]
    ]

    out = product_info.merge(lead_cols, on="supplier_id", how="left", validate="many_to_one")
    out = out.merge(inv_cols, on="product_id", how="left", validate="one_to_one")
    out = out.merge(daily_cols, on="product_id", how="left", validate="one_to_one")
    out["avg_daily_demand"] = out["avg_daily_demand"].fillna(0.0)
    out["daily_demand_std"] = out["daily_demand_std"].fillna(0.0)
    out["current_stock_units"] = out["current_stock_units"].fillna(0)
    out["inbound_open_units"] = out["inbound_open_units"].fillna(0)
    out["inventory_position_units"] = out["inventory_position_units"].fillna(0)
    out["planning_lead_time_std_days"] = out["planning_lead_time_std_days"].fillna(
        out["lead_time_sigma_days"]
    )

    records: list[dict[str, float]] = []
    for row in out.itertuples(index=False):
        h = annual_holding_cost_per_unit(float(row.unit_cost), float(row.holding_cost_pct))
        eoq = economic_order_quantity(
            float(row.annual_units),
            float(row.ordering_cost),
            float(row.unit_cost),
            float(row.holding_cost_pct),
        )
        recommended_order_qty = int(math.ceil(max(eoq, float(row.min_order_qty))))
        levels: dict[str, float] = {}
        for service_level in service_levels:
            suffix = f"{int(round(service_level * 100))}"
            z = service_level_z(service_level)
            ss = safety_stock_units(
                float(row.avg_daily_demand),
                float(row.daily_demand_std),
                float(row.avg_actual_lead_time_days),
                float(row.planning_lead_time_std_days),
                service_level,
            )
            levels[f"z_{suffix}"] = z
            levels[f"safety_stock_{suffix}_units"] = ss
            levels[f"rop_{suffix}_units"] = reorder_point_units(
                float(row.avg_daily_demand),
                float(row.avg_actual_lead_time_days),
                ss,
            )
        target_suffix = (
            "90" if row.target_service_level <= 0.90 else "95" if row.target_service_level <= 0.95 else "99"
        )
        target_z = service_level_z(float(row.target_service_level))
        target_ss = levels[f"safety_stock_{target_suffix}_units"]
        constant_lead_ss = target_z * math.sqrt(
            max(float(row.promised_lead_time_days) * float(row.daily_demand_std) ** 2, 0)
        )
        penalty_units = max(target_ss - constant_lead_ss, 0.0)
        lead_extension_units = max(
            (float(row.avg_actual_lead_time_days) - float(row.promised_lead_time_days))
            * float(row.avg_daily_demand),
            0.0,
        )
        records.append(
            {
                "annual_holding_cost_per_unit": h,
                "eoq_units": eoq,
                "recommended_order_qty": recommended_order_qty,
                "safety_stock_target_units": target_ss,
                "rop_target_units": levels[f"rop_{target_suffix}_units"],
                "target_z": target_z,
                "safety_stock_constant_lead_target_units": constant_lead_ss,
                "lead_time_safety_stock_penalty_units": penalty_units,
                "lead_time_cycle_stock_penalty_units": lead_extension_units,
                "lead_time_exposure_units": penalty_units + lead_extension_units,
                "lead_time_exposure_value": (penalty_units + lead_extension_units) * float(row.unit_cost),
                "eoq_annual_cycle_holding_cost": (eoq / 2.0) * h,
                "target_safety_stock_holding_cost": target_ss * h,
                **levels,
            }
        )

    metrics = pd.DataFrame(records)
    out = pd.concat([out.reset_index(drop=True), metrics], axis=1)
    out["lead_time_exposure_value"] = out["lead_time_exposure_value"].round(2)
    out["eoq_annual_cycle_holding_cost"] = out["eoq_annual_cycle_holding_cost"].round(2)
    out["target_safety_stock_holding_cost"] = out["target_safety_stock_holding_cost"].round(2)
    out["target_service_level_pct"] = (out["target_service_level"] * 100).round(0).astype(int)
    out["days_of_supply"] = np.where(
        out["avg_daily_demand"] > 0,
        out["current_stock_units"] / out["avg_daily_demand"],
        np.nan,
    )
    out["static_gap_to_rop_target_units"] = (
        out["inventory_position_units"] - out["rop_target_units"]
    )
    out["static_reorder_required"] = (
        out["inventory_position_units"] < out["rop_target_units"]
    )
    return out


def aggregate_supplier_performance(
    supplier_stats: pd.DataFrame,
    policy: pd.DataFrame,
) -> pd.DataFrame:
    """Add SKU-level lead-time exposure to the supplier scorecard."""

    exposure = (
        policy.groupby("supplier_id", as_index=False)
        .agg(
            lead_time_exposure_units=("lead_time_exposure_units", "sum"),
            lead_time_exposure_value=("lead_time_exposure_value", "sum"),
            lead_time_safety_stock_units=("lead_time_safety_stock_penalty_units", "sum"),
            annual_consumption_value=("annual_consumption_value", "sum"),
            sku_count=("product_id", "count"),
        )
        .round({"lead_time_exposure_value": 2, "annual_consumption_value": 2})
    )
    out = supplier_stats.merge(exposure, on="supplier_id", how="left", validate="one_to_one")
    for column in (
        "lead_time_exposure_units",
        "lead_time_exposure_value",
        "lead_time_safety_stock_units",
        "annual_consumption_value",
        "sku_count",
    ):
        out[column] = out[column].fillna(0)
    out["avg_lead_time_variance_pct"] = np.where(
        out["promised_lead_time_days"] > 0,
        out["lead_time_variance_days"] / out["promised_lead_time_days"],
        np.nan,
    )
    return out.sort_values(
        ["overdue_inbound_units", "lead_time_exposure_value"], ascending=False
    ).reset_index(drop=True)


def build_snapshot_planning_history(
    inventory_snapshots: pd.DataFrame,
    daily_demand: pd.DataFrame,
    policy: pd.DataFrame,
    as_of: pd.Timestamp | str,
) -> pd.DataFrame:
    """Build a retrospective ROP line for each weekly inventory snapshot.

    The dashboard needs a meaningful on-hand-vs-ROP trend, not a single current
    ROP repeated across every history row. For each snapshot date this function
    uses trailing 365-day demand known at that date and the SKU's planning
    lead-time parameters and target service level.

    This is a retrospective planning line, not a reconstruction of the orders
    the simulator actually placed. Lead-time mean and standard deviation come
    from the full evaluation window, so early points contain mild look-ahead in
    the lead-time parameter. Demand statistics never use future demand.
    """

    as_of_ts = pd.Timestamp(as_of).normalize()
    snapshots = inventory_snapshots.copy()
    snapshots["snapshot_date"] = pd.to_datetime(
        snapshots["snapshot_date"]
    ).dt.normalize()
    snapshots = snapshots[snapshots["snapshot_date"] <= as_of_ts].sort_values(
        ["product_id", "snapshot_date"]
    )
    if snapshots.empty:
        return pd.DataFrame(
            columns=[
                "snapshot_date",
                "product_id",
                "trailing_avg_daily_demand",
                "trailing_daily_demand_std",
                "historical_safety_stock_target_units",
                "historical_rop_target_units",
                "on_hand_vs_rop_units",
                "snapshot_stock_status",
            ]
        )

    daily = daily_demand.copy()
    daily["demand_date"] = pd.to_datetime(daily["demand_date"]).dt.normalize()
    params = policy.set_index("product_id")[
        [
            "target_service_level",
            "avg_actual_lead_time_days",
            "planning_lead_time_std_days",
        ]
    ]
    rows: list[dict[str, float | int | str | pd.Timestamp]] = []

    for product_id, group in daily.groupby("product_id", sort=True):
        if product_id not in params.index:
            continue
        product_snapshots = snapshots[snapshots["product_id"] == product_id]
        if product_snapshots.empty:
            continue

        series = (
            group.sort_values("demand_date")
            .set_index("demand_date")["units_sold"]
            .astype(float)
        )
        demand_stats = pd.DataFrame(
            {
                "trailing_avg_daily_demand": series.rolling(
                    "365D", min_periods=1
                ).mean(),
                "trailing_daily_demand_std": series.rolling(
                    "365D", min_periods=2
                ).std(),
            }
        )
        snapshot_dates = pd.DatetimeIndex(product_snapshots["snapshot_date"])
        demand_stats = demand_stats.reindex(snapshot_dates, method="ffill").fillna(0.0)

        parameter = params.loc[product_id]
        target_service_level = float(parameter["target_service_level"])
        mean_lead_time = max(float(parameter["avg_actual_lead_time_days"]), 1.0)
        lead_time_std = float(parameter["planning_lead_time_std_days"])
        z_value = service_level_z(target_service_level)

        for snapshot_date, on_hand, inbound in zip(
            snapshot_dates,
            product_snapshots["on_hand_units"].to_numpy(dtype=float),
            product_snapshots["inbound_units"].to_numpy(dtype=float),
        ):
            row = demand_stats.loc[snapshot_date]
            average_daily = float(row["trailing_avg_daily_demand"])
            daily_std = float(row["trailing_daily_demand_std"])
            safety_stock = safety_stock_units(
                average_daily,
                daily_std,
                mean_lead_time,
                lead_time_std,
                target_service_level,
            )
            reorder_point = reorder_point_units(
                average_daily, mean_lead_time, safety_stock
            )
            inventory_position = float(on_hand) + float(inbound)
            if inventory_position <= 0:
                stock_status = "Stocked Out"
            elif inventory_position <= reorder_point:
                stock_status = "Reorder Now"
            elif float(on_hand) <= reorder_point:
                stock_status = "Inbound Pending"
            else:
                stock_status = "Healthy"
            rows.append(
                {
                    "snapshot_date": snapshot_date,
                    "product_id": int(product_id),
                    "trailing_avg_daily_demand": round(average_daily, 4),
                    "trailing_daily_demand_std": round(daily_std, 4),
                    "planning_lead_time_days": round(mean_lead_time, 2),
                    "planning_lead_time_std_days": round(lead_time_std, 2),
                    "target_service_level": target_service_level,
                    "target_z": round(z_value, 4),
                    "historical_safety_stock_target_units": round(safety_stock, 2),
                    "historical_rop_target_units": round(reorder_point, 2),
                    "on_hand_vs_rop_units": round(float(on_hand) - reorder_point, 2),
                    "snapshot_stock_status": stock_status,
                }
            )

    return pd.DataFrame(rows).sort_values(
        ["snapshot_date", "product_id"]
    ).reset_index(drop=True)


def abc_xyz_summary(overview: pd.DataFrame) -> pd.DataFrame:
    """Dashboard-ready aggregate for the ABC-XYZ heatmap."""

    summary = (
        overview.groupby(["abc_class", "xyz_class"], as_index=False)
        .agg(
            sku_count=("product_id", "count"),
            annual_consumption_value=("annual_consumption_value", "sum"),
            current_inventory_value=("current_inventory_value", "sum"),
            annual_holding_cost=("annual_holding_cost_52w_avg", "sum"),
            at_risk_skus=("stockout_risk_flag", "sum"),
        )
        .sort_values(["abc_class", "xyz_class"])
    )
    total_value = summary["annual_consumption_value"].sum()
    summary["consumption_value_share"] = (
        summary["annual_consumption_value"] / total_value if total_value else 0.0
    )
    return summary.reset_index(drop=True)


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, date_format="%Y-%m-%d")
