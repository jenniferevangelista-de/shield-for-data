import pytest

from shield import scenarios


def say(desk, text, who="jen"):
    return "\n".join(r.body for r in desk.handle(text, who))


def publication(wh):
    return wh.scalar("SELECT status FROM ops.publications WHERE asset = 'dashboard.daily_revenue' "
                     "AND business_date = ?", [wh.today])


def test_scan_changes_nothing_until_approved(desk, wh):
    scenarios.inject(wh, "duplicate_keys")
    before = wh.scalar("SELECT count(*) FROM sales.orders")
    out = say(desk, "@shield scan")
    assert "F-1" in out and "duplicate_keys" in out and "approve F-1" in out
    assert wh.scalar("SELECT count(*) FROM sales.orders") == before


@pytest.mark.parametrize("scenario", ["stale_business_date", "null_spike", "duplicate_keys"])
def test_approved_fix_resolves_and_rechecks(desk, wh, scenario):
    scenarios.inject(wh, scenario)
    say(desk, "@shield scan")
    out = say(desk, "@shield approve F-1", who="Jen")
    assert "approved by Jen" in out and "Re-check passed" in out
    assert say(desk, "@shield scan").startswith(":white_check_mark:")
    assert wh.scalar("SELECT status FROM ops.findings WHERE finding_id = 'F-1'") == "resolved"
    assert publication(wh) == "scheduled"


@pytest.mark.parametrize("scenario", ["schema_drift", "row_count_drop", "late_upstream"])
def test_unfixable_here_is_held_and_escalated(desk, wh, scenario):
    scenarios.inject(wh, scenario)
    say(desk, "@shield scan")
    out = say(desk, "@shield approve F-1")
    assert "Re-check still fails" in out and "Notified" in out
    assert publication(wh) == "held"
    assert wh.scalar("SELECT count(*) FROM ops.notifications") > 0
    assert "already mitigated" in say(desk, "@shield scan")


def test_stale_date_rerun_uses_the_next_attempt(desk, wh):
    scenarios.inject(wh, "stale_business_date")
    say(desk, "@shield scan")
    say(desk, "@shield approve F-1")
    attempts = wh.query("SELECT DISTINCT attempt FROM ops.pipeline_runs WHERE business_date = ?", [wh.today])
    assert attempts == [(1,)]
    assert wh.scalar("SELECT max(business_date) FROM sales.orders") == wh.today


def test_reject_leaves_data_alone(desk, wh):
    scenarios.inject(wh, "null_spike")
    say(desk, "@shield scan")
    nulls = wh.scalar("SELECT count(*) FROM sales.orders WHERE customer_id IS NULL")
    out = say(desk, "@shield reject F-1 known test load")
    assert "rejected by jen: known test load" in out
    assert wh.scalar("SELECT count(*) FROM sales.orders WHERE customer_id IS NULL") == nulls


def test_edit_swaps_the_actions_before_approval(desk, wh):
    scenarios.inject(wh, "duplicate_keys")
    say(desk, "@shield scan")
    assert "hold_dashboard" in say(desk, "@shield edit F-1 hold_dashboard+notify_owners")
    out = say(desk, "@shield approve F-1")
    assert "hold_dashboard" in out and "Re-check still fails" in out


def test_errors_are_explained_not_raised(desk, wh):
    assert "no finding F-9" in say(desk, "@shield approve F-9")
    scenarios.inject(wh, "duplicate_keys")
    say(desk, "@shield scan")
    assert "unknown action" in say(desk, "@shield edit F-1 drop_table")
    say(desk, "@shield approve F-1")
    assert "already resolved" in say(desk, "@shield approve F-1")
    assert "didn't understand" in say(desk, "@shield dance")


def test_audit_trail_records_who_did_what(desk, wh):
    scenarios.inject(wh, "duplicate_keys")
    say(desk, "@shield scan")
    say(desk, "@shield approve F-1", who="Jen")
    audit = say(desk, "@shield audit")
    assert "| Jen | dedupe_partition |" in audit
    assert "| shield | recheck | resolved |" in audit


def test_audit_document_callback_fires_on_changes(wh, catalog):
    from shield.desk import Desk

    docs = []
    d = Desk(wh, catalog, on_audit_change=docs.append)
    d.handle("@shield break duplicate_keys", "jen")
    d.handle("@shield status", "jen")
    assert len(docs) == 1 and docs[0].startswith("# Shield audit trail")


def test_help_lists_commands(desk):
    out = say(desk, "@shield help")
    assert "approve" in out and "stale_business_date" in out


def test_who_uses_the_catalog(desk):
    out = say(desk, "@shield who sales.orders")
    assert "orders-team" in out and "dashboard.daily_revenue" in out
