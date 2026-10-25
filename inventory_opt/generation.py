"""Deterministic synthetic supply-chain data generator.

The generator creates an internally consistent operating history:

1. Supplier and product master data.
2. 24 months of daily demand under steady, seasonal, or intermittent archetypes.
3. A daily inventory policy with weekly replenishment, variable lead times, lost
   sales when stock is exhausted, and POs that can still be open at the horizon.
4. Weekly inventory snapshots plus a final snapshot at the analysis date.

A deliberate subset of high-velocity SKUs stops placing orders near the horizon.
This stress scenario exercises the stockout/reorder dashboard without hand-
editing the outputs. It is recorded in the generation manifest.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from inventory_opt.config import (
    DEFAULT_END_DATE,
    DEFAULT_PRODUCT_COUNT,
    DEFAULT_SEED,
    DEFAULT_START_DATE,
    DEFAULT_SUPPLIER_COUNT,
)
from inventory_opt.inventory import (
    economic_order_quantity,
    reorder_point_units,
    safety_stock_units,
)

LOGGER = logging.getLogger(__name__)

CATEGORIES = (
    "Electronics",
    "Packaging",
    "Hardware",
    "Consumables",
    "Industrial Components",
    "Safety Equipment",
)

CATEGORY_ITEMS: dict[str, tuple[str, ...]] = {
    "Electronics": (
        "Wireless Sensor",
        "Controller Board",
        "Power Relay",
        "LED Driver",
        "Signal Cable",
    ),
    "Packaging": (
        "Corrugated Carton",
        "Pallet Wrap",
        "Foam Insert",
        "Shipping Label Roll",
        "Poly Mailer",
    ),
    "Hardware": (
        "Hex Bolt Pack",
        "Flange Bearing",
        "Lock Washer",
        "Steel Bracket",
        "Threaded Rod",
    ),
    "Consumables": (
        "Nitrile Gloves",
        "Safety Glasses",
        "Shop Towel Roll",
        "Adhesive Tape",
        "Cleaning Solvent",
    ),
    "Industrial Components": (
        "Hydraulic Hose",
        "Pneumatic Valve",
        "Gear Coupling",
        "Drive Belt",
        "Pressure Gauge",
    ),
    "Safety Equipment": (
        "Hi-Vis Vest",
        "Respirator Cartridge",
        "Hard Hat",
        "Ear Protection",
        "First Aid Kit",
    ),
}

ADJECTIVES = (
    "Compact",
    "Heavy-Duty",
    "Precision",
    "Industrial",
    "Modular",
    "High-Temp",
    "Eco",
    "Reinforced",
    "Standard",
    "Premium",
)

SUPPLIER_NAMES = (
    "Northwind Components",
    "Sierra Plastics",
    "Orion Metals",
    "BlueLine Packaging",
    "Atlas Fasteners",
    "Vertex Electronics",
    "Meridian Textiles",
    "Cascade Chemicals",
    "Summit Industrial",
    "Harbor Safety",
    "Redwood Paper",
    "Apex Optics",
)

COUNTRY_CODES = ("US", "CA", "MX", "DE", "VN", "IN", "CN", "GB", "PL", "MY", "JP", "BR")
CHANNELS = ("Retail", "Wholesale", "Online")


@dataclass(frozen=True)
class GeneratorConfig:
    start_date: date = DEFAULT_START_DATE
    end_date: date = DEFAULT_END_DATE
    n_products: int = DEFAULT_PRODUCT_COUNT
    n_suppliers: int = DEFAULT_SUPPLIER_COUNT
    seed: int = DEFAULT_SEED
    understocked_skus: int = 8
    end_order_freeze_days: int = 35

    def validate(self) -> None:
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")
        if self.n_products < 1:
            raise ValueError("n_products must be positive")
        if self.n_suppliers < 1:
            raise ValueError("n_suppliers must be positive")
        if self.n_suppliers > len(SUPPLIER_NAMES):
            raise ValueError(f"n_suppliers cannot exceed {len(SUPPLIER_NAMES)}")
        if not 0 <= self.understocked_skus <= self.n_products:
            raise ValueError("understocked_skus must be between 0 and n_products")
        if self.end_order_freeze_days < 0:
            raise ValueError("end_order_freeze_days must be non-negative")


@dataclass
class SyntheticDataset:
    suppliers: pd.DataFrame
    products: pd.DataFrame
    sales_transactions: pd.DataFrame
    purchase_orders: pd.DataFrame
    inventory_snapshots: pd.DataFrame
    manifest: dict[str, Any] = field(default_factory=dict)

    def write(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        self.suppliers.to_csv(output_dir / "suppliers.csv", index=False)
        self.products.to_csv(output_dir / "products.csv", index=False)
        self.sales_transactions.to_csv(output_dir / "sales_transactions.csv", index=False)
        self.purchase_orders.to_csv(output_dir / "purchase_orders.csv", index=False)
        self.inventory_snapshots.to_csv(output_dir / "inventory_snapshots.csv", index=False)
        with (output_dir / "generation_manifest.json").open("w", encoding="utf-8") as handle:
            json.dump(self.manifest, handle, indent=2, default=str)


def generate_dataset(config: GeneratorConfig | None = None) -> SyntheticDataset:
    """Generate all core CSVs in memory from a single deterministic seed."""

    cfg = config or GeneratorConfig()
    cfg.validate()
    rng = np.random.default_rng(cfg.seed)
    dates = pd.date_range(cfg.start_date, cfg.end_date, freq="D")
    if len(dates) < 60:
        raise ValueError("The generator requires at least 60 days of history")

    suppliers = _generate_suppliers(cfg, rng)
    products, profiles = _generate_products(cfg, rng, suppliers)
    supplier_by_id = suppliers.set_index("supplier_id").to_dict(orient="index")

    understocked_ids = _select_understocked_skus(cfg, profiles, rng)
    freeze_start = cfg.end_date - timedelta(days=cfg.end_order_freeze_days)

    planned_demands: dict[int, np.ndarray] = {}
    for product_id in products["product_id"]:
        planned_demands[int(product_id)] = _simulate_planned_demand(
            profiles[int(product_id)], dates, rng
        )

    sales_daily: list[tuple[int, date, int]] = []
    po_rows: list[dict[str, Any]] = []
    snapshot_rows: list[dict[str, Any]] = []
    lost_sales_units = 0

    for product in products.itertuples(index=False):
        product_id = int(product.product_id)
        supplier = supplier_by_id[int(product.supplier_id)]
        planned = planned_demands[product_id]
        daily_mean = float(planned.mean())
        daily_std = float(planned.std(ddof=1))
        promised_lead = int(supplier["promised_lead_time_days"])
        lead_sigma = float(supplier["lead_time_sigma_days"])
        target = float(product.target_service_level)

        safety_stock = safety_stock_units(
            daily_mean,
            daily_std,
            promised_lead,
            lead_sigma,
            target,
        )
        rop = reorder_point_units(daily_mean, promised_lead, safety_stock)
        annual_demand = daily_mean * 365
        raw_eoq = economic_order_quantity(
            annual_demand,
            float(product.ordering_cost),
            float(product.unit_cost),
            float(product.holding_cost_pct),
        )
        # Practical guardrails: respect the supplier minimum and do not let a
        # theoretical EOQ represent more than ~120 days of demand. The raw EOQ
        # remains available in the analytics output for audit.
        practical_eoq = float(
            np.clip(
                raw_eoq,
                product.min_order_qty,
                max(product.min_order_qty, annual_demand / 3.0),
            )
        )
        order_up_to = rop + practical_eoq
        on_hand = int(
            np.ceil(max(rop + practical_eoq * 0.75, daily_mean * promised_lead + 1))
        )
        inbound = 0
        receipts_by_date: dict[date, list[int]] = {}
        open_order_indexes: set[int] = set()
        freeze_orders = product_id in understocked_ids and cfg.end_order_freeze_days > 0

        for day_index, timestamp in enumerate(dates):
            day = timestamp.date()

            for po_index in receipts_by_date.pop(day, []):
                row = po_rows[po_index]
                if row["status"] == "OPEN":
                    received_qty = row["quantity_ordered"]
                    on_hand += received_qty
                    inbound -= received_qty
                    row["received_date"] = day
                    row["quantity_received"] = received_qty
                    row["status"] = "RECEIVED"
                    open_order_indexes.discard(po_index)

            desired = int(planned[day_index])
            sold = min(on_hand, desired)
            lost_sales_units += max(desired - sold, 0)
            on_hand -= sold
            if sold > 0:
                sales_daily.append((product_id, day, sold))

            can_order = timestamp.weekday() < 5
            if freeze_orders and day >= freeze_start:
                can_order = False

            inventory_position = on_hand + inbound
            if can_order and inventory_position <= rop:
                quantity = int(
                    np.ceil(max(practical_eoq, order_up_to - inventory_position))
                )
                quantity = max(quantity, int(product.min_order_qty))
                actual_lead = _sample_actual_lead_days(
                    promised_lead,
                    lead_sigma,
                    float(supplier["on_time_target_pct"]),
                    rng,
                )
                promised_date = day + timedelta(days=promised_lead)
                expected_receipt = _next_business_day(day + timedelta(days=actual_lead))

                po_index = len(po_rows)
                po_rows.append(
                    {
                        "po_id": po_index + 1,
                        "po_number": f"PO-{po_index + 1:06d}",
                        "product_id": product_id,
                        "supplier_id": int(product.supplier_id),
                        "order_date": day,
                        "promised_date": promised_date,
                        "received_date": None,
                        "quantity_ordered": quantity,
                        "quantity_received": 0,
                        "unit_cost": round(float(product.unit_cost), 2),
                        "status": "OPEN",
                        "quoted_lead_time_days": promised_lead,
                        "notes": None,
                    }
                )
                inbound += quantity
                open_order_indexes.add(po_index)
                if expected_receipt <= cfg.end_date:
                    receipts_by_date.setdefault(expected_receipt, []).append(po_index)

            if timestamp.weekday() == 0 or day == cfg.end_date:
                snapshot_rows.append(
                    {
                        "snapshot_date": day,
                        "product_id": product_id,
                        "on_hand_units": int(on_hand),
                        "inbound_units": int(inbound),
                    }
                )

    for po_index in open_order_indexes:
        po_rows[po_index]["notes"] = "Open at analysis horizon"

    sales = _build_transactions(sales_daily, products, rng)
    purchase_orders = pd.DataFrame(po_rows).sort_values(["order_date", "po_id"]).reset_index(drop=True)
    snapshots = pd.DataFrame(snapshot_rows).sort_values(
        ["snapshot_date", "product_id"]
    ).reset_index(drop=True)

    manifest = {
        "seed": cfg.seed,
        "start_date": cfg.start_date.isoformat(),
        "end_date": cfg.end_date.isoformat(),
        "days": len(dates),
        "product_count": int(len(products)),
        "supplier_count": int(len(suppliers)),
        "sales_transaction_count": int(len(sales)),
        "purchase_order_count": int(len(purchase_orders)),
        "inventory_snapshot_count": int(len(snapshots)),
        "open_purchase_orders_at_horizon": int((purchase_orders["status"] == "OPEN").sum()),
        "planned_units": int(sum(int(planned.sum()) for planned in planned_demands.values())),
        "fulfilled_units": int(sales["quantity_sold"].sum()),
        "lost_sales_units": int(lost_sales_units),
        "demand_patterns": products["demand_pattern"].value_counts().to_dict(),
        "understocked_skus": [
            products.loc[products["product_id"] == pid, "sku"].iloc[0]
            for pid in sorted(understocked_ids)
        ],
        "end_order_freeze_days": cfg.end_order_freeze_days,
        "notes": (
            "A subset of high-velocity SKUs intentionally stops replenishing near the "
            "analysis horizon to create realistic reorder/stockout exceptions."
        ),
    }

    LOGGER.info(
        "Generated %s SKUs, %s sales rows, %s POs, %s snapshots",
        len(products),
        len(sales),
        len(purchase_orders),
        len(snapshots),
    )
    return SyntheticDataset(
        suppliers=suppliers,
        products=products,
        sales_transactions=sales,
        purchase_orders=purchase_orders,
        inventory_snapshots=snapshots,
        manifest=manifest,
    )


def _generate_suppliers(cfg: GeneratorConfig, rng: np.random.Generator) -> pd.DataFrame:
    promised_choices = np.array([7, 10, 12, 14, 18, 21, 25, 30, 35, 42, 45, 49])
    promised = rng.choice(promised_choices[: cfg.n_suppliers], size=cfg.n_suppliers, replace=False)
    on_time_targets = rng.uniform(0.84, 0.96, size=cfg.n_suppliers)
    rows = []
    for index in range(cfg.n_suppliers):
        lead = int(promised[index])
        variability = float(np.clip(lead * rng.uniform(0.07, 0.19), 0.8, 6.5))
        rows.append(
            {
                "supplier_id": index + 1,
                "supplier_name": SUPPLIER_NAMES[index],
                "country_code": COUNTRY_CODES[index],
                "promised_lead_time_days": lead,
                "lead_time_sigma_days": round(variability, 2),
                "on_time_target_pct": round(float(on_time_targets[index]), 4),
            }
        )
    return pd.DataFrame(rows).sort_values("supplier_id").reset_index(drop=True)


def _generate_products(
    cfg: GeneratorConfig,
    rng: np.random.Generator,
    suppliers: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[int, dict[str, Any]]]:
    n_steady = int(round(cfg.n_products * 0.35))
    n_seasonal = int(round(cfg.n_products * 0.30))
    n_intermittent = cfg.n_products - n_steady - n_seasonal
    patterns = (
        ["steady"] * n_steady
        + ["seasonal"] * n_seasonal
        + ["intermittent"] * n_intermittent
    )
    rng.shuffle(patterns)

    categories = [CATEGORIES[i % len(CATEGORIES)] for i in range(cfg.n_products)]
    rng.shuffle(categories)
    supplier_ids = rng.integers(1, cfg.n_suppliers + 1, size=cfg.n_products)
    service_levels = rng.choice([0.90, 0.95, 0.99], size=cfg.n_products, p=[0.20, 0.60, 0.20])
    min_order_choices = np.array([1, 5, 10, 25, 50])
    min_order_probs = np.array([0.15, 0.25, 0.30, 0.20, 0.10])

    rows: list[dict[str, Any]] = []
    profiles: dict[int, dict[str, Any]] = {}
    for index in range(cfg.n_products):
        product_id = index + 1
        category = categories[index]
        pattern = patterns[index]
        item = CATEGORY_ITEMS[category][product_id % len(CATEGORY_ITEMS[category])]
        adjective = ADJECTIVES[(product_id * 3) % len(ADJECTIVES)]
        unit_cost = float(np.clip(rng.lognormal(mean=3.2, sigma=0.85), 4.5, 750.0))
        margin = float(rng.uniform(1.30, 2.20))
        unit_price = round(unit_cost * margin, 2)
        holding_cost_pct = round(float(rng.uniform(0.18, 0.32)), 4)
        ordering_cost = round(float(rng.uniform(55, 375)), 2)
        min_order_qty = int(rng.choice(min_order_choices, p=min_order_probs))
        target_service_level = float(rng.choice(service_levels))

        profile = {
            "pattern": pattern,
            "base_daily": float(np.clip(rng.lognormal(mean=0.75, sigma=0.85), 0.18, 18.0)),
            "weekend_factor": float(rng.uniform(0.35, 0.82)),
            "trend_total": float(rng.uniform(-0.12, 0.20)),
            "seasonal_amplitude": float(rng.uniform(0.35, 0.72)),
            "peak_day": int(rng.integers(1, 366)),
            "dispersion": float(rng.uniform(4.0, 14.0)),
            "promo_rate": float(rng.uniform(0.008, 0.020)),
            "promo_lift": float(rng.uniform(1.7, 3.0)),
            "event_probability": float(rng.uniform(0.04, 0.28)),
            "event_mean": float(rng.uniform(1.5, 8.0)),
        }
        if pattern == "steady":
            profile["seasonal_amplitude"] = float(rng.uniform(0.03, 0.12))
        if pattern == "intermittent":
            profile["promo_rate"] = 0.004
            profile["event_mean"] = float(rng.uniform(1.5, 10.0))

        expected_weekday_factor = 5 / 7 + (2 / 7) * profile["weekend_factor"]
        if pattern == "intermittent":
            expected_daily = (
                profile["event_probability"] * profile["event_mean"] * 0.9
            )
        else:
            expected_daily = profile["base_daily"] * expected_weekday_factor
        profile["expected_daily"] = expected_daily

        rows.append(
            {
                "product_id": product_id,
                "sku": f"SKU-{product_id:04d}",
                "product_name": f"{adjective} {item} {100 + product_id}",
                "category": category,
                "demand_pattern": pattern,
                "supplier_id": int(supplier_ids[index]),
                "unit_cost": round(unit_cost, 2),
                "unit_price": unit_price,
                "holding_cost_pct": holding_cost_pct,
                "ordering_cost": ordering_cost,
                "min_order_qty": min_order_qty,
                "target_service_level": target_service_level,
                "is_active": True,
            }
        )
        profiles[product_id] = profile

    return pd.DataFrame(rows), profiles


def _select_understocked_skus(
    cfg: GeneratorConfig,
    profiles: dict[int, dict[str, Any]],
    rng: np.random.Generator,
) -> set[int]:
    if cfg.understocked_skus == 0:
        return set()
    ranked = sorted(
        profiles,
        key=lambda product_id: profiles[product_id]["expected_daily"],
        reverse=True,
    )
    candidate_pool = ranked[: max(cfg.understocked_skus * 3, min(len(ranked), 20))]
    selected = rng.choice(
        candidate_pool,
        size=min(cfg.understocked_skus, len(candidate_pool)),
        replace=False,
    )
    return {int(product_id) for product_id in selected}


def _simulate_planned_demand(
    profile: dict[str, Any],
    dates: pd.DatetimeIndex,
    rng: np.random.Generator,
) -> np.ndarray:
    n_days = len(dates)
    day_of_week = dates.dayofweek.to_numpy()
    day_of_year = dates.dayofyear.to_numpy()
    weekend = day_of_week >= 5
    weekday_factor = np.where(weekend, profile["weekend_factor"], 1.0)
    trend = np.linspace(
        1.0 - profile["trend_total"] / 2.0,
        1.0 + profile["trend_total"] / 2.0,
        n_days,
    )
    seasonality = 1.0 + profile["seasonal_amplitude"] * np.cos(
        2.0 * np.pi * (day_of_year - profile["peak_day"]) / 365.25
    )
    seasonality = np.clip(seasonality, 0.20, 1.9)

    if profile["pattern"] == "intermittent":
        event_probability = profile["event_probability"] * np.where(weekend, 0.55, 1.0)
        events = rng.random(n_days) < event_probability
        event_qty = _negative_binomial(
            np.full(n_days, profile["event_mean"]),
            dispersion=2.2,
            rng=rng,
        )
        demand = np.where(events, event_qty, 0)
        promo_events = rng.random(n_days) < profile["promo_rate"]
        demand = np.where(promo_events & events, np.maximum(1, np.round(demand * profile["promo_lift"])), demand)
    else:
        base_rate = (
            profile["base_daily"]
            * weekday_factor
            * seasonality
            * trend
        )
        promo_events = rng.random(n_days) < profile["promo_rate"]
        base_rate = np.where(promo_events, base_rate * profile["promo_lift"], base_rate)
        demand = _negative_binomial(
            base_rate,
            dispersion=profile["dispersion"],
            rng=rng,
        )

    return demand.astype(int)


def _negative_binomial(
    mean: np.ndarray,
    dispersion: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Negative-binomial draws with explicit mean and dispersion.

    Variance = mean + mean^2 / dispersion. Lower dispersion means more
    overdispersion, which creates realistic demand spikes without using an
    unrealistic pure Poisson process.
    """

    mean = np.maximum(mean, 0.0)
    result = np.zeros_like(mean, dtype=int)
    positive = mean > 1e-9
    if positive.any():
        p = dispersion / (dispersion + mean[positive])
        result[positive] = rng.negative_binomial(dispersion, p)
    return result


