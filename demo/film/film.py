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
IMG = HERE.parents[1] / "docs" / "img"
MEAS = json.loads((HERE / "measured.json").read_text(encoding="utf-8"))


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
@lru_cache(maxsize=8)
def _photo(name, w):
    im = Image.open(IMG / name).convert("RGB")
    h = int(im.height * w / im.width); im = im.resize((w, h), Image.LANCZOS)
    framed = Image.new("RGBA", (w + 24, h + 24), (255, 255, 255, 255)); framed.paste(im, (12, 12))
    return framed


def tape_photo(img, name, cx, cy, w, ang, k=1.0):
    """A real screenshot from the repository, taped onto the paper."""
    if k <= 0: return
    ph = _photo(name, w).rotate(ang, expand=True, resample=Image.BICUBIC)
    y = int(cy - ph.height / 2 + (1 - eout(k)) * 60)
    shadow = Image.new("RGBA", ph.size, (0, 0, 0, 60))
    img.paste(shadow, (int(cx - ph.width / 2) + 10, y + 12), ph); img.paste(ph, (int(cx - ph.width / 2), y), ph)
    d = ImageDraw.Draw(img, "RGBA")
    for tx in (cx - w * 0.35, cx + w * 0.35):
        d.polygon([(tx - 60, y - 14), (tx + 60, y - 4), (tx + 54, y + 30), (tx - 66, y + 20)], fill=(250, 236, 170, 200))

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
    tape_photo(img, "channel.png", 760, 470, 1180, -2, seg(t, a + 0.2, a + 0.9))
    d = ImageDraw.Draw(img)
    if t > at("room", 0.35): text(d, "the real channel", 1620, 200, 44, TEAL)
    if t > at("room", 0.5): text(d, "Mattermost + Switch", 1620, 270, 40, INK)
    if t > at("room", 0.8): stamp(img, "ROOM ONLY", 1620, 470, -6, NAVY, 64)
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
    tape_photo(img, "finding.png", 680, 480, 1220, 1.5, seg(t, a + 0.2, a + 0.9))
    d = ImageDraw.Draw(img)
    notes = [("what broke", at("explain", 0.2)), ("why it matters", at("explain", 0.3)), ("who is downstream", at("explain", 0.42)),
             ("proposed fix", at("explain", 0.55)), ("why: Gemma, local", at("explain", 0.75))]
    for i, (lab, ts) in enumerate(notes):
        if t > ts:
            y = 190 + i * 125; wline(d, [(1340, y), (1420, y)], t, 820 + i, 6, RED); text(d, lab, 1440, y, 40, RED, "lm")
    return img


STEPS = [("hold the 08:00 report", 0.5), ("re-run 3 jobs · 999 rows", 0.63), ("check again", 0.78)]


def sc_approve(img, d, t):
    a = A("approve")
    stick(d, t, (300, 820), 1.0, armR=(-30, -60), mood="normal", seed=1000)
    bubble(d, t, 420, 200, "@shield approve F-1", 1010, seg(t, at("approve", 0.28), at("approve", 0.36)), "engineer")
    for i, (s, f) in enumerate(STEPS):
        y = 450 + i * 120; k = seg(t, at("approve", f), at("approve", f + 0.05))
        if k > 0: check(d, t, 760, y - 4, k, 1020 + i, s=1.3); text(d, s, 820, y, 50, INK, "lm")
    if t > at("approve", 0.8):
        n = MEAS["scenarios"]["stale_business_date"]["after"]["rows_today"]
        big_number(d, t, 1520, 280, n, "orders for Nov 05", seg(t, at("approve", 0.8), at("approve", 0.92)), GREEN, 1030)
    if t > at("approve", 0.9): stamp(img, "RE-CHECK PASSED", 1380, 870, -5, GREEN, 72)
    return img


def sc_before_after(img, d, t):
    sc = MEAS["scenarios"]
    dup_b, dup_a = sc["duplicate_keys"]["before"], sc["duplicate_keys"]["after"]
    nb, na = sc["null_spike"]["before"], sc["null_spike"]["after"]
    sb, sa = sc["stale_business_date"]["before"], sc["stale_business_date"]["after"]
    text(d, "BEFORE", 560, 140, 90, RED, "mm", "impact.ttf"); text(d, "AFTER", 1400, 140, 90, GREEN, "mm", "impact.ttf")
    text(d, "without Shield", 560, 215, 36, SOFT); text(d, "with Shield, after approval", 1400, 215, 36, SOFT)
    wline(d, [(1020, 130), (1020, 840)], t, 1100, 6, SOFT)
    pct = nb["null_customer_rows"] * 100 // nb["rows_today"]
    rows = [("duplicates", f"{dup_b['rows_today']:,} orders · ${dup_b['revenue_today']:,.0f}",
             f"{dup_a['rows_today']:,} orders · ${dup_a['revenue_today']:,.0f}", 0.05),
            ("", f"{dup_b['duplicate_rows']} duplicated orders", f"{dup_a['duplicate_rows']} duplicates", 0.2),
            ("no customer", f"{nb['null_customer_rows']} orders ({pct}%)", f"{na['null_customer_rows']} left in the report", 0.38),
            ("wrong day", f"{sb['rows_today']} orders for Nov 05", f"{sa['rows_today']} orders for Nov 05", 0.55)]
    for i, (lab, b, af, f) in enumerate(rows):
        y = 330 + i * 125
        if t > at("before_after", f):
            if lab: text(d, lab, 560, y - 46, 28, SOFT, "mm")
            text(d, b, 560, y, 40, RED, "mm"); cross(d, t, 985, y, 1, 1110 + i)
        if t > at("before_after", f + 0.08):
            text(d, af, 1400, y, 40, GREEN, "mm"); check(d, t, 1760, y - 4, 1, 1120 + i, s=1.2)
    if t > at("before_after", 0.78):
        text(d, "schema drift · volume drop · late file: report held, owners notified", 960, 860, 38, NAVY)
    if at("before_after", 0.1) < t < at("before_after", 0.4):
        stamp(img, f"+${dup_b['revenue_today'] - dup_a['revenue_today']:,.0f} FAKE REVENUE", 560, 930, -4, RED, 46)
    return img


