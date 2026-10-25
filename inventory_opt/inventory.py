"""Core inventory-management formulas.

The functions in this module are intentionally pure and unit-testable. Every
formula documents its assumptions because a mathematically correct EOQ or ROP
can still be operationally wrong when its assumptions are violated.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

from inventory_opt.config import ABC_A_THRESHOLD, ABC_B_THRESHOLD, XYZ_X_THRESHOLD, XYZ_Y_THRESHOLD


def service_level_z(service_level: float) -> float:
    """Return the standard-normal quantile for a cycle service level.

    Examples: 0.90 -> 1.2816, 0.95 -> 1.6449, 0.99 -> 2.3263.
    """

    if not 0 < service_level < 1:
        raise ValueError(f"service_level must be in (0, 1), got {service_level!r}")
    return NormalDist().inv_cdf(service_level)


def economic_order_quantity(
    annual_demand: float,
    ordering_cost: float,
    unit_cost: float,
    holding_cost_pct: float,
) -> float:
    """Classic EOQ: sqrt(2 * D * S / H), with H = unit_cost * holding_rate.

    Assumptions: known constant annual demand, fixed ordering cost, carrying
    cost proportional to average cycle stock, no quantity discounts, no
    stockouts, and instantaneous (or deterministic) replenishment. Reorder
    point logic handles stochastic lead time separately.
    """

    if annual_demand < 0 or ordering_cost < 0 or unit_cost < 0 or holding_cost_pct < 0:
        raise ValueError("EOQ inputs must be non-negative")
    if annual_demand == 0 or ordering_cost == 0 or unit_cost == 0 or holding_cost_pct == 0:
        return 0.0

    annual_holding_cost_per_unit = unit_cost * holding_cost_pct
    return math.sqrt((2.0 * annual_demand * ordering_cost) / annual_holding_cost_per_unit)


def safety_stock_units(
    avg_daily_demand: float,
    daily_demand_std: float,
    avg_lead_time_days: float,
    lead_time_std_days: float,
    service_level: float,
) -> float:
    """Safety stock with variable demand and variable supplier lead time.

    SS = Z * sqrt(L_bar * sigma_D^2 + D_bar^2 * sigma_L^2)

    Assumptions: daily demand is independent and approximately normal; lead
    time is independent of demand; the planner targets a cycle service level
    (probability of no stockout per replenishment cycle). For highly
    intermittent or skewed demand, use the empirical simulation in
    ``stockout.py`` alongside this planning approximation.
    """

    inputs = (avg_daily_demand, daily_demand_std, avg_lead_time_days, lead_time_std_days)
    if any(value < 0 for value in inputs):
        raise ValueError("Safety-stock inputs must be non-negative")

    z = service_level_z(service_level)
    variance = (avg_lead_time_days * daily_demand_std**2) + (
        avg_daily_demand**2 * lead_time_std_days**2
    )
    return z * math.sqrt(max(variance, 0.0))


def reorder_point_units(
    avg_daily_demand: float,
    avg_lead_time_days: float,
    safety_stock: float,
) -> float:
    """ROP = expected demand during lead time + safety stock."""

    if min(avg_daily_demand, avg_lead_time_days, safety_stock) < 0:
        raise ValueError("ROP inputs must be non-negative")
    return avg_daily_demand * avg_lead_time_days + safety_stock


def annual_holding_cost_per_unit(unit_cost: float, holding_cost_pct: float) -> float:
    """Annual cost to carry one unit (H in the EOQ formula)."""

    if unit_cost < 0 or holding_cost_pct < 0:
        raise ValueError("Cost inputs must be non-negative")
    return unit_cost * holding_cost_pct


def assign_abc_classes(
    annual_consumption_value: pd.Series,
    a_threshold: float = ABC_A_THRESHOLD,
    b_threshold: float = ABC_B_THRESHOLD,
) -> pd.Series:
    """Classify SKUs by cumulative annual consumption value.

    Sorting is descending by value and, for deterministic ties, by the Series
    index. A SKU is A when cumulative value *before* that SKU is below 80%,
    B below 95%, and C otherwise. This guarantees class A contributes at least
    80% of total value (it may cross the boundary slightly).

    This is the value-based Pareto interpretation, not a fixed 20% SKU count.
    """

    if not 0 < a_threshold < b_threshold < 1:
        raise ValueError("Thresholds must satisfy 0 < A < B < 1")

    values = annual_consumption_value.astype(float).fillna(0).clip(lower=0)
    result = pd.Series("C", index=values.index, dtype="object")
    total = float(values.sum())
    if total <= 0 or values.empty:
        return result

    ordered = values.sort_values(ascending=False, kind="mergesort")
    value_before = ordered.cumsum().shift(1).fillna(0)
    share_before = value_before / total

    classes = np.where(
        share_before < a_threshold,
        "A",
        np.where(share_before < b_threshold, "B", "C"),
    )
    result.loc[ordered.index] = classes
    return result


def assign_xyz_classes(
    demand_cv: pd.Series,
    x_threshold: float = XYZ_X_THRESHOLD,
    y_threshold: float = XYZ_Y_THRESHOLD,
) -> pd.Series:
    """Classify demand volatility: X <= 0.50, Y <= 1.00, Z > 1.00.

    CV uses calendar-complete weekly demand, including zero weeks. Including
    zeros is essential for intermittent SKUs; using only selling days would
    hide their volatility. A zero-mean SKU is classified Z because demand is
    non-operational rather than stable.
    """

    if not 0 < x_threshold < y_threshold:
        raise ValueError("XYZ thresholds must satisfy 0 < X < Y")

    cv = demand_cv.astype(float)
    result = pd.Series("Z", index=cv.index, dtype="object")
    result.loc[cv.notna() & (cv <= y_threshold)] = "Y"
    result.loc[cv.notna() & (cv <= x_threshold)] = "X"
    return result


def weekly_demand_cv(mean_units: float, std_units: float) -> float:
    """Coefficient of variation; returns NaN for zero demand."""

    if mean_units <= 0:
        return float("nan")
    return std_units / mean_units
