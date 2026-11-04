"""Mix for the Shield film: an original tonal bed (A minor pads + piano, no heartbeat) under the problem, then
"Funkorama" (Kevin MacLeod, CC BY 4.0) at 30% from the Switch room on. Voices by Ava.
No noise anywhere: every effect is tonal (pop, toc, bell, sine sweep), and the music is low-passed so cymbals and
hi-hats cannot hiss.  python demo/film/audio.py -> demo/film/mix.wav
"""
import os
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt

from film import A, DUR, MUSIC_SWITCH, V, at, timeline

HERE = Path(__file__).resolve().parent
SR = 48000; N = int(SR * DUR)
MUSIC = Path(os.environ.get("SHIELD_MUSIC", "C:/Users/jenni/Downloads/codegames/pipeline/music/incompetech/Funkorama.mp3"))


def T(s): return int(s * SR)
def tt(d): return np.arange(int(d * SR)) / SR
def hz(m): return 440.0 * 2 ** ((m - 69) / 12)
def lpf(x, k):
    k = max(1, int(k)); c = np.cumsum(np.concatenate([np.zeros(k), x])); return (c[k:] - c[:-k]) / k


def load(p):
    tmp = HERE / "_tmp_mix.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-ac", "1", "-ar", str(SR), str(tmp)], check=True)
    a, _ = sf.read(tmp, dtype="float64"); tmp.unlink(); return a


def add(buf, t0, s, g=1.0):
    i = T(t0)
    if i >= len(buf) or i < 0: return
    j = min(len(buf), i + len(s)); buf[i:j] += s[: j - i] * g


def bed(dur):
    n = int(dur * SR); out = np.zeros(n)
    prog = [(57, [57, 60, 64]), (53, [53, 57, 60]), (50, [50, 53, 57]), (52, [52, 56, 59])]
    step = 4.0
    for k in range(int(dur / step) + 1):
        root, ch = prog[k % 4]; t0 = k * step; m = int(step * SR * 1.15)
        t = np.arange(m) / SR; env = np.minimum(1, t / 1.2) * np.minimum(1, (step * 1.15 - t) / 0.8).clip(0)
        pad = sum(np.sin(2 * np.pi * hz(x) * (1 + dt) * t) + 0.35 * np.sin(4 * np.pi * hz(x) * (1 + dt) * t) for x in ch for dt in (-0.003, 0.003))
        add(out, t0, pad * env * 0.05); add(out, t0, np.sin(2 * np.pi * hz(root - 24) * t) * env * 0.12)
        for b, x in enumerate([ch[0] + 12, ch[2] + 12, ch[1] + 12, ch[2] + 12]):
            pt = np.arange(int(1.6 * SR)) / SR
            add(out, t0 + b * 1.0, sum(np.sin(2 * np.pi * hz(x) * h * pt) / h ** 1.5 for h in (1, 2, 3)) * np.exp(-pt * 2.2) * 0.07)
    return out


# tonal effects only (no noise)
def pop(): t = tt(0.18); return np.sin(2 * np.pi * (700 + 900 * t) * t) * np.exp(-t * 28) * 0.5
def toc(): t = tt(0.12); return np.sin(2 * np.pi * 520 * t) * np.exp(-t * 45) * 0.6
def chime(f0=1320): t = tt(0.6); return sum(np.sin(2 * np.pi * f0 * m * t) / m for m in (1, 2, 3)) * np.exp(-t * 5) * 0.25
def tick(): t = tt(0.05); return np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 120) * 0.35
def sweep(up=True):                                    # a tonal "swoosh": a sine glide, not noise
    t = tt(0.32); f = (300 + 1100 * t / 0.32) if up else (1400 - 1100 * t / 0.32)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / 0.32) ** 2 * 0.28
def low_toc(): t = tt(0.3); return np.sin(2 * np.pi * (110 + 90 * np.exp(-t * 25)) * t) * np.exp(-t * 14) * 0.8


voice = np.zeros(N); sfx = np.zeros(N)
for s in timeline().values():
    v = load(HERE / "voice" / s["voice"]); add(voice, s["start"], v / (np.abs(v).max() + 1e-9) * 0.9)

