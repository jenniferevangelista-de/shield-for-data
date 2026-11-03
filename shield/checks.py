"""Shield's checks. Each returns zero or more findings with a proposed fix.

The business-date gate comes first because it is the one a green pipeline
hides best: it follows the contract from "Your pipeline ran green and shipped
last week's data anyway" (the greatest recorded attempt per job and business
date wins, and a date is ready only when every required job's newest attempt
succeeded for that date).
"""

from __future__ import annotations

from datetime import date, datetime

from .expectations import ExpectationOutcome, validate_orders
from .findings import Finding, Fix
from .warehouse import ORDERS_COLUMNS, REQUIRED_JOBS, Warehouse, at

TABLE = "sales.orders"


def checkpoint(wh: Warehouse) -> datetime:
    """The moment Shield checks: 07:00 UTC, an hour before the 08:00 report."""
    return at(wh.today, 7, 0)


# ---- the business-date gate --------------------------------------------------

def latest_attempts(wh: Warehouse, business_date: date) -> dict[str, tuple[int, str, str]]:
    """job -> (attempt, state, run_id) for the greatest attempt recorded for that date."""
    rows = wh.query(
        "SELECT job, attempt, state, run_id FROM ops.pipeline_runs WHERE business_date = ? "
        "QUALIFY row_number() OVER (PARTITION BY job ORDER BY attempt DESC) = 1",
        [business_date],
    )
    return {job: (attempt, state, run_id) for job, attempt, state, run_id in rows}


def business_date_ready(wh: Warehouse, business_date: date) -> tuple[bool, dict]:
    latest = latest_attempts(wh, business_date)
    missing = [j for j in REQUIRED_JOBS if j not in latest]
    not_green = {j: latest[j][1] for j in REQUIRED_JOBS if j in latest and latest[j][1] != "SUCCESS"}
    ready = not missing and not not_green
    return ready, {
        "required_jobs": list(REQUIRED_JOBS),
        "missing_jobs": missing,
        "not_successful": not_green,
        "authorizing_runs": {j: latest[j][2] for j in latest if latest[j][1] == "SUCCESS"},
    }


def check_business_date(wh: Warehouse, gx_outcomes: list[ExpectationOutcome]) -> list[Finding]:
    required = wh.today
    ready, gate = business_date_ready(wh, required)
    green_today = wh.query(
        "SELECT DISTINCT business_date FROM ops.pipeline_runs "
        "WHERE state = 'SUCCESS' AND CAST(started_at AS DATE) = ?",
        [required],
    )
    newest = wh.scalar(f"SELECT max(business_date) FROM {TABLE}")
    freshness = next(
        (o for o in gx_outcomes if o.expectation == "expect_column_max_to_be_between"), None
    )
    fresh = freshness.success if freshness else newest == required
    if ready and fresh:
        return []
    evidence = {
        "required_business_date": required.isoformat(),
        "newest_business_date_in_table": newest.isoformat() if newest else None,
        "runs_green_today_for": sorted(d[0].isoformat() for d in green_today),
        **gate,
    }
    if green_today and not ready:
        summary = (
            f"Every job ran green this morning, but for business date "
            f"{', '.join(sorted(d[0].isoformat() for d in green_today))}, not {required}. "
            f"The newest partition in {TABLE} is {newest}."
        )
    else:
        summary = f"{TABLE} is not ready for {required}: newest partition is {newest}."
    return [Finding(
        check="business_date_gate",
        table=TABLE,
        business_date=required,
        severity="critical",
        summary=summary,
        evidence=evidence,
        fix=Fix(
            actions=["hold_dashboard", "rerun_partition"],
            rationale="Hold the 08:00 report, then re-run the jobs for today's business date and re-check.",
        ),
        source="great_expectations+gate",
    )]


# ---- Great Expectations backed checks ----------------------------------------

def _gx(outcomes: list[ExpectationOutcome], kind: str) -> ExpectationOutcome | None:
    return next((o for o in outcomes if o.expectation == kind and not o.success), None)


def check_schema(wh: Warehouse, outcomes: list[ExpectationOutcome]) -> list[Finding]:
    o = _gx(outcomes, "expect_table_columns_to_match_set")
    if not o:
        return []
    mismatch = o.observed.get("details", {}).get("mismatched", {})
    unexpected = sorted(mismatch.get("unexpected", []))
    missing = sorted(mismatch.get("missing", []))
    return [Finding(
        check="schema_drift",
        table=TABLE,
        business_date=wh.today,
        severity="critical",
        summary=(
            f"{TABLE} no longer matches its contract. New columns: {', '.join(unexpected) or 'none'}. "
            f"Missing columns: {', '.join(missing) or 'none'}."
        ),
        evidence={"expected": list(ORDERS_COLUMNS), "unexpected": unexpected, "missing": missing},
        fix=Fix(
            actions=["hold_dashboard", "notify_owners"],
            rationale="Consumers read `country`; hold the report and ask the producer to restore the contract.",
        ),
        source="great_expectations",
    )]


