"""Probabilistic stockout risk over supplier lead time.

The analytic safety-stock formula is a planning approximation. For an
operational stockout probability we simulate the two sources of uncertainty
jointly:

* Lead time ~ Gamma(mean = historical supplier mean, std = historical supplier std).
* Demand rate ~ Normal(forecast daily rate, forecast-rate standard error), floored at zero.
* Demand over lead time ~ Negative Binomial calibrated to historical daily
  dispersion, which preserves realistic burstiness for intermittent SKUs.

The probability is the share of 20,000 simulations where demand during the lead
time exceeds available inventory (on hand plus inbound promised within the
horizon). The analytic normal probability is retained for auditability.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

from inventory_opt.config import RISK_HIGH_THRESHOLD, RISK_MEDIUM_THRESHOLD, RISK_WATCH_THRESHOLD


@dataclass(frozen=True)
class StockoutRisk:
    expected_lead_time_days: float
    expected_lead_demand_units: float
    lead_demand_std_units: float
    projected_available_units: float
    projected_ending_inventory_units: float
    normal_stockout_probability: float
    stockout_probability: float
    p95_lead_demand_units: float
    risk_tier: str
    simulations: int


def estimate_stockout_risk(
    available_units: float,
    mean_daily_demand: float,
    daily_demand_std: float,
    mean_lead_time_days: float,
    lead_time_std_days: float,
    forecast_rate_std_daily: float = 0.0,
    n_simulations: int = 20_000,
    random_seed: int = 42,
) -> StockoutRisk:
    """Estimate P(demand during lead time > available inventory)."""

    if available_units < 0:
        raise ValueError("available_units must be non-negative")
    if min(mean_daily_demand, daily_demand_std, mean_lead_time_days, lead_time_std_days) < 0:
        raise ValueError("risk inputs must be non-negative")
    if mean_lead_time_days <= 0:
        raise ValueError("mean_lead_time_days must be positive")
    if n_simulations < 1_000:
        raise ValueError("n_simulations must be at least 1,000")

    rng = np.random.default_rng(random_seed)

    # Lead-time distribution: gamma is right-skewed and bounded at zero.
    if lead_time_std_days > 0:
        shape = (mean_lead_time_days / lead_time_std_days) ** 2
        scale = (lead_time_std_days**2) / mean_lead_time_days
        lead_times = rng.gamma(shape=shape, scale=scale, size=n_simulations)
        lead_times = np.clip(lead_times, 1.0, 365.0)
    else:
        lead_times = np.full(n_simulations, mean_lead_time_days, dtype=float)

    # Forecast rate uncertainty. Correlation across days is assumed perfect
    # within the horizon, so one rate draw is shared by all days in that path.
    if forecast_rate_std_daily > 0:
        demand_rates = rng.normal(
            mean_daily_demand, forecast_rate_std_daily, size=n_simulations
        )
        demand_rates = np.clip(demand_rates, 0.0, None)
    else:
        demand_rates = np.full(n_simulations, mean_daily_demand, dtype=float)

    mean_total_demand = demand_rates * lead_times
    variance_total_demand = lead_times * (daily_demand_std**2)
    excess_variance = variance_total_demand - mean_total_demand

    simulated_demand = np.zeros(n_simulations, dtype=float)
    poisson_mask = (mean_total_demand > 0) & (excess_variance <= 1e-9)
    if poisson_mask.any():
        simulated_demand[poisson_mask] = rng.poisson(
            mean_total_demand[poisson_mask]
        ).astype(float)

    nb_mask = (mean_total_demand > 0) & (excess_variance > 1e-9)
    if nb_mask.any():
        means = mean_total_demand[nb_mask]
        size = np.square(means) / excess_variance[nb_mask]
        probability = size / (size + means)
        simulated_demand[nb_mask] = rng.negative_binomial(size, probability).astype(float)

    # Analytic normal benchmark with lead-time and demand-rate uncertainty.
    expected_demand = mean_daily_demand * mean_lead_time_days
    variance = (
        mean_lead_time_days * daily_demand_std**2
        + mean_daily_demand**2 * lead_time_std_days**2
        + (mean_lead_time_days * forecast_rate_std_daily) ** 2
    )
    sigma = float(np.sqrt(max(variance, 0.0)))
    if sigma <= 1e-12:
        normal_probability = 1.0 if expected_demand > available_units else 0.0
    else:
        normal_probability = 1.0 - NormalDist().cdf(
            (available_units - expected_demand) / sigma
        )

    probability = float(np.mean(simulated_demand > available_units))
    risk_tier = classify_risk_tier(probability)
    return StockoutRisk(
        expected_lead_time_days=float(mean_lead_time_days),
        expected_lead_demand_units=float(expected_demand),
        lead_demand_std_units=sigma,
        projected_available_units=float(available_units),
        projected_ending_inventory_units=float(available_units - expected_demand),
        normal_stockout_probability=float(normal_probability),
        stockout_probability=probability,
        p95_lead_demand_units=float(np.quantile(simulated_demand, 0.95)),
        risk_tier=risk_tier,
        simulations=n_simulations,
    )


def classify_risk_tier(probability: float) -> str:
    """Map stockout probability to an operational severity label."""

    if probability >= RISK_HIGH_THRESHOLD:
        return "Critical"
    if probability >= RISK_MEDIUM_THRESHOLD:
        return "High"
    if probability >= RISK_WATCH_THRESHOLD:
        return "Watch"
    return "Low"


def is_stockout_risk(probability: float) -> bool:
    """Primary dashboard flag: high/critical risk."""

    return probability >= RISK_MEDIUM_THRESHOLD
