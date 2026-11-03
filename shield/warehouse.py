"""A small, fully synthetic DuckDB warehouse for the Shield demo.

Everything here is fictional: a daily `orders` table fed by three jobs, a raw
landing table the jobs load from, and the control tables Shield reads and
writes (runs, upstream files, publications, quarantine, notifications, audit).

The demo is pinned to one business date (`DEMO_TODAY`) so every run is
reproducible, whatever day you clone the repo.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

DEMO_TODAY = date(2026, 11, 5)
REQUIRED_JOBS = ("dim_customers", "dim_products", "load_orders")
HISTORY_DAYS = 7
ROWS_PER_DAY = 1000
ORDERS_COLUMNS = (
    "order_id",
    "customer_id",
    "product_id",
    "business_date",
    "amount_cents",
    "country",
    "created_at",
)

_SCHEMA = """
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS sales;
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS raw.orders_landing (
    order_id BIGINT, customer_id BIGINT, product_id BIGINT, business_date DATE,
    amount_cents BIGINT, country VARCHAR, created_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS sales.orders (
    order_id BIGINT, customer_id BIGINT, product_id BIGINT, business_date DATE,
    amount_cents BIGINT, country VARCHAR, created_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS ops.pipeline_runs (
    job VARCHAR, business_date DATE, attempt INTEGER, run_id VARCHAR,
    state VARCHAR, started_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS ops.upstream_files (
    name VARCHAR, business_date DATE, owner VARCHAR,
    expected_by TIMESTAMPTZ, arrived_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS ops.publications (
    asset VARCHAR, business_date DATE, status VARCHAR, reason VARCHAR,
    updated_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS ops.quarantine (
    table_name VARCHAR, business_date DATE, reason VARCHAR, rows_moved BIGINT,
    quarantined_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS ops.notifications (
    sent_at TIMESTAMPTZ, owner VARCHAR, asset VARCHAR, message VARCHAR
);
CREATE TABLE IF NOT EXISTS ops.findings (
    finding_id VARCHAR PRIMARY KEY, check_name VARCHAR, table_name VARCHAR,
    business_date DATE, severity VARCHAR, summary VARCHAR, evidence_json VARCHAR,
    fix_json VARCHAR, status VARCHAR, created_at TIMESTAMPTZ, decided_by VARCHAR,
    decided_at TIMESTAMPTZ, result VARCHAR
);
CREATE TABLE IF NOT EXISTS ops.audit_log (
    logged_at TIMESTAMPTZ, finding_id VARCHAR, actor VARCHAR, action VARCHAR, detail VARCHAR
);
CREATE TABLE IF NOT EXISTS sales.orders_quarantine AS SELECT * FROM sales.orders WHERE false;
"""


def utc(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def at(day: date, hh: int, mm: int = 0) -> datetime:
    return utc(day.year, day.month, day.day, hh, mm)


@dataclass
class Warehouse:
    """Thin wrapper around a DuckDB connection with the demo schema."""

    con: duckdb.DuckDBPyConnection
    today: date = DEMO_TODAY

    @classmethod
    def open(cls, path: str | Path = ":memory:", today: date = DEMO_TODAY) -> "Warehouse":
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(path))
        con.execute("SET TimeZone = 'UTC'")
        con.execute(_SCHEMA)
        return cls(con=con, today=today)

    # ---- helpers -------------------------------------------------------
    def query(self, sql: str, params: list | tuple | None = None) -> list[tuple]:
        return self.con.execute(sql, params or []).fetchall()

    def scalar(self, sql: str, params: list | tuple | None = None):
        row = self.con.execute(sql, params or []).fetchone()
        return None if row is None else row[0]

    def df(self, sql: str, params: list | tuple | None = None):
        return self.con.execute(sql, params or []).df()

    def orders_columns(self) -> list[str]:
        rows = self.query(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'sales' AND table_name = 'orders' ORDER BY ordinal_position"
        )
        return [r[0] for r in rows]

    # ---- seeding -------------------------------------------------------
    def reset(self) -> None:
        """Drop all data and rebuild a healthy warehouse for `today`."""
        for table in (
            "raw.orders_landing",
            "ops.pipeline_runs",
            "ops.upstream_files",
            "ops.publications",
            "ops.quarantine",
            "ops.notifications",
            "ops.findings",
            "ops.audit_log",
        ):
            self.con.execute(f"DELETE FROM {table}")
        self.con.execute("DROP TABLE IF EXISTS sales.orders")
        self.con.execute("DROP TABLE IF EXISTS sales.orders_quarantine")
        self.con.execute(_SCHEMA)
        self._seed_landing()
        for offset in range(HISTORY_DAYS, -1, -1):
            day = self.today - timedelta(days=offset)
            self.load_partition(day, attempt=1, started_at=at(day, 5, 30))
            self.con.execute(
                "INSERT INTO ops.upstream_files VALUES (?, ?, ?, ?, ?)",
                [f"payments_{day.isoformat()}.csv", day, "payments-team",
                 at(day, 5, 0), at(day, 4, 40)],
            )
            # Past days are published; today's 08:00 report is still scheduled.
            status = "scheduled" if day == self.today else "published"
            self.con.execute(
                "INSERT INTO ops.publications VALUES ('dashboard.daily_revenue', ?, ?, NULL, ?)",
                [day, status, at(day, 8, 0)],
            )

    def _seed_landing(self) -> None:
        rng = random.Random(42)
        rows = []
        order_id = 100_000
        countries = ("BR", "PT", "US", "MX", "IN", "DE")
        for offset in range(HISTORY_DAYS, -1, -1):
            day = self.today - timedelta(days=offset)
            n = ROWS_PER_DAY + rng.randint(-60, 60)
            for _ in range(n):
                order_id += 1
                rows.append((
                    order_id,
                    rng.randint(1, 5000),
                    rng.randint(1, 300),
                    day,
                    rng.randint(500, 50_000),
                    rng.choice(countries),
                    at(day, rng.randint(0, 3), rng.randint(0, 59)),
                ))
        self.con.executemany(
            "INSERT INTO raw.orders_landing VALUES (?, ?, ?, ?, ?, ?, ?)", rows
        )

    def load_partition(
        self,
        business_date: date,
        attempt: int,
        started_at: datetime,
        source_date: date | None = None,
        state: str = "SUCCESS",
    ) -> None:
        """Run the three jobs for `business_date`.

        `source_date` lets a scenario reproduce the classic incident from the
        article: the job is labelled with one date but loads another one.
        """
        source_date = source_date or business_date
        for job in REQUIRED_JOBS:
            self.con.execute(
                "INSERT INTO ops.pipeline_runs VALUES (?, ?, ?, ?, ?, ?)",
                [job, business_date, attempt,
                 f"run-{job}-{business_date.isoformat()}-{attempt}", state, started_at],
            )
        if state != "SUCCESS":
            return
        self.con.execute("DELETE FROM sales.orders WHERE business_date = ?", [business_date])
        self.con.execute(
            "INSERT INTO sales.orders SELECT * FROM raw.orders_landing WHERE business_date = ?",
            [source_date],
        )

    # ---- audit ---------------------------------------------------------
    def audit(self, finding_id: str | None, actor: str, action: str, detail: str) -> None:
        self.con.execute(
            "INSERT INTO ops.audit_log VALUES (now(), ?, ?, ?, ?)",
            [finding_id, actor, action, detail],
        )

    def audit_rows(self, limit: int = 50) -> list[tuple]:
        return self.query(
            "SELECT strftime(logged_at, '%Y-%m-%d %H:%M:%S'), coalesce(finding_id, '-'), actor, action, detail "
            "FROM ops.audit_log ORDER BY logged_at, rowid LIMIT ?",
            [limit],
        )
