"""The conversation logic, independent of any chat transport.

`Desk.handle(text, sender)` takes one message addressed to Shield and returns
the replies to post. The Switch agent (`shield.agent`) feeds it messages from
the room; the tests feed it strings directly.

Nothing is changed in the warehouse without a person's approval: `scan`
records findings as `open`, and only `approve` runs fix actions.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from . import checks, fixes, scenarios
from .catalog import Catalog, owners_affected
from .findings import FIX_ACTIONS, Finding, Fix
from .narrator import interpret, why_it_matters
from .warehouse import Warehouse

ICON = {"critical": ":rotating_light:", "warning": ":warning:"}

HELP = """**Shield** watches `sales.orders` and its upstream files, and only changes data after you approve.

| Command | What it does |
|---|---|
| `@shield scan` | run every check (business-date gate, schema, row count, nulls, duplicates, upstream files) |
| `@shield approve F-1` | apply the proposed fix for F-1, re-check and post the result |
| `@shield edit F-1 hold_dashboard+notify_owners` | change the fix before approving |
| `@shield reject F-1 <reason>` | close the finding without touching data |
| `@shield status` | open findings and today's publication status |
| `@shield who sales.orders` | owners and downstream assets from the catalog |
| `@shield audit` | the audit trail |
| `@shield break <scenario>` / `@shield reset` | demo only: seed an incident or a healthy warehouse |