def sc_tech(img, d, t):
    a = A("tech")
    boxes = [(110, "Mattermost", "the team chat", SOFT), (690, "Switch", "rooms, @mentions, docs", TEAL),
             (1270, "Shield agent", "custom Python agent", NAVY)]
    for i, (x, h_, sub, col) in enumerate(boxes):
        if seg(t, a + 0.3 + i * 0.5, a + 0.8 + i * 0.5) > 0:
            wrect(d, x, 160, x + 540, 380, t, 1200 + i, 8, fill=(255, 252, 242))
            text(d, h_, x + 270, 235, 60, col, "mm", "impact.ttf"); text(d, sub, x + 270, 320, 32, INK)
    if t > at("tech", 0.25):
        wline(d, [(650, 270), (690, 270)], t, 1210, 6); wline(d, [(1230, 270), (1270, 270)], t, 1211, 6)
        text(d, "events stream down (SSE) · operations go up (HTTP) · heartbeat every 2 s", 960, 450, 40, INK)
    facts = [("149", "lines: the whole Switch client", TEAL), ("5", "Great Expectations checks", ORANGE), ("4B", "Gemma, running locally", NAVY)]
    for i, (n, lab, col) in enumerate(facts):
        if t > at("tech", 0.45 + i * 0.15):
            x = 300 + i * 560; text(d, n, x, 650, 150, col, "mm", "impact.ttf"); text(d, lab, x, 780, 36, INK)
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
    tape_photo(img, "audit.png", 740, 480, 1220, -1.5, seg(t, a + 0.2, a + 0.9))
    d = ImageDraw.Draw(img)
    if t > at("audit", 0.4): text(d, "who · what · when", 1640, 300, 44, NAVY)
    if t > at("audit", 0.7): stamp(img, "ROOM DOCUMENT", 1640, 480, 6, TEAL, 56)
    return img


def nums():
    tl = json.loads((HERE / "timeline.json").read_text(encoding="utf-8")); n = tl["numbers"]
    out = [(n["caught"], f"of {n['caught']} incidents caught", TEAL, "{:.0f}"), (n["fixed"], "fixed in place", GREEN, "{:.0f}"),
           (n["held"], "held, owners told", NAVY, "{:.0f}"), (n["scan"], "seconds per scan", ORANGE, "{:.2f}")]
    if tl.get("chat_reply_max_s") and tl["chat_reply_max_s"] < 2: out.append((2, f"s per Switch reply", BLUE, "<{:.0f}"))
    else: out.append((0, "fixes without approval", RED, "{:.0f}"))
    out.append((42, "unit tests", GREEN, "{:.0f}"))
    return out


def sc_numbers(img, d, t):
    for i, (v, lab, col, fmt) in enumerate(nums()):
        cx = 340 + (i % 3) * 620; cy = 270 + (i // 3) * 380
        k = seg(t, at("numbers", 0.02 + i * 0.12), at("numbers", 0.12 + i * 0.12))
        big_number(d, t, cx, cy, v, lab, k, col, 1400 + i, fmt=fmt)
    if t > at("numbers", 0.88): stamp(img, "US$ 0 TO RUN", 960, 930, -3, ORANGE, 50)
    return img


def sc_end(img, d, t):
    a = A("end")
    shieldy(img, t, 1600, 990, 440, 0.0, "cheer", lift=1.0)
    d = ImageDraw.Draw(img); z = eout(seg(t, a, a + 0.5))
    text(d, "SHIELD for data", 760, 300, int(60 + 70 * z), NAVY, "mm", "impact.ttf")
    if t > a + 1.0: text(d, "Checks by Shieldy. Decisions by people.", 760, 430, 48, INK)
    if t > a + 2.0: text(d, "github.com/jenniferevangelista-de/shield-for-data", 760, 540, 36, TEAL)
    if t > a + 2.6: text(d, "Jennifer Evangelista", 760, 640, 46, SOFT)
    text(d, 'Music: "Funkorama" Kevin MacLeod (incompetech.com), CC BY 4.0 · opening score: original · all data fictional',
         W / 2, 1050, 22, SOFT)
    return img


ORDER = [("hello", sc_hello), ("intro", sc_intro), ("green", sc_green), ("twist", sc_twist), ("cost", sc_cost), ("room", sc_room),
         ("six", sc_six), ("explain", sc_explain), ("approve", sc_approve), ("before_after", sc_before_after), ("guard", sc_guard),
         ("reject", sc_reject), ("audit", sc_audit), ("tech", sc_tech), ("numbers", sc_numbers), ("end", sc_end)]


def render(t):
    img = paper().copy(); d = ImageDraw.Draw(img)
    fn = ORDER[0][1]
    for sid, f in ORDER:
        if t >= (A(sid) if sid != "hello" else 0): fn = f
    img = fn(img, d, t) or img
    img = dark_overlay(img, seg(t, A("green") + 2.0, A("twist")) * (1 - seg(t, MUSIC_SWITCH - 0.3, MUSIC_SWITCH + 1.0)))
    if fn not in (sc_hello, sc_intro, sc_end):
        m = narr_level(t); worried = A("twist") <= t < MUSIC_SWITCH
        cheer = (A("approve") + V("approve") * 0.85 <= t < A("before_after")) or (A("numbers") <= t < A("end") and m is None)
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
