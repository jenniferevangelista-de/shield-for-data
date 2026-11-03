"""Plain-language "why it matters" lines for a finding.

Shield's numbers always come from the checks. The model is only asked to
explain the impact in one or two sentences, using the evidence it is given,
and Shield falls back to a fixed sentence per check when no model is
configured or the call fails. That keeps the bot useful offline and in tests.

The default model is served by GitHub Models, which is free with a GitHub
token (`SHIELD_LLM_TOKEN`, or `GITHUB_TOKEN`).
"""

from __future__ import annotations

import os

from .findings import Finding

FALLBACK = {
    "business_date_gate": (
        "The scheduler says success, but the 08:00 report would show last week's numbers as today's. "
        "Green runs are not the same as the right business date."
    ),
    "row_count": "A partial load looks complete to every dashboard, so revenue would be understated without any error.",
    "schema_drift": "Every query that selects the old column will fail or return nulls once consumers read today's data.",
    "null_rate": "Orders without a customer drop out of customer-level revenue and churn features.",
    "duplicate_keys": "Duplicated orders inflate today's revenue and counts in every downstream table.",
    "late_upstream": "Without the payments file, today's revenue would be published without settled payments.",
}

ENDPOINT = "https://models.github.ai/inference/chat/completions"


def _token() -> str | None:
    return os.environ.get("SHIELD_LLM_TOKEN") or os.environ.get("GITHUB_TOKEN")


def why_it_matters(f: Finding, downstream: list[str], timeout: float = 20.0) -> str:
    fallback = FALLBACK.get(f.check, "This breaks the data contract for downstream consumers.")
    token = _token()
    if not token or os.environ.get("SHIELD_LLM", "on") == "off":
        return fallback
    try:
        import requests

        prompt = (
            "You are Shield, a data quality teammate posting in a team chat. In at most two short "
            "sentences, explain to a data engineer why this finding matters for the downstream assets. "
            "Use only the facts given, do not invent numbers, no greetings, no em dashes.\n"
            f"Check: {f.check}\nTable: {f.table}\nSummary: {f.summary}\nEvidence: {f.evidence_json()}\n"
            f"Downstream assets: {', '.join(downstream) or 'none'}"
        )
        r = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "model": os.environ.get("SHIELD_LLM_MODEL", "openai/gpt-4.1-mini"),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 120,
                "temperature": 0.2,
            },
            timeout=timeout,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip().replace("—", ",")
        return text or fallback
    except Exception:
        return fallback
