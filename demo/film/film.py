"""Shield film (Night Guard paper style). Jennifer opens; Shieldy, a kawaii data guard, tells the story: the green
pipeline that shipped last week's data, the Switch room, the six checks, the human approval, the audit trail and
the numbers. All data shown is the fictional demo warehouse from this repository.

  python demo/film/script.py                   -> voices + timeline.json
  python demo/film/film.py 5 20 40             -> review frames in demo/film/review/
  python demo/film/audio.py && python demo/film/render.py   -> demo/film/out/shield_film.mp4
"""
import json
import math
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from draw import (BLUE, CREAM, FPS, GREEN, GREY, H, INK, NAVY, ORANGE, RED, SOFT, W, WHITE, card, dr, eio, eout,  # noqa: E402,F401
                  font, paper, poof, rms_env, seg, stamp, stick, text, wcircle, wline, wrect)
from shieldy import shieldy  # noqa: E402

MINT = (176, 232, 214); TEAL = (30, 140, 130)
VOICE = HERE / "voice"


@lru_cache(maxsize=1)
def timeline():
    tl = json.loads((HERE / "timeline.json").read_text(encoding="utf-8"))
    return {s["id"]: s for s in tl["scenes"]}


def S(sid): return timeline()[sid]
def A(sid): return S(sid)["start"]
def V(sid): return S(sid)["voice_dur"]
def at(sid, frac): return A(sid) + V(sid) * frac


DUR = round(S("end")["end"] + 0.6, 2)
MUSIC_SWITCH = A("room")


def narr_level(t, who="shieldy"):
    """Mouth opening for Shieldy from the loudness of the narration: 0 in pauses, None when Shieldy is not speaking."""
    for s in timeline().values():
        if s["start"] <= t < s["start"] + s["voice_dur"]:
            if s["who"] != who: return None
            e = rms_env(str(VOICE / s["voice"])); k = int((t - s["start"]) * 12)
            m = e[k] if 0 <= k < len(e) else 0.0
            return 0.0 if m < 0.12 else min(1.0, m * 1.25)
    return None


@lru_cache(maxsize=1)
def subs():
    out = []
    for s in timeline().values():
        parts = [p.strip() for p in s["line"].replace(": ", ":|").replace(". ", ".|").replace("? ", "?|").replace("! ", "!|").split("|") if p.strip()]
        merged, cur = [], ""
        for p in parts:
            if cur and len(cur) + len(p) > 66: merged.append(cur); cur = p
            else: cur = (cur + " " + p).strip()
        merged.append(cur)
        final = []
        for p in merged:
            while len(p) > 70:
                i = p.rfind(", ", 0, 66); i = i + 1 if i > 20 else p.rfind(" ", 0, 64)
                final.append(p[:i].strip()); p = p[i:].strip()
            final.append(p)
        total = sum(len(p) for p in final); t = s["start"]
        for p in final:
            dd = s["voice_dur"] * len(p) / total; out.append((t, t + dd + 0.2, p)); t += dd
    return out


def subtitle(d, t):
    for a, b, s in subs():
        if a <= t < b:
            f = font("segoeprb.ttf", 40); w = d.textlength(s, font=f)
            d.rounded_rectangle((W / 2 - w / 2 - 24, 1002, W / 2 + w / 2 + 24, 1062), 18, fill=(255, 251, 240))
            text(d, s, W / 2, 1031, 40, INK); return


def dark_overlay(img, k):
    if k <= 0: return img
    return Image.blend(img, Image.new("RGB", img.size, (20, 24, 48)), 0.22 * k)


# ------------------------------------------------------------------ props
def check(d, t, x, y, k, seed, col=GREEN, s=1.0):
    if k > 0:
        wline(d, [(x - 18 * s, y), (x - 4 * s, y + 16 * s), (x - 4 * s + 34 * s * eout(k), y + 16 * s - 44 * s * eout(k))], t, seed, int(8 * s), col)


def cross(d, t, x, y, k, seed, s=1.0):
    if k > 0:
        e = eout(k) * 18 * s
        wline(d, [(x - e, y - e), (x + e, y + e)], t, seed, int(8 * s), RED); wline(d, [(x - e, y + e), (x + e, y - e)], t, seed + 1, int(8 * s), RED)


