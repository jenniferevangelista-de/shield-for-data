"""What a check produces: a finding, its evidence and the fix Shield proposes."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date

# Fix actions Shield knows how to apply. The engineer can swap the proposed
# action for any of these with `@shield edit <id> <action>`.
FIX_ACTIONS = {
    "rerun_partition": "re-run today's jobs for the required business date",
    "hold_dashboard": "hold the downstream dashboard for this business date",
    "quarantine_partition": "move today's partition to a quarantine table",
    "dedupe_partition": "remove duplicate keys from today's partition",
    "notify_owners": "notify the owners of every downstream asset",
}


@dataclass
class Fix:
    actions: list[str]
    rationale: str

    def describe(self) -> str:
        return " + ".join(f"`{a}`" for a in self.actions)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "Fix":
        return cls(**json.loads(raw))


@dataclass
class Finding:
    check: str
    table: str
    business_date: date
    severity: str  # "critical" blocks publication, "warning" does not
    summary: str
    evidence: dict
    fix: Fix
    finding_id: str = ""
    status: str = "open"
    source: str = "shield"  # "great_expectations" when a GX suite produced it
    extra: dict = field(default_factory=dict)

    def evidence_json(self) -> str:
        return json.dumps(self.evidence, default=str, sort_keys=True)