add(sfx, 0.5, chime(880), 0.8); add(sfx, 0.65, chime(1320), 0.8); add(sfx, at("hello", 0.55), low_toc(), 0.6)
add(sfx, A("intro") + 0.3, chime(1320), 0.8); add(sfx, A("intro") + 0.45, chime(1760), 0.8); add(sfx, at("intro", 0.75), low_toc(), 0.6)
a = A("green")
for i in range(3): add(sfx, a + 1.2 + i * 0.7 + 0.3, chime(1047 + 220 * i), 0.6)
add(sfx, at("green", 0.82), sweep(), 0.8)
add(sfx, A("twist") + 0.3, pop(), 0.6); add(sfx, at("twist", 0.2), pop(), 0.6); add(sfx, at("twist", 0.33), low_toc(), 0.9)
add(sfx, at("twist", 0.42), low_toc(), 0.8)
add(sfx, at("cost", 0.6), low_toc(), 0.8)
add(sfx, A("room") + 0.3, sweep(), 0.7); add(sfx, at("room", 0.8), toc())
add(sfx, A("six") + 0.3, sweep(), 0.8)
for i in range(6): add(sfx, at("six", 0.14 + i * 0.07), tick())
add(sfx, at("six", 0.75), toc())
add(sfx, A("explain") + 0.2, sweep(), 0.6)
for f in (0.2, 0.3, 0.42, 0.55, 0.75): add(sfx, at("explain", f), pop(), 0.5)
add(sfx, at("approve", 0.3), pop())
for f, _ in ((0.5, 0), (0.63, 0), (0.78, 0)): add(sfx, at("approve", f + 0.03), chime(1320), 0.6)
add(sfx, at("approve", 0.8), sweep(), 0.6); add(sfx, at("approve", 0.9), chime(1568)); add(sfx, at("approve", 0.9) + 0.12, chime(2093))
add(sfx, A("guard") + 0.3, pop()); add(sfx, at("guard", 0.45), pop()); add(sfx, at("guard", 0.72), toc())
add(sfx, at("reject", 0.3), pop()); add(sfx, at("reject", 0.65), pop()); add(sfx, at("reject", 0.85), chime(1568), 0.8)
add(sfx, A("audit") + 0.3, sweep(), 0.7); add(sfx, at("audit", 0.7), toc())
add(sfx, A("before_after") + 0.2, sweep(), 0.8)
for f in (0.05, 0.2, 0.38, 0.55):
    add(sfx, at("before_after", f), low_toc(), 0.5); add(sfx, at("before_after", f + 0.08), chime(1568), 0.6)
for i in range(3): add(sfx, A("tech") + 0.4 + i * 0.5, pop(), 0.6)
for i in range(3): add(sfx, at("tech", 0.47 + i * 0.15), chime(1175 + 150 * i), 0.5)
for i in range(6): add(sfx, at("numbers", 0.07 + i * 0.12), chime(1047 + 110 * i), 0.5)
add(sfx, at("numbers", 0.88), toc())
add(sfx, A("end"), chime(880), 1.0); add(sfx, A("end") + 0.15, chime(1320), 1.0)

lp = butter(8, 3800, btype="low", fs=SR, output="sos")
ds = T(max(0.0, A("green") - 0.6)); dr = np.zeros(N); b = bed(MUSIC_SWITCH + 3)[: N - ds]; dr[ds:ds + len(b)] = b
dr /= (np.abs(dr).max() + 1e-9)
mk = load(MUSIC) if MUSIC.exists() else np.zeros(N)
while len(mk) < N: mk = np.concatenate([mk, mk])
mk = sosfiltfilt(lp, mk[:N]); mk /= (np.abs(mk).max() + 1e-9); dr = sosfiltfilt(lp, dr)
x = np.clip((np.arange(N) / SR - MUSIC_SWITCH) / 2.0, 0, 1)
music = dr * (1 - x) * 0.5 + mk * x * 0.30
music[ds:ds + T(1.5)] *= np.linspace(0, 1, T(1.5))
music[:ds] += mk[:ds] * 0.12                           # light tune under the hellos
duck = lpf((np.abs(voice) > 0.02).astype(float), SR // 4); duck = 1 - 0.55 * np.clip(duck * 3, 0, 1)
fade = np.ones(N); fade[T(DUR - 2.5):] = np.linspace(1, 0, N - T(DUR - 2.5))
mix = voice + sfx * 0.6 + music * duck * fade
mix = mix / np.abs(mix).max() * 0.89
sf.write(HERE / "mix.wav", np.stack([mix, mix], 1), SR); print("ok", DUR)
