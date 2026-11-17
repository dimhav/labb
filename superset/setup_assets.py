"""Registrerar datalagret (analytics.*) i Superset.

Skapar:
  * en Database-anslutning mot Postgres/warehouse
  * dataset for analytics.fct_daily_sales och analytics.dim_customers
  * ett enkelt dashboard med tva charts

Skriptet ar idempotent och kors vid varje start av Superset-tjansten.
"""
from __future__ import annotations

import json
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("setup-assets")

WAREHOUSE_DB = os.environ.get("WAREHOUSE_DB", "warehouse")
WAREHOUSE_USER = os.environ.get("WAREHOUSE_USER", "warehouse")
WAREHOUSE_PASSWORD = os.environ.get("WAREHOUSE_PASSWORD", "warehouse")

SQLALCHEMY_URI = (
    f"postgresql+psycopg2://{WAREHOUSE_USER}:{WAREHOUSE_PASSWORD}"
    f"@postgres:5432/{WAREHOUSE_DB}"
)

DATASETS = [
    {
        "table_name": "fct_daily_sales",
        "schema": "analytics",
        "metrics": [
            {
                "metric_name": "revenue",
                "expression": "SUM(revenue)",
                "verbose_name": "Intakt",
                "metric_type": "sum",
            },
            {
                "metric_name": "orders",
                "expression": "SUM(orders)",
                "verbose_name": "Ordrar",
                "metric_type": "sum",
            },
            {
                "metric_name": "units",
                "expression": "SUM(units)",
                "verbose_name": "Enheter",
                "metric_type": "sum",
            },
        ],
    },
    {
        "table_name": "dim_customers",
        "schema": "analytics",
        "metrics": [
            {
                "metric_name": "customers",
                "expression": "COUNT(*)",
                "verbose_name": "Kunder",
                "metric_type": "count",
            },
            {
                "metric_name": "lifetime_revenue",
                "expression": "SUM(lifetime_revenue)",
                "verbose_name": "Livstidsintakt",
                "metric_type": "sum",
            },
        ],
    },
]


def main() -> None:
    from superset.app import create_app

    app = create_app()
    with app.app_context():
        from superset import db
        from superset.connectors.sqla.models import SqlaTable, SqlMetric
        from superset.models.core import Database

        database = (
            db.session.query(Database)
            .filter(Database.database_name == "pgsqlmesh warehouse")
            .one_or_none()
        )
        if database is None:
            database = Database(
                database_name="pgsqlmesh warehouse",
                sqlalchemy_uri=SQLALCHEMY_URI,
                expose_in_sqllab=True,
                allow_ctas=False,
                allow_cvas=False,
            )
            db.session.add(database)
            db.session.commit()
            log.info("Registrerade databas 'pgsqlmesh warehouse'.")
        else:
            database.sqlalchemy_uri = SQLALCHEMY_URI
            db.session.commit()

        tables = {}
        for spec in DATASETS:
            table = (
                db.session.query(SqlaTable)
                .filter(
                    SqlaTable.database_id == database.id,
                    SqlaTable.schema == spec["schema"],
                    SqlaTable.table_name == spec["table_name"],
                )
                .one_or_none()
            )
            if table is None:
                table = SqlaTable(
                    table_name=spec["table_name"],
                    schema=spec["schema"],
                    database_id=database.id,
                )
                db.session.add(table)
                db.session.commit()
                table.fetch_metadata()
                log.info("Skapade dataset %s.%s.", spec["schema"], spec["table_name"])

            existing = {m.metric_name for m in table.metrics}
            for m in spec["metrics"]:
                if m["metric_name"] not in existing:
                    table.metrics.append(SqlMetric(**m))
            db.session.commit()
            tables[spec["table_name"]] = table

        _create_dashboard(db, tables)


def _create_dashboard(db, tables) -> None:
    """Skapar ett dashboard med tva charts (bast-effort)."""
    try:
        from superset.models.dashboard import Dashboard
        from superset.models.slice import Slice

        dashboard = (
            db.session.query(Dashboard)
            .filter(Dashboard.dashboard_title == "pgsqlmesh Analytics")
            .one_or_none()
        )
        if dashboard is None:
            dashboard = Dashboard(dashboard_title="pgsqlmesh Analytics", published=True)
            db.session.add(dashboard)
            db.session.commit()

        sales = tables["fct_daily_sales"]
        charts = [
            {
                "slice_name": "Intakt per dag",
                "viz_type": "echarts_timeseries_line",
                "table": sales,
                "params": {
                    "viz_type": "echarts_timeseries_line",
                    "x_axis": "order_date",
                    "time_grain_sqla": "P1D",
                    "metrics": ["revenue"],
                    "groupby": [],
                    "row_limit": 1000,
                },
            },
            {
                "slice_name": "Ordrar per land",
                "viz_type": "table",
                "table": sales,
                "params": {
                    "viz_type": "table",
                    "query_mode": "aggregate",
                    "groupby": ["country"],
                    "metrics": ["orders", "revenue"],
                    "row_limit": 50,
                },
            },
        ]

        for spec in charts:
            existing = (
                db.session.query(Slice)
                .filter(Slice.slice_name == spec["slice_name"])
                .one_or_none()
            )
            if existing is None:
                chart = Slice(
                    slice_name=spec["slice_name"],
                    viz_type=spec["viz_type"],
                    datasource_type="table",
                    datasource_id=spec["table"].id,
                    params=json.dumps(spec["params"]),
                )
                db.session.add(chart)
                db.session.commit()
                dashboard.slices.append(chart)
                log.info("Skapade chart '%s'.", spec["slice_name"])

        db.session.commit()
        log.info("Dashboard 'pgsqlmesh Analytics' klart.")
    except Exception as exc:  # noqa: BLE001 - dashboard ar best-effort
        db.session.rollback()
        log.warning("Kunde inte skapa dashboard: %s", exc)


if __name__ == "__main__":
    main()
