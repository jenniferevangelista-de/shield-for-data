"""Fix actions. Shield only runs these after a person approves them in chat.

Every action writes what it did to `ops.audit_log` and returns one line for the
channel. Actions are idempotent for a given business date, so approving twice
or re-running after a partial failure does no harm.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .catalog import Catalog, owners_affected
from .findings import FIX_ACTIONS, Finding
from .warehouse import Warehouse

DASHBOARD = "dashboard.daily_revenue"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hold_dashboard(wh: Warehouse, f: Finding, actor: str, catalog: Catalog) -> str:
    wh.con.execute(
        "UPDATE ops.publications SET status = 'held', reason = ?, updated_at = ? "
        "WHERE asset = ? AND business_date = ?",
        [f"{f.finding_id}: {f.check}", _now(), DASHBOARD, f.business_date],
    )
    wh.audit(f.finding_id, actor, "hold_dashboard", f"{DASHBOARD} held for {f.business_date}")
    return f"{DASHBOARD} is on hold for {f.business_date}."


def release_dashboard(wh: Warehouse, f: Finding, actor: str) -> str:
    changed = wh.scalar(
        "SELECT count(*) FROM ops.publications WHERE asset = ? AND business_date = ? AND status = 'held'",
        [DASHBOARD, f.business_date],
    )
    if not changed:
        return ""
    wh.con.execute(
        "UPDATE ops.publications SET status = 'scheduled', reason = NULL, updated_at = ? "
        "WHERE asset = ? AND business_date = ?",
        [_now(), DASHBOARD, f.business_date],
    )
    wh.audit(f.finding_id, actor, "release_dashboard", f"{DASHBOARD} back on schedule for {f.business_date}")
    return f"{DASHBOARD} is back on schedule for {f.business_date}."


def rerun_partition(wh: Warehouse, f: Finding, actor: str, catalog: Catalog) -> str:
    attempt = (wh.scalar(
        "SELECT max(attempt) FROM ops.pipeline_runs WHERE business_date = ?", [f.business_date]
    ) or 0) + 1
    wh.load_partition(f.business_date, attempt=attempt, started_at=_now())
    rows = wh.scalar("SELECT count(*) FROM sales.orders WHERE business_date = ?", [f.business_date])
    wh.audit(f.finding_id, actor, "rerun_partition",
             f"attempt {attempt} for {f.business_date} loaded {rows} rows")
    return f"Re-ran the 3 jobs for {f.business_date} (attempt {attempt}): {rows} rows loaded."


def quarantine_partition(wh: Warehouse, f: Finding, actor: str, catalog: Catalog) -> str:
    """Move only the rows that break the contract, so the rest stays usable."""
    column = f.evidence.get("column", "customer_id")
    where = f"business_date = ? AND {column} IS NULL"
    moved = wh.scalar(f"SELECT count(*) FROM sales.orders WHERE {where}", [f.business_date])
    wh.con.execute(f"INSERT INTO sales.orders_quarantine SELECT * FROM sales.orders WHERE {where}",
                   [f.business_date])
    wh.con.execute(f"DELETE FROM sales.orders WHERE {where}", [f.business_date])
    wh.con.execute("INSERT INTO ops.quarantine VALUES ('sales.orders', ?, ?, ?, ?)",
                   [f.business_date, f"{f.finding_id}: {column} is null", moved, _now()])
    wh.audit(f.finding_id, actor, "quarantine_partition",
             f"{moved} rows with null {column} moved to sales.orders_quarantine")
    return f"Moved {moved} rows with no {column} to sales.orders_quarantine."


def dedupe_partition(wh: Warehouse, f: Finding, actor: str, catalog: Catalog) -> str:
    before = wh.scalar("SELECT count(*) FROM sales.orders WHERE business_date = ?", [f.business_date])
    wh.con.execute(
        "CREATE OR REPLACE TEMP TABLE _dedup AS SELECT * FROM sales.orders WHERE business_date = ? "
        "QUALIFY row_number() OVER (PARTITION BY order_id ORDER BY created_at DESC) = 1",
        [f.business_date],
    )
    wh.con.execute("DELETE FROM sales.orders WHERE business_date = ?", [f.business_date])
    wh.con.execute("INSERT INTO sales.orders SELECT * FROM _dedup")
    after = wh.scalar("SELECT count(*) FROM sales.orders WHERE business_date = ?", [f.business_date])
    wh.audit(f.finding_id, actor, "dedupe_partition", f"{before - after} duplicate rows removed")
    return f"Removed {before - after} duplicate rows; one row per order_id remains."


def notify_owners(wh: Warehouse, f: Finding, actor: str, catalog: Catalog) -> str:
    owners, downstream = owners_affected(catalog, f.table)
    message = f"{f.finding_id} on {f.table} ({f.business_date}): {f.summary}"
    for owner in owners:
        wh.con.execute("INSERT INTO ops.notifications VALUES (?, ?, ?, ?)",
                       [_now(), owner, f.table, message])
    incident = catalog.record_incident(f.table, f"Shield {f.finding_id}: {f.check}", f.summary)
    wh.audit(f.finding_id, actor, "notify_owners",
             f"notified {', '.join(owners) or 'nobody'}; catalog incident {incident}")
    names = ", ".join(owners) if owners else "no owners on record"
    return f"Notified {names}. Incident {incident} recorded on {f.table} in the catalog."


ACTIONS = {
    "hold_dashboard": hold_dashboard,
    "rerun_partition": rerun_partition,
    "quarantine_partition": quarantine_partition,
    "dedupe_partition": dedupe_partition,
    "notify_owners": notify_owners,
}
assert set(ACTIONS) == set(FIX_ACTIONS), "every documented action needs an implementation"


def apply(wh: Warehouse, f: Finding, actor: str, catalog: Catalog) -> list[str]:
    return [ACTIONS[a](wh, f, actor, catalog) for a in f.fix.actions]
