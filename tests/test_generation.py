from datetime import date

import pandas as pd

from inventory_opt.generation import GeneratorConfig, generate_dataset


def test_synthetic_dataset_is_internally_consistent(tmp_path) -> None:
    config = GeneratorConfig(
        start_date=date(2025, 1, 1),
        end_date=date(2025, 7, 1),
        n_products=8,
        n_suppliers=4,
        seed=7,
        understocked_skus=1,
        end_order_freeze_days=10,
    )
    dataset = generate_dataset(config)

    assert len(dataset.suppliers) == 4
    assert len(dataset.products) == 8
    assert dataset.products["sku"].is_unique
    assert set(dataset.products["demand_pattern"]) <= {"steady", "seasonal", "intermittent"}
    assert dataset.sales_transactions["quantity_sold"].gt(0).all()
    assert pd.to_datetime(dataset.sales_transactions["sale_date"]).between(
        pd.Timestamp(config.start_date), pd.Timestamp(config.end_date)
    ).all()
    assert len(dataset.purchase_orders) > 0
    assert set(dataset.products["product_id"]) == set(
        dataset.inventory_snapshots["product_id"]
    )
    latest = pd.to_datetime(dataset.inventory_snapshots["snapshot_date"]).max()
    assert latest == pd.Timestamp(config.end_date)
    final_rows = dataset.inventory_snapshots[
        pd.to_datetime(dataset.inventory_snapshots["snapshot_date"]) == latest
    ]
    assert len(final_rows) == 8
    assert (final_rows["on_hand_units"] >= 0).all()

    dataset.write(tmp_path)
    assert (tmp_path / "sales_transactions.csv").exists()
    assert (tmp_path / "generation_manifest.json").exists()
    assert dataset.manifest["product_count"] == 8
