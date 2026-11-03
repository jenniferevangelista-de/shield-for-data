"""Seeded incidents for the demo. Each one breaks today's data in one specific way.

All of them start from a healthy warehouse (`Warehouse.reset`) and only touch
today's business date, so you can inject, fix and re-inject them as often as
you like.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Callable

from .warehouse import Warehouse, at


def stale_business_date(wh: Warehouse) -> str:
    """The article's incident: every job ran green this morning, but it was a
    backfill for last week, so today's partition is missing."""
    today = wh.today
    backfill_day = today - timedelta(days=7)
    wh.con.execute("DELETE FROM ops.pipeline_runs WHERE business_date = ?", [today])
    wh.con.execute("DELETE FROM sales.orders WHERE business_date = ?", [today])
    # Green runs that started today, but processed last week's business date.
    wh.load_partition(backfill_day, attempt=2, started_at=at(today, 5, 30))
    return f"Jobs re-ran green at 05:30 today, but for business date {backfill_day}."


def row_count_drop(wh: Warehouse) -> str:
    """An upstream filter change: today's partition has a fraction of its usual rows."""
    today = wh.today
    wh.con.execute(
        "DELETE FROM sales.orders WHERE business_date = ? AND order_id % 10 <> 0", [today]
    )
    return "Today's orders partition lost about 90% of its rows."


def schema_drift(wh: Warehouse) -> str:
    """A producer renamed `country` to `country_code` and added `discount_cents`."""
    wh.con.execute("ALTER TABLE sales.orders RENAME COLUMN country TO country_code")
    wh.con.execute("ALTER TABLE sales.orders ADD COLUMN discount_cents BIGINT DEFAULT 0")
    return "sales.orders changed shape: country became country_code, discount_cents appeared."


def null_spike(wh: Warehouse) -> str:
    """A broken join upstream leaves customer_id empty for part of today's rows."""
    wh.con.execute(
        "UPDATE sales.orders SET customer_id = NULL "
        "WHERE business_date = ? AND order_id % 5 = 0",
        [wh.today],
    )
    return "About 20% of today's orders lost their customer_id."


def duplicate_keys(wh: Warehouse) -> str:
    """A retried load appended part of the partition twice."""
    wh.con.execute(
        "INSERT INTO sales.orders SELECT * FROM sales.orders "
        "WHERE business_date = ? AND order_id % 25 = 0",
        [wh.today],
    )
    return "A retried load appended part of today's orders a second time."


def late_upstream(wh: Warehouse) -> str:
    """The payments file that today's load depends on never arrived."""
    wh.con.execute(
        "UPDATE ops.upstream_files SET arrived_at = NULL WHERE business_date = ?", [wh.today]
    )
    return "Today's payments file was due at 05:00 UTC and has not arrived."


SCENARIOS: dict[str, Callable[[Warehouse], str]] = {
    "stale_business_date": stale_business_date,
    "row_count_drop": row_count_drop,
    "schema_drift": schema_drift,
    "null_spike": null_spike,
    "duplicate_keys": duplicate_keys,
    "late_upstream": late_upstream,
}


def inject(wh: Warehouse, name: str) -> str:
    try:
        scenario = SCENARIOS[name]
    except KeyError:
        raise ValueError(f"unknown scenario {name!r}; try one of: {', '.join(SCENARIOS)}") from None
    wh.audit(None, "shield", "scenario", f"{name}: {scenario.__doc__.split('.')[0].strip()}")
    return scenario(wh)
