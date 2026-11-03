"""Assemble the narrated demo video from the recorded scenes and the cards.

Needs ffmpeg, edge-tts and Playwright (for rendering the cards). Run it where
the recordings are, never on a slow laptop: it encodes 1080p video.

    python demo/build_video.py out/ shield_demo.mp4                       # the demo
    python demo/build_video.py out/ shield_explainer.mp4 explainer.json   # the explainer
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import edge_tts
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
W, H = 1920, 1080


def run(*args: str) -> None:
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=nw=1:nk=1", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def render_cards(names: list[str], out: Path) -> None:
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": W, "height": H})
        for name in names:
            page.goto(f"file://{HERE / 'cards.html'}?card={name}")
            page.wait_for_timeout(300)
            page.screenshot(path=str(out / f"card_{name}.png"))
        b.close()


async def speak(text: str, voice: str, rate: str, path: Path) -> None:
    await edge_tts.Communicate(text, voice, rate=rate).save(str(path))


def main(rec_dir: str, output: str, script_name: str = "script.json") -> None:
    rec = Path(rec_dir)
    work = rec / "build"
    work.mkdir(parents=True, exist_ok=True)
    script = json.loads((HERE / script_name).read_text())
    segs = script["segments"]
    render_cards([s["card"] for s in segs if "card" in s], work)

    parts = []
    for i, s in enumerate(segs):
        audio = work / f"{i:02d}_{s['id']}.mp3"
        asyncio.run(speak(s["text"], script["voice"], script["rate"], audio))
        narr = duration(audio)
        clip = work / f"{i:02d}_{s['id']}.mp4"
        if "card" in s:
            total = narr + 1.0
            run("ffmpeg", "-y", "-loop", "1", "-i", str(work / f"card_{s['card']}.png"), "-i", str(audio),
                "-t", f"{total:.2f}", "-vf", f"scale={W}:{H},format=yuv420p,fade=in:0:12",
                "-af", "adelay=400|400,apad", "-r", "30", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-shortest", str(clip))
        else:
            video = rec / f"{s['scene']}.webm"
            vlen = duration(video) - 2.5  # the first seconds are the channel loading
            target = narr + 1.5
            # Speed long scenes up (typing and waiting) but never beyond 3x, so text stays readable.
            speed = min(max(vlen / target, 1.0), 3.0)
            total = max(target, vlen / speed)
            vf = (f"setpts=PTS/{speed:.3f},scale={W}:{H}:force_original_aspect_ratio=decrease,"
                  f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x0d1420,"
                  f"tpad=stop_mode=clone:stop_duration=30,format=yuv420p")
            run("ffmpeg", "-y", "-ss", "2.5", "-i", str(video), "-i", str(audio), "-t", f"{total:.2f}", "-vf", vf,
                "-af", "adelay=300|300,apad", "-r", "30", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "20", "-c:a", "aac", "-b:a", "160k", str(clip))
        parts.append(clip)
        print(f"{s['id']}: narration {narr:.1f}s")

    concat = work / "concat.txt"
    concat.write_text("".join(f"file '{p}'\n" for p in parts))
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", output)
    print(f"wrote {output} ({duration(Path(output)):.0f}s)")


if __name__ == "__main__":
    main(*sys.argv[1:4])
