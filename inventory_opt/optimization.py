"""Forecast-driven replenishment decisions and stockout-risk composition."""

from __future__ import annotations

import math
from datetime import timedelta

import numpy as np
import pandas as pd

from inventory_opt.config import SERVICE_LEVELS
from inventory_opt.forecasting import forecast_daily_rate_for_horizon
from inventory_opt.inventory import (
    reorder_point_units,
    safety_stock_units,
)
from inventory_opt.stockout import classify_risk_tier, estimate_stockout_risk


def build_dynamic_replenishment(
    policy: pd.DataFrame,
    forecasts: pd.DataFrame,
    po_performance: pd.DataFrame,
    forecast_accuracy: pd.DataFrame,
    as_of: pd.Timestamp | str,
) -> pd.DataFrame:
    """Add forecast-based ROP, stockout probability, and action status.

    The original policy table uses trailing historical demand statistics. This
    function preserves those audit columns and adds a forecast-driven decision
    layer. Stockout risk uses only inbound purchase orders promised within the
    lead-time horizon; the reorder position uses all open inbound supply.
    """

    as_of_ts = pd.Timestamp(as_of).normalize()
    accuracy_map = (
        forecast_accuracy.set_index("product_id")["wape"].to_dict()
        if not forecast_accuracy.empty
        else {}
    )
    forecasts = forecasts.copy()
    forecasts["forecast_month"] = pd.to_datetime(forecasts["forecast_month"])
    rows: list[dict[str, float | int | str | bool | pd.Timestamp | None]] = []

    for record in policy.itertuples(index=False):
        product_id = int(record.product_id)
        sku_forecast = forecasts[forecasts["product_id"] == product_id].sort_values(
            "forecast_month"
        )
        if sku_forecast.empty:
            raise ValueError(f"No forecast available for product_id={product_id}")

        mean_lead = max(float(record.avg_actual_lead_time_days), 1.0)
        lead_horizon_days = max(1, int(math.ceil(mean_lead)))
        units_30d, daily_rate_30d, rate_std_30d = forecast_daily_rate_for_horizon(
            sku_forecast, as_of_ts, 30
        )
        lead_units, lead_daily_rate, lead_rate_std = forecast_daily_rate_for_horizon(
            sku_forecast, as_of_ts, lead_horizon_days
        )

        open_pos = po_performance[
            (po_performance["product_id"] == product_id) & po_performance["is_open"]
        ]
        due_by_lead = open_pos[
            open_pos["promised_date"] <= as_of_ts + pd.Timedelta(days=lead_horizon_days)
        ]
        inbound_within_lead = float(due_by_lead["open_units"].sum())
        available_for_lead = float(record.current_stock_units) + inbound_within_lead

        risk = estimate_stockout_risk(
            available_units=available_for_lead,
            mean_daily_demand=lead_daily_rate,
            daily_demand_std=float(record.daily_demand_std),
            mean_lead_time_days=mean_lead,
            lead_time_std_days=float(record.planning_lead_time_std_days),
            forecast_rate_std_daily=lead_rate_std,
            n_simulations=20_000,
            random_seed=20260930 + product_id,
        )

        dynamic_policy: dict[str, float] = {}
        for service_level in SERVICE_LEVELS:
            suffix = f"{int(round(service_level * 100))}"
            ss = safety_stock_units(
                lead_daily_rate,
                float(record.daily_demand_std),
                mean_lead,
                float(record.planning_lead_time_std_days),
                service_level,
            )
            dynamic_policy[f"dynamic_safety_stock_{suffix}_units"] = ss
            dynamic_policy[f"dynamic_rop_{suffix}_units"] = reorder_point_units(
                lead_daily_rate, mean_lead, ss
            )

        target_suffix = (
            "90"
            if record.target_service_level <= 0.90
            else "95"
            if record.target_service_level <= 0.95
            else "99"
        )
        dynamic_ss_target = dynamic_policy[f"dynamic_safety_stock_{target_suffix}_units"]
        dynamic_rop_target = dynamic_policy[f"dynamic_rop_{target_suffix}_units"]
        gap_to_dynamic_rop = float(record.inventory_position_units) - dynamic_rop_target

        status = _reorder_status(
            current_stock=float(record.current_stock_units),
            inventory_position=float(record.inventory_position_units),
            dynamic_rop=dynamic_rop_target,
            stockout_probability=risk.stockout_probability,
        )
        reorder_required = (gap_to_dynamic_rop < 0) or (risk.stockout_probability >= 0.25)
        if reorder_required:
            suggested = max(
                dynamic_rop_target
                + float(record.recommended_order_qty)
                - float(record.inventory_position_units),
                0.0,
            )
            if 0 < suggested < float(record.min_order_qty):
                suggested = float(record.min_order_qty)
        else:
            suggested = 0.0

        expected_unmet = max(risk.expected_lead_demand_units - available_for_lead, 0.0)
        rows.append(
            {
                "forecast_next_30d_units": round(units_30d, 2),
                "forecast_daily_demand_30d": round(daily_rate_30d, 4),
                "forecast_rate_std_daily": round(rate_std_30d, 4),
                "forecast_lead_time_units": round(lead_units, 2),
                "forecast_lead_time_daily_rate": round(lead_daily_rate, 4),
                "forecast_model": str(sku_forecast.iloc[0]["model"]),
                "forecast_wape": accuracy_map.get(product_id, np.nan),
                "lead_time_horizon_days": lead_horizon_days,
                "inbound_within_lead_time_units": int(inbound_within_lead),
                "available_for_lead_time_units": available_for_lead,
                "expected_lead_demand_units": round(
                    risk.expected_lead_demand_units, 2
                ),
                "lead_demand_p95_units": round(risk.p95_lead_demand_units, 2),
                "projected_ending_inventory_units": round(
                    risk.projected_ending_inventory_units, 2
                ),
                "normal_stockout_probability": round(
                    risk.normal_stockout_probability, 4
                ),
                "stockout_probability": round(risk.stockout_probability, 4),
                "risk_tier": classify_risk_tier(risk.stockout_probability),
                "risk_rank": _risk_rank(risk.stockout_probability),
                "stockout_risk_flag": risk.stockout_probability >= 0.25,
                "watchlist_flag": risk.stockout_probability >= 0.10,
                "projected_lost_sales_units": round(expected_unmet, 2),
                "projected_lost_revenue_value": round(
                    expected_unmet * float(record.unit_price), 2
                ),
                "simulation_count": risk.simulations,
                **dynamic_policy,
                "dynamic_safety_stock_target_units": dynamic_ss_target,
                "dynamic_rop_target_units": round(dynamic_rop_target, 2),
                "gap_to_dynamic_rop_units": round(gap_to_dynamic_rop, 2),
                "days_of_supply_forecast": round(
                    float(record.current_stock_units) / daily_rate_30d, 2
                )
                if daily_rate_30d > 0
                else np.nan,
                "reorder_status": status,
                "reorder_required": bool(reorder_required),
                "suggested_order_units": int(math.ceil(suggested)),
                "risk_action": _risk_action(status, risk.stockout_probability),
            }
        )

    dynamic = pd.DataFrame(rows)
    out = pd.concat([policy.reset_index(drop=True), dynamic], axis=1)
    out["stockout_risk_flag"] = out["stockout_risk_flag"].astype(bool)
    out["watchlist_flag"] = out["watchlist_flag"].astype(bool)
    out["reorder_required"] = out["reorder_required"].astype(bool)
    return out


def _reorder_status(
    current_stock: float,
    inventory_position: float,
    dynamic_rop: float,
    stockout_probability: float,
) -> str:
    if current_stock <= 0 and stockout_probability >= 0.10:
        return "Stocked Out"
    if inventory_position <= dynamic_rop:
        return "Reorder Now"
    if stockout_probability >= 0.50:
        return "Expedite"
    if stockout_probability >= 0.25:
        return "At Risk"
    if current_stock <= dynamic_rop:
        return "Inbound Pending"
    if stockout_probability >= 0.10:
        return "Watch"
    return "Healthy"


def _risk_action(status: str, stockout_probability: float) -> str:
    if status in {"Stocked Out", "Reorder Now"}:
        return "Place replenishment order"
    if status == "Expedite":
        return "Expedite open PO / validate inbound"
    if status == "At Risk" or stockout_probability >= 0.25:
        return "Review order quantity and service level"
    if status == "Inbound Pending":
        return "Monitor inbound receipt"
    if status == "Watch":
        return "Monitor forecast and lead time"
    return "No action"


def _risk_rank(probability: float) -> int:
    if probability >= 0.50:
        return 4
    if probability >= 0.25:
        return 3
    if probability >= 0.10:
        return 2
    return 1
