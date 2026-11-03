"""Narration for the Shield film. Jennifer opens (Ava, first person); Shieldy narrates the rest (Ava, a little higher).
Every number matches the repository: 6 incident types, 5 Great Expectations expectations, 5 fix actions, 42 unit tests.

  python demo/film/script.py   -> demo/film/voice/*.mp3 and demo/film/timeline.json
"""
import asyncio
import json
import subprocess
from pathlib import Path

import edge_tts

HERE = Path(__file__).resolve().parent
JENNI = ("en-US-AvaMultilingualNeural", "-4%", "+0Hz")
SHIELDY = ("en-US-AvaMultilingualNeural", "+6%", "+14Hz")

# scene id, who, narration, extra seconds after the line
SCENES = [
    ("hello", "jenni", "Hi, I'm Jennifer Evangelista, a data engineering and solutions architecture specialist from Brazil. "
                       "For Flip the Switch, I built Shield, a data quality teammate for your team chat. Shieldy will show you.", 0.8),
    ("intro", "shieldy", "Hi! I'm Shieldy, a data guard. I watch your tables, so your team can trust the eight a.m. report.", 0.8),
    ("green", "shieldy", "It's seven a.m. Three jobs ran this morning. Three green checks.", 0.8),
    ("twist", "shieldy", "But they processed October twenty-ninth, not November fifth. A backfill from last week. "
                         "The gate only asked: did the jobs run today?", 1.0),
    ("cost", "shieldy", "At eight, the revenue dashboard would show last week's numbers as today's. And nobody gets an error.", 1.0),
    ("room", "shieldy", "So I live in the team's channel, through Switch. People call me with an at mention, "
                        "and only the people in the room can reach me.", 0.8),
    ("six", "shieldy", "I run six checks: the business date gate, schema, row count, nulls, duplicates and late files. "
                       "Five of them are a Great Expectations contract.", 0.8),
    ("explain", "shieldy", "When something breaks, I explain it in plain words, list everyone downstream, and propose a fix. "
                           "Gemma, a small open model, writes the why, right on the machine.", 0.8),
    ("approve", "shieldy", "Then I wait. Nothing changes until a person says approve. I hold the report, re-run the partition, "
                           "and check again. Re-check passed!", 1.0),
    ("guard", "shieldy", "If someone just says go ahead, I don't act on a guess. Data only changes on an exact command.", 0.8),
    ("reject", "shieldy", "And people stay in charge. A known test load? Reject it with a reason, and I leave the data alone.", 0.8),
    ("audit", "shieldy", "Every scan, approval and fix lands in an audit trail, shared as a document in the Switch room.", 0.8),
    ("numbers", "shieldy", "Six incident types. Five fix actions, and zero without approval. Forty-two unit tests, plus an "
                           "end-to-end test on a real Switch server, on every push. And it costs zero dollars.", 1.2),
    ("end", "shieldy", "Shield. Checks by me, decisions by people. And me? Back on guard!", 3.2),
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
    t, scenes = 0.6, []
    for i, (sid, who, line, gap) in enumerate(SCENES):
        f = out / f"n{i:02d}_{sid}.mp3"
        await speak(line, JENNI if who == "jenni" else SHIELDY, f)
        d = dur(f)
        scenes.append({"id": sid, "who": who, "line": line, "voice": f.name, "start": round(t, 3),
                       "voice_dur": round(d, 3), "end": round(t + d + gap, 3)})
        t += d + gap
    (HERE / "timeline.json").write_text(json.dumps({"scenes": scenes}, indent=1, ensure_ascii=False), encoding="utf-8")
    print("total", round(t, 1), "s")


if __name__ == "__main__":
    asyncio.run(main())