Fix actions: {actions}
Scenarios: {scenarios}"""


@dataclass
class Reply:
    body: str


def _clean(text: str) -> str:
    text = re.sub(r"@\S*shield\S*", " ", text, flags=re.IGNORECASE)  # the mention itself
    return re.sub(r"\s+", " ", text).strip()


class Desk:
    def __init__(self, wh: Warehouse, catalog: Catalog,
                 narrate: Callable[[Finding, list[str]], str] = why_it_matters,
                 on_audit_change: Callable[[str], None] | None = None,
                 understand: Callable[[str, list[str]], str | None] = interpret):
        self.wh = wh
        self.catalog = catalog
        self.narrate = narrate
        self.on_audit_change = on_audit_change
        self.understand = understand

    # ---- entry point ----------------------------------------------------
    def handle(self, text: str, sender: str) -> list[Reply]:
        words = _clean(text).split(" ")
        cmd, args = (words[0].lower() if words and words[0] else "help"), words[1:]
        handler = {
            "help": self.cmd_help, "scan": self.cmd_scan, "check": self.cmd_scan,
            "approve": self.cmd_approve, "reject": self.cmd_reject, "edit": self.cmd_edit,
            "status": self.cmd_status, "who": self.cmd_who, "lineage": self.cmd_who,
            "audit": self.cmd_audit, "break": self.cmd_break, "reset": self.cmd_reset,
        }.get(cmd)
        if handler is None:
            return self._free_form(_clean(text), sender)
        try:
            replies = handler(args, sender)
        except ValueError as exc:
            return [Reply(f":x: {exc}")]
        if cmd in ("approve", "reject", "edit", "scan", "break", "reset") and self.on_audit_change:
            self.on_audit_change(self.audit_markdown())
        return replies

    # Commands that change data or state only run when typed exactly.
    _CHANGES_DATA = ("approve", "reject", "edit", "break", "reset")

    def _free_form(self, text: str, sender: str) -> list[Reply]:
        open_ids = [r[0] for r in self.wh.query(
            "SELECT finding_id FROM ops.findings WHERE status = 'open' ORDER BY finding_id")]
        guess = self.understand(text, open_ids) if text else None
        if not guess:
            return [Reply("I didn't catch a request in that. Try `@shield help` for what I can do.")]
        cmd = guess.split(" ")[0].lower()
        if cmd in self._CHANGES_DATA:
            return [Reply(f"I read that as `@shield {guess}`. I only change data on an exact command, "
                          f"so reply with `@shield {guess}` if that is what you want.")]
        replies = self.handle(f"@shield {guess}", sender)
        return [Reply(f"_I read that as `@shield {guess}`._")] + replies

    # ---- commands --------------------------------------------------------
    def cmd_help(self, args, sender) -> list[Reply]:
        return [Reply(HELP.format(
            actions=", ".join(f"`{a}`" for a in FIX_ACTIONS),
            scenarios=", ".join(f"`{s}`" for s in scenarios.SCENARIOS),
        ))]

    def cmd_scan(self, args, sender) -> list[Reply]:
        found = checks.run_all(self.wh)
        self.wh.audit(None, sender, "scan", f"{len(found)} finding(s)")
        if not found:
            return [Reply(f":white_check_mark: All checks passed for `sales.orders` on {self.wh.today}. "
                          "The 08:00 report can go out.")]
        replies = [Reply(f"Scan for {self.wh.today}: **{len(found)} finding(s)**. Nothing is changed until you approve.")]
        for f in found:
            existing = self._open_for(f.check)
            if existing and existing.status == "open":
                replies.append(Reply(f"{existing.finding_id} (`{f.check}`) is still open. "
                                     f"Approve, edit or reject it: `@shield approve {existing.finding_id}`."))
                continue
            if existing:
                replies.append(Reply(f"{existing.finding_id} (`{f.check}`) is still failing but already mitigated "
                                     "(report on hold, owners notified). Waiting for the upstream fix."))
                continue
            self._save(f)
            replies.append(Reply(self.render(f)))
        return replies

    def cmd_approve(self, args, sender) -> list[Reply]:
        f = self._get(args, need_open=True)
        lines = fixes.apply(self.wh, f, sender, self.catalog)
        still = [x for x in checks.run_all(self.wh) if x.check == f.check]
        resolved = not still
        if resolved:
            released = fixes.release_dashboard(self.wh, f, "shield") if not self._other_open_critical(f) else ""
            if released:
                lines.append(released)
            verdict = ":white_check_mark: Re-check passed."
            status = "resolved"
        else:
            verdict = (":hourglass: Re-check still fails: "
                       f"{still[0].summary} The report stays on hold until this is fixed upstream.")
            status = "mitigated"
        self._decide(f, status, sender, " | ".join(lines))
        self.wh.audit(f.finding_id, "shield", "recheck", status)
        body = (f"**{f.finding_id} approved by {sender}.** Applied {f.fix.describe()}:\n"
                + "\n".join(f"- {line}" for line in lines) + f"\n\n{verdict}")
        return [Reply(body)]

    def cmd_reject(self, args, sender) -> list[Reply]:
        f = self._get(args, need_open=True)
        reason = " ".join(args[1:]) or "no reason given"
        self._decide(f, "rejected", sender, reason)
        self.wh.audit(f.finding_id, sender, "reject", reason)
        return [Reply(f"{f.finding_id} rejected by {sender}: {reason}. No data was changed.")]

    def cmd_edit(self, args, sender) -> list[Reply]:
        f = self._get(args, need_open=True)
        if len(args) < 2:
            raise ValueError("say which actions to use, e.g. `@shield edit F-1 hold_dashboard+notify_owners`")
        actions = [a for a in re.split(r"[+,]", " ".join(args[1:]).replace(" ", "+")) if a]
        unknown = [a for a in actions if a not in FIX_ACTIONS]
        if unknown:
            raise ValueError(f"unknown action {', '.join(unknown)}; use {', '.join(FIX_ACTIONS)}")
        f.fix = Fix(actions=actions, rationale=f"Edited by {sender}.")
        self.wh.con.execute("UPDATE ops.findings SET fix_json = ? WHERE finding_id = ?",
                            [f.fix.to_json(), f.finding_id])
        self.wh.audit(f.finding_id, sender, "edit", "+".join(actions))
        return [Reply(f"{f.finding_id} will now apply {f.fix.describe()}. "
                      f"Reply `@shield approve {f.finding_id}` to run it.")]

    def cmd_status(self, args, sender) -> list[Reply]:
        rows = self.wh.query(
            "SELECT finding_id, check_name, severity, status FROM ops.findings ORDER BY created_at, finding_id")
        pub = self.wh.query(
            "SELECT status, coalesce(reason, '') FROM ops.publications WHERE asset = ? AND business_date = ?",
            [fixes.DASHBOARD, self.wh.today])
        pub_line = f"`{fixes.DASHBOARD}` for {self.wh.today}: **{pub[0][0]}** {pub[0][1]}" if pub else ""
        if not rows:
            return [Reply(f"No findings recorded. {pub_line}")]
        table = "| Finding | Check | Severity | Status |\n|---|---|---|---|\n" + "\n".join(
            f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |" for r in rows)
        return [Reply(f"{table}\n\n{pub_line}")]

    def cmd_who(self, args, sender) -> list[Reply]:
        name = args[0] if args else "sales.orders"
        owners, downstream = owners_affected(self.catalog, name)
        if not owners and not downstream:
            return [Reply(f"`{name}` is not in the catalog.")]
        chain = ", ".join(f"`{a.name}` ({', '.join(a.owners) or 'no owner'})" for a in downstream) or "nothing"
        return [Reply(f"`{name}` is owned by {', '.join(owners[:1]) or 'nobody'}. Downstream: {chain}.")]

    def cmd_audit(self, args, sender) -> list[Reply]:
        return [Reply(self.audit_markdown(limit=15))]

    def cmd_break(self, args, sender) -> list[Reply]:
        if not args:
            raise ValueError(f"pick a scenario: {', '.join(scenarios.SCENARIOS)}")
        self.wh.reset()
        note = scenarios.inject(self.wh, args[0])
        self.wh.audit(None, sender, "break", args[0])
        return [Reply(f":test_tube: Demo incident seeded on a fresh warehouse: **{args[0]}**. {note} "
                      "Run `@shield scan` to see what Shield finds.")]

    def cmd_reset(self, args, sender) -> list[Reply]:
        self.wh.reset()
        self.wh.audit(None, sender, "reset", "healthy warehouse")
        return [Reply(f"Warehouse reset to a healthy state for {self.wh.today}.")]

    # ---- rendering -------------------------------------------------------
    def render(self, f: Finding) -> str:
        owners, downstream = owners_affected(self.catalog, f.table)
        names = [a.name for a in downstream]
        why = self.narrate(f, names)
        source = " · validated with Great Expectations" if "great_expectations" in f.source else ""
        return (
            f"{ICON.get(f.severity, '')} **{f.finding_id} · {f.check} · {f.severity}** on `{f.table}` "
            f"(business date {f.business_date}){source}\n"
            f"{f.summary}\n"
            f"**Why it matters:** {why}\n"
            f"**Affected:** {', '.join(f'`{n}`' for n in names) or 'no downstream assets'}"
            f"{' · owners ' + ', '.join(owners) if owners else ''}\n"
            f"**Proposed fix:** {f.fix.describe()}. {f.fix.rationale}\n"
            f"Reply `@shield approve {f.finding_id}`, `@shield edit {f.finding_id} <actions>` "
            f"or `@shield reject {f.finding_id} <reason>`."
        )

    def audit_markdown(self, limit: int = 200) -> str:
        rows = self.wh.audit_rows(limit=limit)
        lines = ["# Shield audit trail", "",
                 f"Business date {self.wh.today}. Every action below was taken in this room.", "",
                 "| When (UTC) | Finding | Who | Action | Detail |", "|---|---|---|---|---|"]
        lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |" for r in rows]
        return "\n".join(lines)

    # ---- persistence -----------------------------------------------------
    def _next_id(self) -> str:
        n = self.wh.scalar("SELECT count(*) FROM ops.findings") or 0
        return f"F-{n + 1}"

    def _save(self, f: Finding) -> None:
        f.finding_id = self._next_id()
        self.wh.con.execute(
            "INSERT INTO ops.findings VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, NULL, NULL, NULL)",
            [f.finding_id, f.check, f.table, f.business_date, f.severity, f.summary,
             f.evidence_json(), f.fix.to_json(), datetime.now(timezone.utc)],
        )
        self.wh.audit(f.finding_id, "shield", "found", f.summary)

    def _row_to_finding(self, row) -> Finding:
        fid, check, table, bdate, sev, summary, ev, fix, status = row
        return Finding(check=check, table=table, business_date=bdate, severity=sev, summary=summary,
                       evidence=json.loads(ev), fix=Fix.from_json(fix), finding_id=fid, status=status)

    _COLS = "finding_id, check_name, table_name, business_date, severity, summary, evidence_json, fix_json, status"

    def _get(self, args, need_open: bool) -> Finding:
        if not args:
            raise ValueError("which finding? e.g. `@shield approve F-1`")
        fid = args[0].upper()
        fid = fid if fid.startswith("F-") else f"F-{fid.lstrip('F')}"
        rows = self.wh.query(f"SELECT {self._COLS} FROM ops.findings WHERE finding_id = ?", [fid])
        if not rows:
            raise ValueError(f"there is no finding {fid}")
        f = self._row_to_finding(rows[0])
        if need_open and f.status != "open":
            raise ValueError(f"{fid} is already {f.status}")
        return f

    def _open_for(self, check: str) -> Finding | None:
        rows = self.wh.query(
            f"SELECT {self._COLS} FROM ops.findings WHERE check_name = ? AND status IN ('open', 'mitigated') "
            "ORDER BY created_at DESC LIMIT 1", [check])
        return self._row_to_finding(rows[0]) if rows else None

    def _other_open_critical(self, f: Finding) -> bool:
        return bool(self.wh.scalar(
            "SELECT count(*) FROM ops.findings WHERE status IN ('open', 'mitigated') "
            "AND severity = 'critical' AND finding_id <> ?", [f.finding_id]))

    def _decide(self, f: Finding, status: str, who: str, result: str) -> None:
        self.wh.con.execute(
            "UPDATE ops.findings SET status = ?, decided_by = ?, decided_at = ?, result = ? WHERE finding_id = ?",
            [status, who, datetime.now(timezone.utc), result, f.finding_id],
        )