def bubble(d, t, x, y, s, seed, k=1.0, who="engineer", col=WHITE, size=40, who_col=SOFT):
    if k <= 0: return
    f = font("segoeprb.ttf", size); w = d.textlength(s, font=f) + 60; h = size + 50
    sc = eout(k); w2, h2 = w * sc, h * sc
    wrect(d, x, y, x + w2, y + h2, t, seed, 5, fill=col)
    if k >= 0.6:
        text(d, who, x + 14, y - 24, 28, who_col, "lm")
        text(d, s, x + 30, y + h / 2, size, INK, "lm")


def chat_window(d, t, x0, y0, x1, y1, seed=900, title="# data-quality"):
    wrect(d, x0, y0, x1, y1, t, seed, 8, fill=(252, 252, 255))
    d.rectangle((x0 + 6, y0 + 6, x1 - 6, y0 + 70), fill=NAVY)
    text(d, title, x0 + 30, y0 + 38, 38, WHITE, "lm", "impact.ttf")
    text(d, "through Switch", x1 - 30, y0 + 38, 30, MINT, "rm")


def clock(d, t, cx, cy, r, hh, mm, seed=300):
    wcircle(d, cx, cy, r, t, seed, 9, fill=WHITE)
    for i in range(12):
        a = math.radians(i * 30 - 90)
        wline(d, [(cx + (r - 22) * math.cos(a), cy + (r - 22) * math.sin(a)), (cx + (r - 8) * math.cos(a), cy + (r - 8) * math.sin(a))], t, seed + 10 + i, 5)
    ah = math.radians((hh % 12 + mm / 60) * 30 - 90); am = math.radians(mm * 6 - 90)
    wline(d, [(cx, cy), (cx + r * 0.5 * math.cos(ah), cy + r * 0.5 * math.sin(ah))], t, seed + 40, 9)
    wline(d, [(cx, cy), (cx + r * 0.78 * math.cos(am), cy + r * 0.78 * math.sin(am))], t, seed + 41, 6, RED)


def calendar(d, t, cx, cy, mon, day, col, seed, k=1.0):
    if k <= 0: return
    s = eout(k); w, h = 300 * s, 320 * s
    wrect(d, cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, t, seed, 8, fill=WHITE)
    if k > 0.7:
        d.rectangle((cx - w / 2 + 6, cy - h / 2 + 6, cx + w / 2 - 6, cy - h / 2 + 80), fill=col)
        text(d, mon, cx, cy - h / 2 + 44, 52, WHITE, "mm", "impact.ttf")
        text(d, day, cx, cy + 40, 150, INK, "mm", "impact.ttf")


def big_number(d, t, cx, cy, value, label, k, col, seed, size=150, fmt="{:.0f}"):
    if k <= 0: return
    v = value * eout(k)
    wrect(d, cx - 230, cy - 150, cx + 230, cy + 150, t, seed, 7, fill=(255, 252, 242))
    text(d, fmt.format(v), cx, cy - 30, size, col, "mm", "impact.ttf")
    text(d, label, cx, cy + 92, 36, INK)


# ------------------------------------------------------------------ scenes
def sc_hello(img, d, t):
    z = eout(seg(t, 0.4, 1.2))
    text(d, "SHIELD", 960, 300, int(60 + 120 * z), NAVY, "mm", "impact.ttf")
    if t > 1.0: text(d, "for data", 960, 430, 64, TEAL)
    if t > at("hello", 0.25):
        text(d, "Jennifer Evangelista", 960, 570, 60, INK)
        text(d, "data engineering · solutions architecture · Brazil", 960, 650, 40, SOFT)
    if t > at("hello", 0.55): stamp(img, "FLIP THE SWITCH", 960, 790, -4, RED, 64)
    k = seg(t, at("hello", 0.8), at("hello", 1.0))
    if k > 0: shieldy(img, t, int(1720 - 0 * k), int(1000 + 260 * (1 - eout(k))), 300, 0.0, "listen", lift=0.6 * k)
    return img


def sc_intro(img, d, t):
    a = A("intro")
    shieldy(img, t, 620, 990, 640, narr_level(t) or 0.0, "talk", lift=eio(seg(t, a, a + 0.8)) * (1 - seg(t, a + 4.0, a + 4.8)))
    d = ImageDraw.Draw(img); z = eout(seg(t, a + 0.3, a + 0.9))
    text(d, "SHIELDY", 1330, 260, int(40 + 110 * z), NAVY, "mm", "impact.ttf")
    if t > a + 1.6: text(d, "data guard", 1330, 380, 56, INK)
    if t > at("intro", 0.75): stamp(img, "ON DUTY", 1330, 560, -5, TEAL, 80)
    return img


