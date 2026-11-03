"""The data contract for `sales.orders`, written as a Great Expectations suite.

Shield runs the suite against today's partition with an ephemeral GX context
(no GX Cloud, nothing written to disk) and turns every failed expectation into
a finding the team can act on in chat.
"""

from __future__ import annotations

import logging
import os
import statistics
from dataclasses import dataclass
from datetime import date

os.environ.setdefault("GX_ANALYTICS_ENABLED", "False")

import great_expectations as gx  # noqa: E402
import great_expectations.expectations as gxe  # noqa: E402

from .warehouse import ORDERS_COLUMNS, Warehouse  # noqa: E402

logging.getLogger("great_expectations").setLevel(logging.ERROR)

# Contract parameters. In a real team these come from the consumer agreement.
ROW_COUNT_TOLERANCE = 0.5  # today may be 50% below or above the trailing median
NULL_MOSTLY = 0.99  # at most 1% of customer_id may be null


@dataclass
class ExpectationOutcome:
    expectation: str
    column: str | None
    success: bool
    observed: dict
    kwargs: dict


def _context():
    ctx = gx.get_context(mode="ephemeral")
    try:  # quieter logs: no progress bars in a chat bot
        from great_expectations.data_context.types.base import ProgressBarsConfig

        ctx.variables.progress_bars = ProgressBarsConfig(globally=False)
    except Exception:  # pragma: no cover - only affects console output
        pass
    return ctx


def trailing_median_rows(wh: Warehouse, day: date) -> int:
    rows = wh.query(
        "SELECT count(*) FROM sales.orders WHERE business_date < ? "
        "AND business_date >= ? - INTERVAL 7 DAY GROUP BY business_date",
        [day, day],
    )
    counts = [r[0] for r in rows]
    return int(statistics.median(counts)) if counts else 0


def build_suite(median_rows: int, required_date: date) -> gx.ExpectationSuite:
    suite = gx.ExpectationSuite(name="sales_orders_contract")
    suite.add_expectation(
        gxe.ExpectTableColumnsToMatchSet(column_set=list(ORDERS_COLUMNS), exact_match=True)
    )
    if median_rows:
        suite.add_expectation(
            gxe.ExpectTableRowCountToBeBetween(
                min_value=int(median_rows * (1 - ROW_COUNT_TOLERANCE)),
                max_value=int(median_rows * (1 + ROW_COUNT_TOLERANCE)),
            )
        )
    suite.add_expectation(gxe.ExpectColumnValuesToNotBeNull(column="customer_id", mostly=NULL_MOSTLY))
    suite.add_expectation(gxe.ExpectColumnValuesToBeUnique(column="order_id"))
    suite.add_expectation(
        gxe.ExpectColumnMaxToBeBetween(
            column="business_date", min_value=required_date, max_value=required_date
        )
    )
    return suite


def validate_orders(wh: Warehouse, required_date: date) -> list[ExpectationOutcome]:
    """Validate the newest partition of `sales.orders` against the contract.

    The batch is the newest business date present, not `required_date`, on
    purpose: when the newest data is last week's, the freshness expectation
    is the one that has to fail.
    """
    newest = wh.scalar("SELECT max(business_date) FROM sales.orders")
    df = wh.df("SELECT * FROM sales.orders WHERE business_date = ?", [newest])
    if "business_date" in df.columns:
        df["business_date"] = df["business_date"].map(lambda v: v.date() if hasattr(v, "date") else v)
    median_rows = trailing_median_rows(wh, newest) if newest else 0

    ctx = _context()
    batch_def = (
        ctx.data_sources.add_pandas("shield_warehouse")
        .add_dataframe_asset("sales.orders")
        .add_batch_definition_whole_dataframe("newest_partition")
    )
    suite = ctx.suites.add(build_suite(median_rows, required_date))
    result = batch_def.get_batch(batch_parameters={"dataframe": df}).validate(suite)

    outcomes = []
    for r in result.results:
        cfg = r.expectation_config
        kwargs = {k: v for k, v in cfg.kwargs.items() if k not in ("batch_id",)}
        outcomes.append(
            ExpectationOutcome(
                expectation=cfg.type,
                column=kwargs.get("column"),
                success=bool(r.success),
                observed=dict(r.result or {}),
                kwargs=kwargs,
            )
        )
    return outcomes
