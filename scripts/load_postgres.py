"""Optional PostgreSQL loader using transactional COPY.

Usage:
    python scripts/load_postgres.py --truncate
    DATABASE_URL=postgresql+psycopg2://... python scripts/load_postgres.py

The raw CSV files must already exist. The loader applies the schema and views,
then uses PostgreSQL COPY for efficient bulk inserts.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

LOGGER = logging.getLogger(__name__)

CORE_TABLES = (
    "suppliers",
    "products",
    "sales_transactions",
    "purchase_orders",
    "inventory_snapshots",
)

EXPECTED_COLUMNS = {
    "suppliers": [
        "supplier_id",
        "supplier_name",
        "country_code",
        "promised_lead_time_days",
        "lead_time_sigma_days",
        "on_time_target_pct",
    ],
    "products": [
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
        "is_active",
    ],
    "sales_transactions": [
        "sale_id",
        "product_id",
        "sale_date",
        "quantity_sold",
        "unit_price",
        "channel",
    ],
    "purchase_orders": [
        "po_id",
        "po_number",
        "product_id",
        "supplier_id",
        "order_date",
        "promised_date",
        "received_date",
        "quantity_ordered",
        "quantity_received",
        "unit_cost",
        "status",
        "quoted_lead_time_days",
        "notes",
    ],
    "inventory_snapshots": [
        "snapshot_date",
        "product_id",
        "on_hand_units",
        "inbound_units",
    ],
}

SEQUENCES = {
    "suppliers": ("supplier_id", "supplier_id"),
    "products": ("product_id", "product_id"),
    "sales_transactions": ("sale_id", "sale_id"),
    "purchase_orders": ("po_id", "po_id"),
}


def load_to_postgres(
    raw_dir: Path,
    database_url: str,
    schema_sql: Path,
    views_sql: Path | None = None,
    truncate: bool = False,
) -> dict[str, int]:
    raw_dir = raw_dir.resolve()
    for table in CORE_TABLES:
        if not (raw_dir / f"{table}.csv").exists():
            raise FileNotFoundError(f"Missing {table}.csv in {raw_dir}")

    engine = create_engine(database_url, pool_pre_ping=True)
    counts: dict[str, int] = {}
    with engine.begin() as connection:
        connection.exec_driver_sql(schema_sql.read_text(encoding="utf-8"))

        existing = {
            table: connection.execute(
                text(f"SELECT COUNT(*) FROM supply_chain.{table}")
            ).scalar_one()
            for table in CORE_TABLES
        }
        if any(existing.values()) and not truncate:
            raise RuntimeError(
                "Target tables already contain data. Re-run with --truncate only "
                "after confirming this is safe. Existing counts: "
                f"{existing}"
            )
        if truncate:
            connection.exec_driver_sql(
                "TRUNCATE TABLE supply_chain.inventory_snapshots, "
                "supply_chain.purchase_orders, supply_chain.sales_transactions, "
                "supply_chain.products, supply_chain.suppliers RESTART IDENTITY CASCADE"
            )

        raw_connection = connection.connection
        with raw_connection.cursor() as cursor:
            for table in CORE_TABLES:
                path = raw_dir / f"{table}.csv"
                with path.open("r", encoding="utf-8", newline="") as handle:
                    reader = csv.reader(handle)
                    header = next(reader)
                if header != EXPECTED_COLUMNS[table]:
                    raise ValueError(
                        f"{table}.csv header does not match the expected contract. "
                        f"Expected {EXPECTED_COLUMNS[table]}, got {header}"
                    )
                copy_sql = (
                    f"COPY supply_chain.{table} ({', '.join(header)}) "
                    "FROM STDIN WITH (FORMAT CSV, HEADER TRUE, NULL '')"
                )
                with path.open("r", encoding="utf-8", newline="") as handle:
                    cursor.copy_expert(copy_sql, handle)

            for table, (pk, sequence_name) in SEQUENCES.items():
                cursor.execute(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence('supply_chain.{table}', '{pk}'),
                        COALESCE((SELECT MAX({pk}) FROM supply_chain.{table}), 1),
                        (SELECT COUNT(*) > 0 FROM supply_chain.{table})
                    )
                    """
                )

        if views_sql is not None:
            connection.exec_driver_sql(views_sql.read_text(encoding="utf-8"))

        for table in CORE_TABLES:
            counts[table] = int(
                connection.execute(
                    text(f"SELECT COUNT(*) FROM supply_chain.{table}")
                ).scalar_one()
            )

    LOGGER.info("Loaded PostgreSQL tables: %s", counts)
    return counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load synthetic CSVs into PostgreSQL.")
    parser.add_argument("--raw-dir", type=Path, default=None)
    parser.add_argument(
        "--database-url",
        default=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg2://postgres:postgres@localhost:5432/supply_chain",
        ),
    )
    parser.add_argument("--schema-sql", type=Path, default=None)
    parser.add_argument("--views-sql", type=Path, default=None)
    parser.add_argument("--skip-views", action="store_true")
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Delete existing supply_chain data before loading",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    root = Path(__file__).resolve().parent.parent
    raw_dir = args.raw_dir or root / "data" / "raw"
    schema_sql = args.schema_sql or root / "sql" / "01_schema.sql"
    views_sql = None if args.skip_views else (args.views_sql or root / "sql" / "02_views.sql")
    load_to_postgres(
        raw_dir=raw_dir,
        database_url=args.database_url,
        schema_sql=schema_sql,
        views_sql=views_sql,
        truncate=args.truncate,
    )


if __name__ == "__main__":
    main()
