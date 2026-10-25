"""Generate the 24-month synthetic supply-chain dataset."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from inventory_opt.config import (  # noqa: E402
    DEFAULT_END_DATE,
    DEFAULT_PRODUCT_COUNT,
    DEFAULT_SEED,
    DEFAULT_START_DATE,
    DEFAULT_SUPPLIER_COUNT,
)
from inventory_opt.generation import GeneratorConfig, generate_dataset  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START_DATE)
    parser.add_argument("--end", type=date.fromisoformat, default=DEFAULT_END_DATE)
    parser.add_argument("--products", type=int, default=DEFAULT_PRODUCT_COUNT)
    parser.add_argument("--suppliers", type=int, default=DEFAULT_SUPPLIER_COUNT)
    parser.add_argument("--understocked-skus", type=int, default=8)
    parser.add_argument("--freeze-days", type=int, default=35)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    root = Path(__file__).resolve().parent.parent
    output_dir = args.output_dir or root / "data" / "raw"
    config = GeneratorConfig(
        start_date=args.start,
        end_date=args.end,
        n_products=args.products,
        n_suppliers=args.suppliers,
        seed=args.seed,
        understocked_skus=args.understocked_skus,
        end_order_freeze_days=args.freeze_days,
    )
    dataset = generate_dataset(config)
    dataset.write(output_dir)
    logging.info("Wrote raw dataset to %s", output_dir)
    logging.info("Manifest: %s", dataset.manifest)


if __name__ == "__main__":
    main()