JOBS = ["dim_customers", "dim_products", "load_orders"]


def sc_green(img, d, t):
    a = A("green")
    clock(d, t, 260, 300, 140, 7, 0)
    text(d, "07:00", 260, 500, 60, INK, "mm", "impact.ttf")
    for i, j in enumerate(JOBS):
        y = 240 + i * 190; k = seg(t, a + 1.2 + i * 0.7, a + 1.6 + i * 0.7)
        wrect(d, 560, y - 60, 1160, y + 60, t, 410 + i, 7, fill=WHITE)
        text(d, j, 600, y, 48, INK, "lm", "impact.ttf")
        check(d, t, 1100, y - 6, k, 420 + i, s=1.6)
        if k > 0: text(d, "SUCCESS", 960, y + 34, 26, GREEN, "mm")
    if t > at("green", 0.8):
        wline(d, [(1200, 430), (1360, 430)], t, 440, 8); wline(d, [(1330, 405), (1362, 430), (1330, 455)], t, 441, 8)
        card(d, t, 1580, 430, seg(t, at("green", 0.8), at("green", 1.0)), "08:00", "revenue report", "ready to ship", NAVY, 450, 400, 260)
    return img


def sc_twist(img, d, t):
    a = A("twist")
    calendar(d, t, 520, 400, "OCTOBER", "29", SOFT, 500, seg(t, a + 0.2, a + 0.8))
    calendar(d, t, 1180, 400, "NOVEMBER", "05", NAVY, 510, seg(t, at("twist", 0.2), at("twist", 0.3)))
    if t > at("twist", 0.12): text(d, "processed", 520, 610, 44, INK)
    if t > at("twist", 0.25): text(d, "needed", 1180, 610, 44, INK)
    cross(d, t, 850, 400, seg(t, at("twist", 0.3), at("twist", 0.36)), 520, s=3)
    if t > at("twist", 0.42): stamp(img, "WRONG DAY", 850, 740, -6, RED, 90)
    if t > at("twist", 0.7):
        d = ImageDraw.Draw(img); text(d, "the gate asked:  did the jobs run TODAY?", 960, 900, 46, SOFT)
    return img


def sc_cost(img, d, t):
    a = A("cost")
    wrect(d, 300, 160, 1140, 760, t, 600, 8, fill=WHITE)
    text(d, "Daily revenue · Nov 05", 720, 220, 50, NAVY, "mm", "impact.ttf")
    pts = [(360, 640), (480, 560), (600, 600), (720, 480), (840, 520), (960, 420), (1080, 450)]
    k = seg(t, a + 0.4, a + 2.0); n = max(2, int(len(pts) * k))
    wline(d, pts[:n], t, 601, 8, BLUE)
    if t > a + 2.0: text(d, "(last week's numbers)", 720, 710, 36, RED)
    stick(d, t, (1420, 820), 1.0, armR=(-40, -80), mood="happy", seed=610)
    if t > at("cost", 0.6): stamp(img, "NO ERROR", 1450, 330, 7, RED, 84)
    return img


def sc_room(img, d, t):
    a = A("room")
    chat_window(d, t, 220, 140, 1380, 900)
    k1 = seg(t, a + 0.6, a + 1.2); k2 = seg(t, at("room", 0.45), at("room", 0.6))
    bubble(d, t, 280, 300, "@shield scan", 910, k1, "engineer")
    bubble(d, t, 560, 450, "On it. Nothing changes until you approve.", 920, k2, "shield", (232, 250, 242), who_col=TEAL)
    if t > at("room", 0.6):
        text(d, "members:", 1520, 300, 40, INK); text(d, "engineer", 1520, 370, 44, NAVY); text(d, "shield", 1520, 440, 44, TEAL)
    if t > at("room", 0.8): stamp(img, "ROOM ONLY", 1600, 620, -6, NAVY, 64)
    return img


CHECKS = ["business-date gate", "schema", "row count", "nulls", "duplicates", "late files"]