def _sample_actual_lead_days(
    promised_days: int,
    sigma_days: float,
    on_time_target: float,
    rng: np.random.Generator,
) -> int:
    """Sample a promised lead time with an on-time probability and late tail.

    On-time deliveries arrive a few days early or exactly on time. The
    (1 - on-time target) late tail is gamma-distributed; its scale grows with
    supplier variability, producing the actual-vs-promised variance that drives
    the safety-stock analysis.
    """

    if rng.random() < on_time_target:
        early_days = int(rng.integers(0, min(3, promised_days) + 1))
        return max(1, promised_days - early_days)

    late_mean = max(1.2, sigma_days * 1.15 + (1.0 - on_time_target) * 12.0)
    late_delay = max(1.0, rng.gamma(shape=2.0, scale=late_mean / 2.0))
    return int(promised_days + max(1, round(late_delay)))


def _next_business_day(value: date) -> date:
    while value.weekday() >= 5:
        value += timedelta(days=1)
    return value


def _build_transactions(
    sales_daily: list[tuple[int, date, int]],
    products: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    product_lookup = products.set_index("product_id")[
        ["sku", "unit_price"]
    ].to_dict(orient="index")
    rows: list[dict[str, Any]] = []
    sale_id = 1
    channel_choices = np.array(CHANNELS)
    channel_probs = np.array([0.42, 0.33, 0.25])

    for product_id, sale_date, quantity in sales_daily:
        if quantity <= 0:
            continue
        if quantity < 4:
            line_count = 1
        else:
            line_count = int(min(4, 1 + rng.poisson(0.85)))
        split = rng.multinomial(quantity, np.full(line_count, 1.0 / line_count))
        for line_quantity in split:
            if line_quantity <= 0:
                continue
            channel = str(rng.choice(channel_choices, p=channel_probs))
            list_price = float(product_lookup[product_id]["unit_price"])
            if channel == "Wholesale":
                multiplier = rng.uniform(0.91, 0.98)
            elif channel == "Online":
                multiplier = rng.uniform(0.97, 1.03)
            else:
                multiplier = rng.uniform(1.00, 1.08)
            rows.append(
                {
                    "sale_id": sale_id,
                    "product_id": product_id,
                    "sale_date": sale_date,
                    "quantity_sold": int(line_quantity),
                    "unit_price": round(list_price * multiplier, 2),
                    "channel": channel,
                }
            )
            sale_id += 1

    return pd.DataFrame(rows).sort_values(["sale_date", "sale_id"]).reset_index(drop=True)


def write_generation_manifest(dataset: SyntheticDataset, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "generation_manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(dataset.manifest, handle, indent=2, default=str)


__all__ = [
    "GeneratorConfig",
    "SyntheticDataset",
    "generate_dataset",
]