def check_row_count(wh: Warehouse, outcomes: list[ExpectationOutcome]) -> list[Finding]:
    o = _gx(outcomes, "expect_table_row_count_to_be_between")
    if not o:
        return []
    observed = o.observed.get("observed_value")
    lo, hi = o.kwargs.get("min_value"), o.kwargs.get("max_value")
    direction = "dropped" if observed is not None and lo is not None and observed < lo else "spiked"
    return [Finding(
        check="row_count",
        table=TABLE,
        business_date=wh.today,
        severity="critical",
        summary=f"Today's row count {direction} to {observed} (expected {lo} to {hi}, from the 7-day median).",
        evidence={"observed_rows": observed, "expected_min": lo, "expected_max": hi},
        fix=Fix(
            actions=["hold_dashboard", "notify_owners"],
            rationale="A partial load looks complete to a dashboard; hold it and tell the owners.",
        ),
        source="great_expectations",
    )]


def check_nulls(wh: Warehouse, outcomes: list[ExpectationOutcome]) -> list[Finding]:
    o = _gx(outcomes, "expect_column_values_to_not_be_null")
    if not o:
        return []
    pct = round(float(o.observed.get("unexpected_percent") or 0), 1)
    return [Finding(
        check="null_rate",
        table=TABLE,
        business_date=wh.today,
        severity="critical",
        summary=(
            f"{pct}% of today's rows have no {o.column} "
            f"({o.observed.get('unexpected_count')} rows; the contract allows {round((1 - o.kwargs.get('mostly', 1)) * 100, 1)}%)."
        ),
        evidence={"column": o.column, "null_rows": o.observed.get("unexpected_count"), "null_percent": pct},
        fix=Fix(
            actions=["quarantine_partition", "notify_owners"],
            rationale="Move the rows without a customer to quarantine so revenue by customer stays correct.",
        ),
        source="great_expectations",
    )]


def check_duplicates(wh: Warehouse, outcomes: list[ExpectationOutcome]) -> list[Finding]:
    o = _gx(outcomes, "expect_column_values_to_be_unique")
    if not o:
        return []
    dup_keys = wh.scalar(
        f"SELECT count(*) FROM (SELECT order_id FROM {TABLE} WHERE business_date = ? "
        "GROUP BY order_id HAVING count(*) > 1)",
        [wh.today],
    )
    extra_rows = wh.scalar(
        f"SELECT count(*) - count(DISTINCT order_id) FROM {TABLE} WHERE business_date = ?", [wh.today]
    )
    return [Finding(
        check="duplicate_keys",
        table=TABLE,
        business_date=wh.today,
        severity="critical",
        summary=f"{dup_keys} order_id values appear more than once today ({extra_rows} extra rows inflate revenue).",
        evidence={"duplicated_keys": dup_keys, "extra_rows": extra_rows},
        fix=Fix(
            actions=["dedupe_partition"],
            rationale="Keep one row per order_id and re-check.",
        ),
        source="great_expectations",
    )]


# ---- upstream arrival ---------------------------------------------------------

def check_upstream(wh: Warehouse) -> list[Finding]:
    now = checkpoint(wh)
    rows = wh.query(
        "SELECT name, owner, expected_by FROM ops.upstream_files "
        "WHERE business_date = ? AND arrived_at IS NULL AND expected_by < ?",
        [wh.today, now],
    )
    findings = []
    for name, owner, expected_by in rows:
        late_min = int((now - expected_by).total_seconds() // 60)
        findings.append(Finding(
            check="late_upstream",
            table=f"upstream:{name}",
            business_date=wh.today,
            severity="warning",
            summary=f"{name} (owner {owner}) was due at {expected_by:%H:%M} UTC and is {late_min} minutes late.",
            evidence={"file": name, "owner": owner, "expected_by": expected_by.isoformat(), "minutes_late": late_min},
            fix=Fix(
                actions=["hold_dashboard", "notify_owners"],
                rationale="Today's revenue needs payments; hold the report and page the upstream owner.",
            ),
        ))
    return findings


def run_all(wh: Warehouse) -> list[Finding]:
    outcomes = validate_orders(wh, wh.today)
    findings: list[Finding] = []
    findings += check_business_date(wh, outcomes)
    findings += check_schema(wh, outcomes)
    findings += check_row_count(wh, outcomes)
    findings += check_nulls(wh, outcomes)
    findings += check_duplicates(wh, outcomes)
    findings += check_upstream(wh)
    return findings