def sc_six(img, d, t):
    a = A("six")
    z = eout(seg(t, a + 0.2, a + 0.8))
    text(d, "6", 330, 470, int(80 + 280 * z), TEAL, "mm", "impact.ttf")
    text(d, "checks", 330, 690, 56, INK)
    for i, c in enumerate(CHECKS):
        y = 190 + i * 110; k = seg(t, at("six", 0.12 + i * 0.07), at("six", 0.16 + i * 0.07))
        if k > 0:
            check(d, t, 760, y - 4, k, 700 + i, s=1.3); text(d, c, 820, y, 52, INK, "lm")
            if 0 < i < 5: text(d, "GX", 1320, y, 34, ORANGE, "lm", "impact.ttf")
    if t > at("six", 0.75): stamp(img, "5 × GREAT EXPECTATIONS", 1380, 870, -4, ORANGE, 54)
    return img


def sc_explain(img, d, t):
    a = A("explain")
    k = seg(t, a + 0.3, a + 1.0)
    if k > 0:
        s = eout(k)
        wrect(d, 200, 140, 200 + 1300 * s, 140 + 700 * s, t, 800, 8, fill=WHITE)
    if k >= 1:
        d.rectangle((208, 148, 1492, 168), fill=RED)
        text(d, "F-1 · business_date_gate · critical", 260, 220, 50, RED, "lm", "impact.ttf")
        rows = [("what broke", "green runs for Oct 29, not Nov 05", at("explain", 0.15)),
                ("why it matters", "written by Gemma, on this machine", at("explain", 0.62)),
                ("affected", "revenue · churn features · dashboard", at("explain", 0.3)),
                ("owners", "4 teams, from the catalog", at("explain", 0.35)),
                ("proposed fix", "hold the report + re-run the partition", at("explain", 0.45))]
        for i, (h, v, ts) in enumerate(rows):
            if t > ts:
                y = 320 + i * 105; text(d, h, 270, y, 36, SOFT, "lm"); text(d, v, 600, y, 42, INK, "lm")
    return img


STEPS = [("hold the 08:00 report", 0.5), ("re-run 3 jobs · 999 rows", 0.63), ("check again", 0.78)]


def sc_approve(img, d, t):
    a = A("approve")
    stick(d, t, (300, 820), 1.0, armR=(-30, -60), mood="normal", seed=1000)
    bubble(d, t, 420, 200, "@shield approve F-1", 1010, seg(t, at("approve", 0.28), at("approve", 0.36)), "engineer")
    for i, (s, f) in enumerate(STEPS):
        y = 450 + i * 120; k = seg(t, at("approve", f), at("approve", f + 0.05))
        if k > 0: check(d, t, 760, y - 4, k, 1020 + i, s=1.3); text(d, s, 820, y, 50, INK, "lm")
    if t > at("approve", 0.88): stamp(img, "RE-CHECK PASSED", 1330, 860, -5, GREEN, 72)
    return img


def sc_guard(img, d, t):
    a = A("guard")
    bubble(d, t, 260, 220, "@shield sure, go ahead with F-1", 1100, seg(t, a + 0.3, a + 0.9), "engineer")
    bubble(d, t, 420, 420, "I read that as approve F-1. Please type it exactly.", 1110, seg(t, at("guard", 0.45), at("guard", 0.6)),
           "shield", (232, 250, 242), who_col=TEAL, size=38)
    if t > at("guard", 0.72): stamp(img, "EXACT COMMAND ONLY", 960, 760, -4, NAVY, 74)
    return img


def sc_reject(img, d, t):
    a = A("reject")
    bubble(d, t, 260, 240, "@shield reject F-1 known test load", 1200, seg(t, at("reject", 0.3), at("reject", 0.42)), "engineer")
    bubble(d, t, 420, 440, "Rejected by engineer. No data was changed.", 1210, seg(t, at("reject", 0.65), at("reject", 0.78)),
           "shield", (232, 250, 242), who_col=TEAL)
    if t > at("reject", 0.85): stamp(img, "PEOPLE DECIDE", 960, 780, 5, GREEN, 80)
    return img


AUDIT = [("user", "break", "duplicate_keys"), ("shield", "found", "F-1 duplicate_keys"), ("user", "approve", "F-1"),
         ("shield", "dedupe", "40 rows removed"), ("shield", "re-check", "resolved")]


