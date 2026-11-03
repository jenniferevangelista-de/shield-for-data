"""Render the Shield film: frames piped to ffmpeg with the mix, loudness -14 LUFS, AAC 48 kHz, plus a 720p copy.
Runs in a Codespace or a CI runner, never on a laptop.  python demo/film/render.py -> demo/film/out/"""
import os
import subprocess
import time
from multiprocessing import Pool
from pathlib import Path

from film import DUR, FPS, H, W, render

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"


def job(i): return render(i / FPS).tobytes()


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True); n = int(DUR * FPS); t0 = time.time()
    final = OUT / "shield_film.mp4"
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-i", str(HERE / "mix.wav"), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                           "-pix_fmt", "yuv420p", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
                           "-shortest", str(final)], stdin=subprocess.PIPE)
    with Pool(int(os.environ.get("RENDER_PROCS", "3"))) as p:
        for b in p.imap(job, range(n), chunksize=8): ff.stdin.write(b)
    ff.stdin.close(); ff.wait()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(final), "-vf", "scale=1280:720", "-c:v", "libx264", "-crf", "22", "-pix_fmt", "yuv420p",
                    "-c:a", "copy", str(OUT / "shield_film_720.mp4")], check=True)
    print("done", round(time.time() - t0), "s")
