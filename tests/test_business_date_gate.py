from datetime import timedelta

from shield import scenarios
from shield.checks import business_date_ready, check_business_date, latest_attempts
from shield.expectations import validate_orders
from shield.warehouse import at


def test_healthy_day_is_ready(wh):
    ready, gate = business_date_ready(wh, wh.today)
    assert ready
    assert set(gate["authorizing_runs"]) == {"dim_customers", "dim_products", "load_orders"}


def test_green_backfill_today_does_not_open_the_gate(wh):
    scenarios.inject(wh, "stale_business_date")
    ready, gate = business_date_ready(wh, wh.today)
    assert not ready
    assert gate["missing_jobs"] == ["dim_customers", "dim_products", "load_orders"]
    [finding] = check_business_date(wh, validate_orders(wh, wh.today))
    assert finding.evidence["runs_green_today_for"] == [(wh.today - timedelta(days=7)).isoformat()]
    assert finding.evidence["newest_business_date_in_table"] == (wh.today - timedelta(days=1)).isoformat()
    assert finding.fix.actions == ["hold_dashboard", "rerun_partition"]


def test_greatest_attempt_wins(wh):
    # attempt 1 succeeded, but a newer attempt 2 failed: the earlier success no longer counts
    wh.load_partition(wh.today, attempt=2, started_at=at(wh.today, 6, 0), state="FAILED")
    assert latest_attempts(wh, wh.today)["load_orders"][:2] == (2, "FAILED")
    ready, gate = business_date_ready(wh, wh.today)
    assert not ready
    assert gate["not_successful"] == {j: "FAILED" for j in ("dim_customers", "dim_products", "load_orders")}


def test_a_newer_successful_attempt_reopens_the_gate(wh):
    wh.load_partition(wh.today, attempt=2, started_at=at(wh.today, 6, 0), state="FAILED")
    wh.load_partition(wh.today, attempt=3, started_at=at(wh.today, 6, 30))
    assert business_date_ready(wh, wh.today)[0]


def test_freshness_alone_fails_when_runs_look_fine(wh):
    # runs for today are green, but the table still holds yesterday's data
    wh.con.execute("DELETE FROM sales.orders WHERE business_date = ?", [wh.today])
    [finding] = check_business_date(wh, validate_orders(wh, wh.today))
    assert finding.check == "business_date_gate"
    assert "not ready" in finding.summary