def sc_audit(img, d, t):
    a = A("audit")
    wrect(d, 220, 140, 1500, 820, t, 1300, 8, fill=WHITE)
    text(d, "Shield audit trail", 260, 200, 56, NAVY, "lm", "impact.ttf")
    text(d, "room document in Switch", 1460, 200, 32, TEAL, "rm")
    for c, x in (("who", 270), ("action", 560), ("detail", 860)):
        text(d, c, x, 290, 34, SOFT, "lm")
    for i, (w_, ac, de) in enumerate(AUDIT):
        if t > a + 0.6 + i * 0.6:
            y = 370 + i * 90; text(d, w_, 270, y, 42, INK, "lm"); text(d, ac, 560, y, 42, INK, "lm"); text(d, de, 860, y, 42, INK, "lm")
    return img


NUMS = [(6, "incident types", TEAL), (5, "fix actions", NAVY), (0, "without approval", RED),
        (42, "unit tests", GREEN), (1, "Switch e2e per push", BLUE), (0, "US$ to run", ORANGE)]


def sc_numbers(img, d, t):
    a = A("numbers")
    for i, (v, lab, col) in enumerate(NUMS):
        cx = 340 + (i % 3) * 620; cy = 270 + (i // 3) * 380
        k = seg(t, at("numbers", 0.02 + i * 0.13), at("numbers", 0.12 + i * 0.13))
        big_number(d, t, cx, cy, v, lab, k, col, 1400 + i)
    return img


def sc_end(img, d, t):
    a = A("end"); vend = a + V("end"); m = narr_level(t)
    shieldy(img, t, 1600, 990, 440, m or 0.0, "talk" if m is not None else "cheer", lift=1.0 if t > vend else 0.3)
    d = ImageDraw.Draw(img); z = eout(seg(t, a, a + 0.5))
    text(d, "SHIELD for data", 760, 300, int(60 + 70 * z), NAVY, "mm", "impact.ttf")
    if t > a + 1.0: text(d, "Checks by Shieldy. Decisions by people.", 760, 430, 48, INK)
    if t > a + 2.0: text(d, "github.com/jenniferevangelista-de/shield-for-data", 760, 540, 36, TEAL)
    if t > a + 2.6: text(d, "Jennifer Evangelista", 760, 640, 46, SOFT)
    text(d, 'Music: "Monkeys Spinning Monkeys" Kevin MacLeod (incompetech.com), CC BY 4.0 · opening score: original · all data fictional',
         W / 2, 1050, 22, SOFT)
    return img


ORDER = [("hello", sc_hello), ("intro", sc_intro), ("green", sc_green), ("twist", sc_twist), ("cost", sc_cost), ("room", sc_room),
         ("six", sc_six), ("explain", sc_explain), ("approve", sc_approve), ("guard", sc_guard), ("reject", sc_reject),
         ("audit", sc_audit), ("numbers", sc_numbers), ("end", sc_end)]


def render(t):
    img = paper().copy(); d = ImageDraw.Draw(img)
    fn = ORDER[0][1]
    for sid, f in ORDER:
        if t >= (A(sid) if sid != "hello" else 0): fn = f
    img = fn(img, d, t) or img
    img = dark_overlay(img, seg(t, A("green") + 2.0, A("twist")) * (1 - seg(t, MUSIC_SWITCH - 0.3, MUSIC_SWITCH + 1.0)))
    if fn not in (sc_hello, sc_intro, sc_end):
        m = narr_level(t); worried = A("twist") <= t < MUSIC_SWITCH
        cheer = (A("approve") + V("approve") * 0.85 <= t < A("guard")) or (A("numbers") <= t < A("end") and m is None)
        shieldy(img, t, 1800, 1000, 220, m or 0.0, "cheer" if cheer else ("talk" if m is not None else "listen"),
                emo="worried" if worried else "happy")
    if fn is not sc_end: subtitle(ImageDraw.Draw(img), t)
    if t < 1.0: img = Image.blend(Image.new("RGB", img.size, (0, 0, 0)), img, t)
    return img


if __name__ == "__main__":
    rv = HERE / "review"; rv.mkdir(exist_ok=True)
    pts = [float(x) for x in sys.argv[1:]] or [A(s) + V(s) * 0.85 for s, _ in ORDER]
    for x in pts:
        render(x).save(rv / f"f_{x:06.1f}.jpg", quality=82)
    print("ok", DUR, len(pts), "frames")
