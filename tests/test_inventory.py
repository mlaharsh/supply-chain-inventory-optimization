import math

import pandas as pd
import pytest

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


def test_service_level_z_values() -> None:
    assert service_level_z(0.90) == pytest.approx(1.2815515655, rel=1e-8)
    assert service_level_z(0.95) == pytest.approx(1.6448536270, rel=1e-8)
    assert service_level_z(0.99) == pytest.approx(2.3263478740, rel=1e-8)
    with pytest.raises(ValueError):
        service_level_z(1.0)


def test_eoq_formula_and_guardrails() -> None:
    # D=12,000, S=100, H = 20 * 0.25 = 5 -> sqrt(2*12000*100/5) = 692.82
    result = economic_order_quantity(12_000, 100, 20, 0.25)
    assert result == pytest.approx(math.sqrt(480_000), rel=1e-10)
    assert annual_holding_cost_per_unit(20, 0.25) == 5
    assert economic_order_quantity(0, 100, 20, 0.25) == 0
    with pytest.raises(ValueError):
        economic_order_quantity(-1, 100, 20, 0.25)


def test_safety_stock_and_rop_against_closed_form() -> None:
    expected_variance = 5 * 4 + 10**2 * 1**2
    expected_ss = 1.6448536270 * math.sqrt(expected_variance)
    ss = safety_stock_units(10, 2, 5, 1, 0.95)
    assert ss == pytest.approx(expected_ss, rel=1e-9)
    assert reorder_point_units(10, 5, ss) == pytest.approx(50 + expected_ss)
    with pytest.raises(ValueError):
        safety_stock_units(-1, 2, 5, 1, 0.95)


def test_abc_cumulative_value_boundaries() -> None:
    values = pd.Series([800, 100, 50, 50], index=["A", "B", "C", "D"], dtype=float)
    classes = assign_abc_classes(values)
    assert classes.to_dict() == {"A": "A", "B": "B", "C": "B", "D": "C"}
    assert (values[classes == "A"].sum() / values.sum()) >= 0.80


def test_abc_handles_zero_values() -> None:
    classes = assign_abc_classes(pd.Series([0, 0], index=["A", "B"]))
    assert (classes == "C").all()


def test_xyz_thresholds_and_zero_mean() -> None:
    cv = pd.Series([0.0, 0.49, 0.50, 0.99, 1.00, 1.01, float("nan")])
    classes = assign_xyz_classes(cv)
    assert list(classes) == ["X", "X", "X", "Y", "Y", "Z", "Z"]
    assert weekly_demand_cv(0, 0) != weekly_demand_cv(0, 0)  # NaN
    assert weekly_demand_cv(10, 2) == 0.2
