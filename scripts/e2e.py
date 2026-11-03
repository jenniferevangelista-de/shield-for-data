"""End-to-end check through a real Switch server and Mattermost.

A person (the Mattermost demo user) and Shield complete every scenario in the
room: seed the incident, scan, approve the fix, and confirm the re-check.
Run it after `scripts/up.sh` with the agent running (`python -m shield.agent`).

    python scripts/e2e.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shield.mattermost import MattermostUser  # noqa: E402

ROOM = os.environ.get("SHIELD_ROOM", "data-quality")

# scenario -> text the re-check reply must contain after approval
EXPECTED = {
    "stale_business_date": "Re-check passed",
    "row_count_drop": "Re-check still fails",
    "schema_drift": "Re-check still fails",
    "null_spike": "Re-check passed",
    "duplicate_keys": "Re-check passed",
    "late_upstream": "Re-check still fails",
}


def load_env(path: str = ".env") -> None:
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)


def step(mm: MattermostUser, ch: str, text: str, expect: str, timeout: float = 120) -> str:
    since = int(time.time() * 1000) - 500
    mm.post(ch, text)
    reply = mm.wait_for(ch, since, expect, timeout=timeout)
    print(f"  {text!r} -> ok")
    return reply["message"]


def main() -> int:
    load_env()
    mm = MattermostUser()
    ch = mm.channel(ROOM)["id"]
    print(f"Channel {ROOM} found; talking to @shield as {mm.me['username']}")
    step(mm, ch, "@shield help", "Shield")
    for scenario, verdict in EXPECTED.items():
        print(f"- {scenario}")
        step(mm, ch, f"@shield break {scenario}", "Demo incident seeded")
        step(mm, ch, "@shield scan", "F-1")
        step(mm, ch, "@shield approve F-1", verdict)
    step(mm, ch, "@shield break null_spike", "Demo incident seeded")
    step(mm, ch, "@shield scan", "F-1")
    step(mm, ch, "@shield reject F-1 false alarm, known test load", "rejected")
    step(mm, ch, "@shield audit", "Shield audit trail")
    print("End-to-end: every scenario completed through Switch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
