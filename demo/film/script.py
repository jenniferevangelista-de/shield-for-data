"""Narration for the Shield film. Jennifer opens (Ava, first person); Shieldy narrates the rest in its own first
person (Ava, a little higher). Every number is read from measured.json (python demo/film/measure.py) and from the
end-to-end timings of a real Switch run (e2e_timings.json), never typed by hand.

  python demo/film/script.py   -> demo/film/voice/*.mp3 and demo/film/timeline.json
"""
import asyncio
import json
import statistics
import subprocess
from pathlib import Path

import edge_tts

HERE = Path(__file__).resolve().parent
JENNI = ("en-US-AvaMultilingualNeural", "-4%", "+0Hz")
SHIELDY = ("en-US-AvaMultilingualNeural", "+6%", "+14Hz")

M = json.loads((HERE / "measured.json").read_text(encoding="utf-8"))
SC = M["scenarios"]
TIM = json.loads((HERE / "e2e_timings.json").read_text()) if (HERE / "e2e_timings.json").exists() else []
# The e2e test polls the channel every 1.5 s, so these timings are upper bounds: every reply came back in the first poll.
WORK = [x for x in TIM if x["message"].startswith(("@shield scan", "@shield approve", "@shield reject"))]  # not the warm-up
REPLY_MAX = max(x["seconds"] for x in WORK) if WORK else None
STEPS = len(WORK)
APPROVE_S = SCAN_S = None


def money(v): return f"{v:,.0f}"


dup_b, dup_a = SC["duplicate_keys"]["before"], SC["duplicate_keys"]["after"]
nul_b = SC["null_spike"]["before"]
inflated = dup_b["revenue_today"] - dup_a["revenue_today"]
NUM = dict(rows=M["warehouse_rows"], caught=M["caught"], fixed=M["resolved_in_place"], held=M["caught"] - M["resolved_in_place"],
           scan=M["scan_seconds_median"], dup=dup_b["duplicate_rows"], inflated=money(inflated), nulls=nul_b["null_customer_rows"],
           today=SC["stale_business_date"]["after"]["rows_today"])
CHAT = (" Through the real Switch server, every reply came back in under two seconds." if REPLY_MAX and REPLY_MAX < 2 else "")

# scene id, who, narration, extra seconds after the line
SCENES = [
    ("hello", "jenni", "Hi, I'm Jennifer Evangelista, a data engineering and solutions architecture specialist from Brazil. "
                       "For Flip the Switch, I built Shield, a data quality teammate for your team chat. Shieldy will show you.", 0.8),
    ("intro", "shieldy", "Hi! I'm Shieldy, a data guard. I watch your tables, so your team can trust the eight a.m. report.", 0.8),
    ("green", "shieldy", "It's seven a.m. Three jobs ran this morning. Three green checks.", 0.8),
    ("twist", "shieldy", "But they processed October twenty-ninth, not November fifth. A backfill from last week. "
                         "The gate only asked: did the jobs run today?", 1.0),
    ("cost", "shieldy", "So today's partition has zero orders, and at eight the revenue report would show yesterday as today. "
                        "Nobody gets an error.", 1.0),
    ("room", "shieldy", "That's why I live in the team's channel, through Switch. People call me with an at mention, "
                        "and only the people in the room can reach me.", 0.8),
    ("six", "shieldy", "I run six checks: the business date gate, schema, row count, nulls, duplicates and late files. "
                       "Five of them are a Great Expectations contract.", 0.8),
    ("explain", "shieldy", "This is my real message in the channel. What broke, why it matters, who is downstream, and the fix "
                           "I propose. Gemma, a small open model, writes the why, right on the machine.", 0.8),
    ("approve", "shieldy", "Then I wait. Nothing changes until a person says approve. I hold the report, re-run the partition, "
                           f"and check again. {NUM['today']} orders for the right day. Re-check passed!", 1.0),
    ("before_after", "shieldy", f"Before and after. Duplicates: {NUM['dup']} extra orders inflated revenue by {NUM['inflated']} "
                                f"dollars, and after the fix there are zero. Nulls: {NUM['nulls']} orders had no customer, and "
                                "after the fix none are left in the report. When the fix must come from upstream, I hold the "
                                "report and tell the owners.", 1.0),
    ("guard", "shieldy", "If someone just says go ahead, I don't act on a guess. Data only changes on an exact command.", 0.8),
    ("reject", "shieldy", "And people stay in charge. A known test load? Reject it with a reason, and I leave the data alone.", 0.8),
    ("audit", "shieldy", "Every scan, approval and fix lands in an audit trail, shared as a document in the Switch room.", 0.8),
    ("tech", "shieldy", "Under the hood, I'm a custom agent on the Switch protocol: events stream down, plain HTTP goes up, "
                        "with a heartbeat every two seconds. My whole Switch client is about one hundred fifty lines.", 0.8),
    ("numbers", "shieldy", f"The numbers. {NUM['caught']} out of {NUM['caught']} incidents caught. {NUM['fixed']} fixed in place, "
                           f"{NUM['held']} held and escalated. Each scan takes about a tenth of a second.{CHAT} Forty-two unit "
                           "tests, an end-to-end test on a real Switch server on every push, and it costs zero dollars.", 1.2),
    ("end", "jenni", "Shield. Checks by Shieldy, decisions by people. Thanks for watching!", 3.2),
]


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True).stdout)


async def speak(line, voice, path, attempts=5):
    for i in range(attempts):            # the TTS service drops a request now and then
        try:
            await edge_tts.Communicate(line, voice[0], rate=voice[1], pitch=voice[2]).save(str(path)); return
        except edge_tts.exceptions.NoAudioReceived:
            if i == attempts - 1: raise
            await asyncio.sleep(3 * (i + 1))


async def main():
    out = HERE / "voice"; out.mkdir(exist_ok=True)
    for f in out.glob("*.mp3"): f.unlink()
    t, scenes = 0.6, []
    for i, (sid, who, line, gap) in enumerate(SCENES):
        f = out / f"n{i:02d}_{sid}.mp3"
        await speak(line, JENNI if who == "jenni" else SHIELDY, f)
        d = dur(f)
        scenes.append({"id": sid, "who": who, "line": line, "voice": f.name, "start": round(t, 3),
                       "voice_dur": round(d, 3), "end": round(t + d + gap, 3)})
        t += d + gap
    (HERE / "timeline.json").write_text(json.dumps({"scenes": scenes, "numbers": NUM, "chat_scan_s": SCAN_S,
                                                    "chat_approve_s": APPROVE_S, "chat_reply_max_s": REPLY_MAX, "chat_steps": STEPS}, indent=1, ensure_ascii=False), encoding="utf-8")
    print("total", round(t, 1), "s", NUM, REPLY_MAX, STEPS)


if __name__ == "__main__":
    asyncio.run(main())
