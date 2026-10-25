"""Demand forecasting with statsmodels Exponential Smoothing / Holt-Winters.

Design choices
---------------
* Monthly demand is used because the portfolio has 24 months of history, enough
  for one annual seasonal cycle to be estimated and validated on a 3-month
  holdout. Weekly data is retained for operational trend visuals.
* Model complexity is selected by AIC, not by the best holdout score. The
  holdout is untouched for accuracy reporting, avoiding optimistic leakage.
* Forecast intervals use the in-sample one-step RMSE scaled by sqrt(h). This is
  a pragmatic approximation; a production system should use ETS simulation
  intervals or conformal prediction calibrated on rolling backtests.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

LOGGER = logging.getLogger(__name__)

MODEL_FAMILIES = {
    "seasonal": [
        (
            "Holt-Winters additive (damped)",
            dict(trend="add", damped_trend=True, seasonal="add", seasonal_periods=12),
        ),
        (
            "Damped trend ETS",
            dict(trend="add", damped_trend=True),
        ),
        (
            "Simple exponential smoothing",
            dict(trend=None, seasonal=None),
        ),
    ],
    "steady": [
        (
            "Damped trend ETS",
            dict(trend="add", damped_trend=True),
        ),
        (
            "Linear trend ETS",
            dict(trend="add", damped_trend=False),
        ),
        (
            "Simple exponential smoothing",
            dict(trend=None, seasonal=None),
        ),
    ],
    "intermittent": [
        (
            "Simple exponential smoothing",
            dict(trend=None, seasonal=None),
        ),
        (
            "Damped trend ETS",
            dict(trend="add", damped_trend=True),
        ),
    ],
}


@dataclass
class ForecastArtifacts:
    forecasts: pd.DataFrame
    monthly_history: pd.DataFrame
    accuracy: pd.DataFrame
    accuracy_summary: dict[str, float]


@dataclass
class _FittedForecast:
    values: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    model: str
    aic: float
    residual_sigma: float


def build_monthly_demand(
    sales: pd.DataFrame,
    products: pd.DataFrame,
    start_date: pd.Timestamp | str,
    end_date: pd.Timestamp | str,
) -> pd.DataFrame:
    """Calendar-complete monthly demand for every active SKU."""

    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    sales = sales.copy()
    sales["sale_date"] = pd.to_datetime(sales["sale_date"]).dt.normalize()
    sales["month_start"] = sales["sale_date"].dt.to_period("M").dt.start_time

    active_ids = products.loc[products["is_active"], "product_id"].astype(int).tolist()
    months = pd.date_range(start.replace(day=1), end.replace(day=1), freq="MS")
    grid = pd.MultiIndex.from_product(
        [active_ids, months], names=["product_id", "month_start"]
    ).to_frame(index=False)
    actuals = (
        sales.groupby(["product_id", "month_start"], as_index=False)
        .agg(actual_units=("quantity_sold", "sum"))
    )
    monthly = grid.merge(
        actuals, on=["product_id", "month_start"], how="left", validate="one_to_one"
    )
    monthly["actual_units"] = monthly["actual_units"].fillna(0).astype(int)
    pattern_map = products.set_index("product_id")["demand_pattern"].to_dict()
    monthly["demand_pattern"] = monthly["product_id"].map(pattern_map)
    return monthly.sort_values(["product_id", "month_start"]).reset_index(drop=True)


def run_forecasting(
    sales: pd.DataFrame,
    products: pd.DataFrame,
    start_date: pd.Timestamp | str,
    end_date: pd.Timestamp | str,
    horizon_months: int = 3,
    holdout_months: int = 3,
) -> ForecastArtifacts:
    """Fit future forecasts and evaluate the same process on a holdout."""

    monthly = build_monthly_demand(sales, products, start_date, end_date)
    pattern_map = products.set_index("product_id")["demand_pattern"].to_dict()
    name_map = products.set_index("product_id")["sku"].to_dict()

    forecast_rows: list[dict[str, Any]] = []
    accuracy_rows: list[dict[str, Any]] = []

    for product_id, group in monthly.groupby("product_id", sort=True):
        group = group.sort_values("month_start").reset_index(drop=True)
        series = group["actual_units"].to_numpy(dtype=float)
        pattern = str(pattern_map[product_id])
        sku = str(name_map[product_id])

        fitted = _fit_forecast(series, pattern, horizon_months)
        future_months = pd.date_range(
            group["month_start"].max() + pd.offsets.MonthBegin(1),
            periods=horizon_months,
            freq="MS",
        )
        for step, (month_start, value, lower, upper) in enumerate(
            zip(future_months, fitted.values, fitted.lower, fitted.upper), start=1
        ):
            days_in_month = month_start.days_in_month
            forecast_qty = round(max(float(value), 0.0), 2)
            forecast_rows.append(
                {
                    "product_id": int(product_id),
                    "sku": sku,
                    "demand_pattern": pattern,
                    "forecast_month": month_start,
                    "horizon_step": step,
                    "forecast_units": forecast_qty,
                    "lower_95_units": round(max(float(lower), 0.0), 2),
                    "upper_95_units": round(max(float(upper), 0.0), 2),
                    "model": fitted.model,
                    "model_aic": round(fitted.aic, 2),
                    "residual_sigma_monthly": round(fitted.residual_sigma, 2),
                    "forecast_daily_rate": round(forecast_qty / days_in_month, 4),
                    "forecast_rate_std_daily": round(
                        fitted.residual_sigma / max(days_in_month, 1), 4
                    ),
                }
            )

        if len(series) > holdout_months + 6:
            train = series[:-holdout_months]
            test = series[-holdout_months:]
            holdout_fit = _fit_forecast(train, pattern, holdout_months)
            predicted = np.clip(holdout_fit.values, 0, None)
            abs_error = np.abs(test - predicted)
            actual_total = float(test.sum())
            mae = float(abs_error.mean())
            abs_error_units = float(abs_error.sum())
            signed_error_units = float(predicted.sum() - test.sum())
            wape = abs_error_units / actual_total if actual_total > 0 else np.nan
            bias = signed_error_units / actual_total if actual_total > 0 else np.nan
            accuracy_rows.append(
                {
                    "product_id": int(product_id),
                    "sku": sku,
                    "demand_pattern": pattern,
                    "holdout_months": holdout_months,
                    "final_model": fitted.model,
                    "holdout_model": holdout_fit.model,
                    "actual_holdout_units": int(test.sum()),
                    "forecast_holdout_units": round(float(predicted.sum()), 2),
                    "abs_error_units": round(abs_error_units, 2),
                    "signed_error_units": round(signed_error_units, 2),
                    "mae_units": round(mae, 2),
                    "wape": round(wape, 4) if np.isfinite(wape) else np.nan,
                    "bias_pct": round(bias, 4) if np.isfinite(bias) else np.nan,
                }
            )

    forecasts = pd.DataFrame(forecast_rows)
    accuracy = pd.DataFrame(accuracy_rows)
    if accuracy.empty:
        summary = {
            "weighted_wape": float("nan"),
            "median_sku_wape": float("nan"),
            "weighted_bias_pct": float("nan"),
            "skus_evaluated": 0,
        }
    else:
        actual_total = float(accuracy["actual_holdout_units"].sum())
        abs_total = float(accuracy["abs_error_units"].sum())
        signed_total = float(accuracy["signed_error_units"].sum())
        valid_wape = accuracy["wape"].dropna()
        summary = {
            "weighted_wape": round(abs_total / actual_total, 4) if actual_total > 0 else float("nan"),
            "median_sku_wape": round(float(valid_wape.median()), 4) if not valid_wape.empty else float("nan"),
            "weighted_bias_pct": round(signed_total / actual_total, 4)
            if actual_total > 0
            else float("nan"),
            "skus_evaluated": int(len(accuracy)),
        }

    LOGGER.info(
        "Forecast complete: %s SKU-month forecasts, weighted holdout WAPE %.3f",
        len(forecasts),
        summary["weighted_wape"],
    )
    return ForecastArtifacts(
        forecasts=forecasts,
        monthly_history=monthly,
        accuracy=accuracy,
        accuracy_summary=summary,
    )


def forecast_daily_rate_for_horizon(
    sku_forecast: pd.DataFrame,
    as_of: pd.Timestamp | str,
    horizon_days: int,
) -> tuple[float, float, float]:
    """Convert monthly forecasts to expected units over a lead-time horizon.

    Returns (expected units, expected units/day, uncertainty in the daily rate).
    Each day in the horizon is assigned to its forecast month; if a lead time
    exceeds the forecast horizon, the last month's daily rate is extrapolated
    for the remaining days.
    """

    if horizon_days <= 0:
        raise ValueError("horizon_days must be positive")
    as_of_ts = pd.Timestamp(as_of).normalize()
    work = sku_forecast.copy()
    work["forecast_month"] = pd.to_datetime(work["forecast_month"]).dt.to_period("M")
    work = work.sort_values("forecast_month")
    if work.empty:
        raise ValueError("No forecast rows supplied")

    monthly_inputs = {
        row.forecast_month: (
            float(row.forecast_units),
            int(row.forecast_month.days_in_month),
            float(row.forecast_rate_std_daily),
        )
        for row in work.itertuples(index=False)
    }
    first_month = work["forecast_month"].min()
    last_month = work["forecast_month"].max()
    total_units = 0.0
    weighted_rate_std = 0.0

    for day_offset in range(1, horizon_days + 1):
        current_day = (as_of_ts + pd.Timedelta(days=day_offset)).to_period("M")
        lookup_month = min(max(current_day, first_month), last_month)
        forecast_units, days_in_month, rate_std = monthly_inputs[lookup_month]
        total_units += forecast_units / days_in_month
        weighted_rate_std += rate_std

    daily_rate = total_units / horizon_days
    daily_rate_std = weighted_rate_std / horizon_days
    return total_units, daily_rate, daily_rate_std


def _fit_forecast(series: np.ndarray, pattern: str, horizon: int) -> _FittedForecast:
    """Fit the AIC-best ETS specification, with a robust naive fallback."""

    values = np.asarray(series, dtype=float)
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    values = np.clip(values, 0, None)

    if len(values) < 6 or np.allclose(values, 0):
        return _fallback_forecast(values, horizon)

    candidates = MODEL_FAMILIES.get(pattern, MODEL_FAMILIES["steady"])
    best: _FittedForecast | None = None
    best_aic = float("inf")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for model_name, kwargs in candidates:
            try:
                model = ExponentialSmoothing(
                    values,
                    initialization_method="estimated",
                    use_boxcox=False,
                    **kwargs,
                )
                result = model.fit(optimized=True, remove_bias=False)
                aic = float(result.aic)
                if not np.isfinite(aic):
                    aic = float("inf")
                forecast_values = np.asarray(result.forecast(horizon), dtype=float)
                residual = np.asarray(result.resid, dtype=float)
                residual = residual[np.isfinite(residual)]
                if residual.size == 0:
                    residual_sigma = float(np.std(values))
                else:
                    residual_sigma = float(np.sqrt(np.mean(np.square(residual))))
                if not np.isfinite(residual_sigma):
                    residual_sigma = 0.0

                h = np.arange(1, horizon + 1, dtype=float)
                interval_width = 1.959963984540054 * residual_sigma * np.sqrt(h)
                candidate = _FittedForecast(
                    values=np.clip(forecast_values, 0, None),
                    lower=np.clip(forecast_values - interval_width, 0, None),
                    upper=np.clip(forecast_values + interval_width, 0, None),
                    model=model_name,
                    aic=aic,
                    residual_sigma=residual_sigma,
                )
                if best is None or aic < best_aic:
                    best = candidate
                    best_aic = aic
            except Exception as exc:  # statsmodels raises several numerical errors
                LOGGER.debug("Candidate %s failed for pattern %s: %s", model_name, pattern, exc)

    if best is None:
        return _fallback_forecast(values, horizon)
    return best


def _fallback_forecast(values: np.ndarray, horizon: int) -> _FittedForecast:
    """Naive 12-month average with residual-based intervals."""

    if values.size == 0:
        values = np.array([0.0])
    lookback = values[-12:] if values.size >= 12 else values
    mean_value = float(np.mean(lookback))
    residuals = lookback - mean_value
    sigma = float(np.sqrt(np.mean(np.square(residuals)))) if residuals.size else 0.0
    forecast = np.repeat(max(mean_value, 0.0), horizon)
    h = np.arange(1, horizon + 1, dtype=float)
    interval = 1.959963984540054 * sigma * np.sqrt(h)
    return _FittedForecast(
        values=forecast,
        lower=np.clip(forecast - interval, 0, None),
        upper=np.clip(forecast + interval, 0, None),
        model="Naive 12-month average (fallback)",
        aic=float("nan"),
        residual_sigma=sigma,
    )
