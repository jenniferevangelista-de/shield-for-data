"""Shield's language model: explanations and free-form messages.

Shield uses an open model served locally by Ollama (default `gemma3:4b`; `gemma3:1b` is lighter but misreads more)
through its OpenAI-compatible API, so it costs nothing and no data leaves the
machine. Any OpenAI-compatible endpoint works: set `SHIELD_LLM_URL`,
`SHIELD_LLM_MODEL` and, if needed, `SHIELD_LLM_KEY`.

The model never decides what happened or what changes. Numbers come from the
checks, and data changes only on an exact command from a person. The model is
used for two things:

* `why_it_matters`: one or two sentences on the impact of a finding.
* `interpret`: turn a free-form message ("is the revenue table ok?") into one
  of Shield's commands, which the desk then runs or asks the person to confirm.

If the model is off (`SHIELD_LLM=off`) or unreachable, Shield falls back to a
fixed sentence and to its exact command syntax.
"""

from __future__ import annotations

import os
import re

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

COMMANDS = ("help", "scan", "status", "who", "audit", "approve", "reject", "edit")


def enabled() -> bool:
    return os.environ.get("SHIELD_LLM", "on").lower() not in ("off", "0", "false", "no")


def _chat(prompt: str, max_tokens: int, timeout: float) -> str:
    import requests

    url = os.environ.get("SHIELD_LLM_URL", "http://localhost:11434/v1").rstrip("/")
    headers = {"Content-Type": "application/json"}
    if os.environ.get("SHIELD_LLM_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['SHIELD_LLM_KEY']}"
    r = requests.post(
        f"{url}/chat/completions",
        headers=headers,
        json={
            "model": os.environ.get("SHIELD_LLM_MODEL", "gemma3:4b"),
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.1,
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def why_it_matters(f: Finding, downstream: list[str], timeout: float = 45.0) -> str:
    fallback = FALLBACK.get(f.check, "This breaks the data contract for downstream consumers.")
    if not enabled():
        return fallback
    prompt = (
        "You are Shield, a data quality assistant writing in a team chat. In at most two short sentences, "
        "tell a data engineer what goes wrong for the downstream assets if nobody acts on this finding. "
        "Use only the facts below. Do not invent numbers. No greeting, no lists, no dashes.\n"
        f"Check: {f.check}\nSummary: {f.summary}\nDownstream assets: {', '.join(downstream) or 'none'}"
    )
    try:
        text = _chat(prompt, 90, timeout)
    except Exception:
        return fallback
    text = re.sub(r"\s+", " ", text.replace("—", ",").replace("*", "")).strip()
    # A small model can drift: keep its words only if they stay short and number-free.
    if not text or len(text) > 320 or re.search(r"\d", text):
        return fallback
    return text


def interpret(message: str, open_findings: list[str], timeout: float = 45.0) -> str | None:
    """Map a free-form message to `<command> [args]`, or None if it is not a request for Shield."""
    if not enabled():
        return None
    prompt = (
        "Map the user's chat message to exactly one command for a data quality bot. Commands:\n"
        "scan = run the data checks; status = list findings; audit = show the audit trail; "
        "who <table> = owners and downstream of a table; help = list commands; "
        "approve <id> = apply the fix for a finding; reject <id> <reason> = close a finding; "
        "none = anything else.\n"
        f"Open findings: {', '.join(open_findings) or 'none'}.\n"
        "Examples:\n"
        "'are today's numbers ok?' -> scan\n"
        "'who owns sales.orders?' -> who sales.orders\n"
        "'go ahead with F-2' -> approve F-2\n"
        "'ignore F-1, it is a test load' -> reject F-1 it is a test load\n"
        "'thanks!' -> none\n"
        f"Message: '{message}'\nAnswer with the command only."
    )
    try:
        text = _chat(prompt, 24, timeout)
    except Exception:
        return None
    line = text.strip().strip("`'\"").splitlines()[0].strip() if text.strip() else ""
    line = re.sub(r"^(->|command:)\s*", "", line, flags=re.IGNORECASE).strip()
    first = line.split(" ")[0].lower() if line else ""
    if first not in COMMANDS:
        return None
    return line
