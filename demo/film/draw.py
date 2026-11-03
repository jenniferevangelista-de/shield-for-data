"""Hand-drawn paper style for the kawaii film (same look as the Night Guard film): wobbly ink lines redrawn on twos,
paper texture, stick figures, cards, stamps and subtitles. Self-contained copy of the primitives Jennifer already uses."""
import math
import random
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 24
INK = (34, 30, 38); RED = (214, 52, 52); PAPER = (247, 242, 230); WHITE = (255, 255, 255)
NAVY = (30, 52, 110); BLUE = (0, 114, 178); ORANGE = (230, 159, 0); GREEN = (40, 150, 100); SOFT = (120, 112, 125)
GREY = (150, 150, 150); CREAM = (255, 251, 240)
import os
F = os.environ.get("FONT_DIR", "C:/Windows/Fonts") + "/"


@lru_cache(maxsize=32)
def font(name, size): return ImageFont.truetype(F + name, size)
def clamp(v, a=0.0, b=1.0): return max(a, min(b, v))
def seg(t, a, b): return clamp((t - a) / (b - a)) if b > a else float(t >= a)
def eout(k): k = clamp(k); return 1 - (1 - k) ** 3
def eio(k): k = clamp(k); return k * k * (3 - 2 * k)
def dr(t): return int(t * 12)  # drawing index (on twos)


def jit(p, t, seed, a=1.6):
    r = random.Random(hash((dr(t), seed, round(p[0]), round(p[1]))) & 0xFFFFFFFF)
    return (p[0] + r.uniform(-a, a), p[1] + r.uniform(-a, a))


def wline(d, pts, t, seed=0, w=7, col=INK, a=1.6):
    """Wobbly ink line through pts, re-jittered every drawing."""
    out = []
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]; n = max(2, int(math.hypot(x1 - x0, y1 - y0) / 28))
        for j in range(n):
            k = j / n; out.append(jit((x0 + (x1 - x0) * k, y0 + (y1 - y0) * k), t, seed + i * 31 + j, a))
    out.append(jit(pts[-1], t, seed + 999, a))
    d.line(out, fill=col, width=w, joint="curve")
    for p in (out[0], out[-1]): d.ellipse((p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2), fill=col)


def wrect(d, x0, y0, x1, y1, t, seed, w=6, col=INK, fill=None):
    if fill: d.rectangle((x0, y0, x1, y1), fill=fill)
    wline(d, [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], t, seed, w, col)


def wcircle(d, cx, cy, r, t, seed, w=7, col=INK, fill=None):
    pts = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 26)]
    pts = [jit(p, t, seed + i, 1.4) for i, p in enumerate(pts)]
    if fill: d.polygon(pts, fill=fill)
    d.line(pts + [pts[0]], fill=col, width=w, joint="curve")


