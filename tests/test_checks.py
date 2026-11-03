import pytest

from shield import checks, scenarios
from shield.expectations import validate_orders

EXPECTED = {
    "stale_business_date": "business_date_gate",
    "row_count_drop": "row_count",
    "schema_drift": "schema_drift",
    "null_spike": "null_rate",
    "duplicate_keys": "duplicate_keys",
    "late_upstream": "late_upstream",
}


def test_healthy_warehouse_has_no_findings(wh):
    assert checks.run_all(wh) == []


def test_every_great_expectation_passes_on_a_healthy_day(wh):
    outcomes = validate_orders(wh, wh.today)
    assert len(outcomes) == 5
    assert all(o.success for o in outcomes)


@pytest.mark.parametrize("scenario,check", EXPECTED.items())
def test_each_scenario_raises_exactly_its_finding(wh, scenario, check):
    scenarios.inject(wh, scenario)
    found = checks.run_all(wh)
    assert [f.check for f in found] == [check]
    f = found[0]
    assert f.summary and f.fix.actions and f.business_date == wh.today


def test_row_count_bounds_come_from_the_trailing_median(wh):
    scenarios.inject(wh, "row_count_drop")
    [f] = checks.run_all(wh)
    assert f.evidence["observed_rows"] < f.evidence["expected_min"] < f.evidence["expected_max"]


def test_schema_drift_names_the_columns(wh):
    scenarios.inject(wh, "schema_drift")
    [f] = checks.run_all(wh)
    assert f.evidence["unexpected"] == ["country_code", "discount_cents"]
    assert f.evidence["missing"] == ["country"]


def test_null_rate_reports_the_share(wh):
    scenarios.inject(wh, "null_spike")
    [f] = checks.run_all(wh)
    assert f.evidence["column"] == "customer_id"
    assert 15 < f.evidence["null_percent"] < 25


def test_unknown_scenario_is_rejected(wh):
    with pytest.raises(ValueError):
        scenarios.inject(wh, "meteor")
