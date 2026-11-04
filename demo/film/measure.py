"""Measure the numbers the film shows, from Shield's own code. Nothing in the film is typed by hand.

For every seeded incident: what the data looked like before Shield, what Shield found, how long the scan took,
and what the data looked like after the approved fix and the re-check.

  python demo/film/measure.py   -> demo/film/measured.json
"""
import json
import os
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
os.environ["SHIELD_LLM"] = "off"

from shield import checks, scenarios  # noqa: E402
from shield.catalog import MockCatalog  # noqa: E402
from shield.desk import Desk  # noqa: E402
from shield.warehouse import Warehouse  # noqa: E402

TODAY_SQL = "SELECT count(*), coalesce(sum(amount_cents), 0) FROM sales.orders WHERE business_date = ?"


def snapshot(wh):
    rows, cents = wh.query(TODAY_SQL, [wh.today])[0]
    newest = wh.scalar("SELECT max(business_date) FROM sales.orders")
    nulls = wh.scalar("SELECT count(*) FROM sales.orders WHERE business_date = ? AND customer_id IS NULL", [wh.today]) \
        if "customer_id" in wh.orders_columns() else None
    dups = wh.scalar("SELECT count(*) - count(DISTINCT order_id) FROM sales.orders WHERE business_date = ?", [wh.today])
    pub = wh.scalar("SELECT status FROM ops.publications WHERE asset = 'dashboard.daily_revenue' AND business_date = ?", [wh.today])
    return {"rows_today": rows, "revenue_today": round(cents / 100, 2), "newest_partition": str(newest),
            "null_customer_rows": nulls, "duplicate_rows": dups, "report": pub}


def main():
    out = {"scenarios": {}}
    healthy = Warehouse.open(); healthy.reset()
    out["healthy"] = snapshot(healthy)
    out["warehouse_rows"] = healthy.scalar("SELECT count(*) FROM sales.orders")
    scan_times = []
    for name in scenarios.SCENARIOS:
        wh = Warehouse.open(); wh.reset(); scenarios.inject(wh, name)
        before = snapshot(wh)
        t0 = time.perf_counter(); found = checks.run_all(wh); scan_times.append(time.perf_counter() - t0)
        desk = Desk(wh, MockCatalog(ROOT / "catalog" / "lineage.yaml"))
        desk.handle("@shield scan", "engineer")
        t1 = time.perf_counter(); reply = desk.handle("@shield approve F-1", "engineer")[0].body; fix_s = time.perf_counter() - t1
        after = snapshot(wh)
        out["scenarios"][name] = {"finding": found[0].check, "summary": found[0].summary, "evidence": found[0].evidence,
                                  "fix": found[0].fix.actions, "before": before, "after": after,
                                  "resolved": "Re-check passed" in reply, "approve_seconds": round(fix_s, 2)}
    out["scan_seconds_median"] = round(statistics.median(scan_times), 2)
    out["caught"] = sum(1 for s in out["scenarios"].values() if s["finding"])
    out["resolved_in_place"] = sum(1 for s in out["scenarios"].values() if s["resolved"])
    (HERE / "measured.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "scenarios"}, default=str))
    for k, v in out["scenarios"].items():
        print(k, "| before", v["before"], "| after", v["after"], "| resolved", v["resolved"], v["approve_seconds"], "s")


if __name__ == "__main__":
    main()