@lru_cache(maxsize=1)
def paper():
    rng = np.random.default_rng(3)
    a = np.ones((H, W, 3), np.float32) * np.array(PAPER, np.float32)
    lo = rng.normal(0, 1, (H // 40, W // 40)).astype(np.float32)
    lo = np.array(Image.fromarray(((lo + 3) * 40).clip(0, 255).astype(np.uint8)).resize((W, H), Image.BICUBIC), np.float32) / 40 - 3
    a += (lo * 3 + rng.normal(0, 1, (H, W)) * 2.5)[..., None]
    y, x = np.ogrid[:H, :W]; v = np.sqrt(((x - W / 2) / (W / 2)) ** 2 + ((y - H / 2) / (H / 2)) ** 2)
    a *= (1 - 0.18 * np.clip(v - 0.6, 0, 1))[..., None]
    return Image.fromarray(a.clip(0, 255).astype(np.uint8))


def text(d, s, x, y, size, col=INK, anchor="mm", fn="segoeprb.ttf"):
    d.text((x, y), s, font=font(fn, size), fill=col, anchor=anchor)


def stick(d, t, hip, s=1.0, lean=0.0, armL=(200, 250), armR=(-20, 70), legL=(100, 90), legR=(80, 90),
          m=0.0, mood="normal", look=0.0, seed=1, helmet=None):
    """Stick figure. Angles in degrees (0 = right, 90 = down). arm=(upper, fore), leg=(thigh, shin).
    helmet: colour of a little football helmet on the head (None = bare head)."""
    hx, hy = hip; L = 95 * s
    def p(o, ang, ln): a = math.radians(ang); return (o[0] + ln * math.cos(a), o[1] + ln * math.sin(a))
    neck = p((hx, hy), -90 + lean, 1.25 * L)
    head = p(neck, -90 + lean, 0.55 * L); hr = 0.5 * L
    wline(d, [(hx, hy), neck], t, seed, 8)
    for i, (a1, a2) in enumerate((armL, armR)):
        e = p(neck, a1, 0.62 * L); h = p(e, a2, 0.6 * L); wline(d, [neck, e, h], t, seed + 10 + i, 8)
    for i, (a1, a2) in enumerate((legL, legR)):
        k = p((hx, hy), a1, 0.75 * L); f = p(k, a2, 0.75 * L); wline(d, [(hx, hy), k, f], t, seed + 20 + i, 8)
    wcircle(d, head[0], head[1], hr, t, seed + 30, 8, fill=PAPER)
    if helmet:
        d.chord((head[0] - hr * 1.08, head[1] - hr * 1.12, head[0] + hr * 1.08, head[1] + hr * 0.9), 180, 360, fill=helmet, outline=INK, width=6)
        d.line([(head[0] - hr * 0.1, head[1] - hr * 1.1), (head[0] - hr * 0.1, head[1] - hr * 0.1)], fill=WHITE, width=5)
        d.line([(head[0] + hr * 0.95, head[1] - hr * 0.05), (head[0] + hr * 1.25, head[1] + hr * 0.25)], fill=GREY, width=5)
    ex = head[0] + look * hr * 0.35; ey = head[1] - hr * 0.12 + (hr * 0.18 if helmet else 0)
    for sx in (-0.32, 0.32):
        cx = ex + sx * hr
        if mood == "sad": wline(d, [(cx - 10, ey - 2), (cx + 10, ey + 4)], t, seed + 40, 6)
        elif mood == "happy": d.arc((cx - 12, ey - 8, cx + 12, ey + 10), 200, 340, fill=INK, width=6)
        else: d.ellipse((cx - 7, ey - 7, cx + 7, ey + 7), fill=INK)
    my = head[1] + hr * 0.42
    if m > 0.05:
        d.ellipse((ex - 16 - 6 * m, my - 6 - 12 * m, ex + 16 + 6 * m, my + 8 + 16 * m), fill=INK)
    elif mood == "sad": d.arc((ex - 20, my, ex + 20, my + 22), 200, 340, fill=INK, width=6)
    else: d.arc((ex - 22, my - 16, ex + 22, my + 14), 20, 160, fill=INK, width=6)
    return head, hr


def stamp(img, s, cx, cy, ang, col=RED, size=80):
    f = font("impact.ttf", size); im = Image.new("RGBA", (int(len(s) * size * 0.62) + 60, size + 50), (0, 0, 0, 0))
    dd = ImageDraw.Draw(im); dd.rectangle((6, 6, im.width - 6, im.height - 6), outline=col + (255,), width=8)
    dd.text((im.width / 2, im.height / 2), s, font=f, fill=col + (255,), anchor="mm")
    im = im.rotate(ang, expand=True, resample=Image.BICUBIC); img.paste(im, (int(cx - im.width / 2), int(cy - im.height / 2)), im)


def card(d, t, cx, cy, k, title, line1, line2, col, seed, w0=620, h0=300):
    if k <= 0: return
    s = eout(k); w, h = w0 * s, h0 * s
    wrect(d, cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, t, seed, 7, fill=(255, 252, 242))
    if k > 0.7:
        d.rectangle((cx - w / 2 + 8, cy - h / 2 + 8, cx + w / 2 - 8, cy - h / 2 + 22), fill=col)
        text(d, title, cx, cy - h0 * 0.22, 70, col, "mm", "impact.ttf")
        text(d, line1, cx, cy + h0 * 0.08, 38, INK); text(d, line2, cx, cy + h0 * 0.28, 32, SOFT)


def poof(d, t, cx, cy, k):
    if k <= 0 or k >= 1: return
    for i in range(8):
        a = i * math.pi / 4; r = 40 + 120 * eout(k)
        x, y = cx + r * math.cos(a), cy + r * math.sin(a); s = 26 * (1 - k)
        d.ellipse((x - s, y - s, x + s, y + s), outline=INK, width=5)


def rms_env(path):
    import soundfile as sf
    a, sr = sf.read(str(path), dtype="float32"); a = a.mean(1) if a.ndim > 1 else a; hop = sr // 12
    r = np.array([np.sqrt(np.mean(a[j:j + hop] ** 2)) for j in range(0, len(a), hop)])
    return (r / (r.max() or 1)).tolist()
