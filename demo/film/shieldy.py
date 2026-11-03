"""Shieldy: a kawaii data guard who narrates the Shield film.

Round mint body with a thick outline, big glossy eyes and blush (same family as the mascots in Jennifer's other
films), a little knight helmet with a visor pushed up and a plume, a shield with a green check on one paw and a
magnifying glass on the other. The mouth follows the narration loudness (closed in the pauses); Shieldy blinks,
can raise the magnifier, cheer, or look worried.
  python demo/film/shieldy.py   -> demo/film/review/shieldy_sheet.png
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

from draw import dr

HERE = Path(__file__).resolve().parent
LINE = (36, 40, 70); BODY = (176, 232, 214); BODY_D = (138, 206, 186); BELLY = (232, 250, 242)
HELM = (196, 204, 222); HELM_D = (150, 160, 186); PLUME = (214, 52, 52)
SHIELD = (30, 52, 110); SHIELD_RIM = (255, 211, 110); CHECK = (60, 190, 120)
GLASS = (190, 232, 250); HANDLE = (176, 122, 72); BLUSH = (245, 150, 175, 150); TONGUE = (240, 120, 140)
WHITE = (255, 255, 255)


def _rot_ellipse(cx, cy, rx, ry, ang, n=36):
    c, s_ = math.cos(ang), math.sin(ang)
    return [(cx + rx * math.cos(2 * math.pi * k / n) * c - ry * math.sin(2 * math.pi * k / n) * s_,
             cy + rx * math.cos(2 * math.pi * k / n) * s_ + ry * math.sin(2 * math.pi * k / n) * c) for k in range(n)]


def shieldy(img, t, cx, by, h=420, m=0.0, mood="talk", lift=0.0, emo="happy"):
    """Draw Shieldy with the feet at (cx, by). m: mouth 0..1 (0 = closed) · mood: talk | listen | cheer
    · lift: 0..1 raises the magnifying glass · emo: happy | worried."""
    SS = 2
    k = SS * h / 420.0
    W_, H_ = int(440 * k), int(460 * k)
    lay = Image.new("RGBA", (W_, H_), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    P = lambda x, y: (x * k, y * k)
    B = lambda x0, y0, x1, y1: (x0 * k, y0 * k, x1 * k, y1 * k)
    lw = max(2, int(7 * k))
    hop = abs(math.sin(dr(t) / 12 * 5.0)) * 14 if mood == "cheer" else 0
    bob = math.sin(dr(t) / 12 * 2.6) * 3 - hop

    d.ellipse(B(120, 438, 320, 456), fill=(0, 0, 0, 40))                                          # soft shadow
    for x0 in (138, 232):                                                                         # little boots
        d.ellipse(B(x0, 410 - hop, x0 + 70, 444 - hop), fill=HELM_D, outline=LINE, width=lw)
    # right paw with the magnifying glass (raised when lift > 0)
    ang = math.radians(-20 + 120 * lift + 10 * lift * math.sin(dr(t) / 12 * 6))
    ax, ay = 352, 336 + bob - 70 * lift
    gx, gy = ax + 46 - 6 * lift, ay - 18 - 96 * lift
    d.line([P(ax, ay), P(gx - 22, gy + 22)], fill=HANDLE, width=int(14 * k))
    d.ellipse(B(gx - 44, gy - 44, gx + 44, gy + 44), fill=GLASS, outline=LINE, width=lw)
    d.ellipse(B(gx - 28, gy - 30, gx - 10, gy - 12), fill=WHITE)
    d.polygon([P(*p) for p in _rot_ellipse(ax, ay, 26, 42, -ang)], fill=BODY, outline=LINE, width=lw)
    # round body and belly
    d.ellipse(B(62, 132 + bob, 358, 428 + bob), fill=BODY, outline=LINE, width=lw)
    d.ellipse(B(132, 270 + bob, 288, 420 + bob), fill=BELLY)
    # left paw holding a shield with a green check, in front of the body
    sx0, sy0 = 34, 318 + bob
    pts = [(sx0, sy0), (sx0 + 104, sy0), (sx0 + 97, sy0 + 80), (sx0 + 52, sy0 + 122), (sx0 + 7, sy0 + 80)]
    d.polygon([P(*p) for p in pts], fill=SHIELD, outline=LINE, width=lw)
    d.line([P(*p) for p in pts + [pts[0]]], fill=SHIELD_RIM, width=max(2, int(5 * k)))
    d.line([P(sx0 + 26, sy0 + 54), P(sx0 + 47, sy0 + 77), P(sx0 + 82, sy0 + 30)], fill=CHECK, width=int(13 * k), joint="curve")
    d.ellipse(B(sx0 + 84, sy0 + 34, sx0 + 124, sy0 + 80), fill=BODY, outline=LINE, width=lw)     # thumb over the shield
    # face: glossy eyes, blush, nose, mouth
    for ex in (164, 256):
        ey = 246 + bob
        if mood != "cheer" and (t % 4.3) < 0.14:
            d.arc(B(ex - 22, ey - 8, ex + 22, ey + 18), 20, 160, fill=LINE, width=lw)
        elif mood == "cheer":
            d.arc(B(ex - 24, ey - 10, ex + 24, ey + 20), 200, 340, fill=LINE, width=lw)
        else:
            d.ellipse(B(ex - 26, ey - 28, ex + 26, ey + 28), fill=LINE)
            d.ellipse(B(ex - 16, ey - 20, ex - 1, ey - 5), fill=WHITE)
            d.ellipse(B(ex + 6, ey + 6, ex + 15, ey + 15), fill=WHITE)
    for x0 in (108, 274):
        d.ellipse(B(x0, 276 + bob, x0 + 38, 294 + bob), fill=BLUSH)
    if emo == "worried":
        for ex, sx in ((164, -1), (256, 1)):
            d.line([P(ex + sx * 26, 208 + bob), P(ex - sx * 14, 194 + bob)], fill=LINE, width=lw)
    d.ellipse(B(201, 268 + bob, 219, 280 + bob), fill=LINE)                                       # nose
    my = 288 + bob
    if m > 0.06:
        o = 0.35 + 0.65 * min(1.0, m)
        d.chord(B(182, my - 10, 238, my + 40 * o), 0, 180, fill=LINE)
        d.chord(B(194, my + 6 * o, 226, my + 36 * o), 0, 180, fill=TONGUE)
    elif emo == "worried":
        d.arc(B(194, my + 2, 226, my + 22), 200, 340, fill=LINE, width=lw)
    else:
        d.arc(B(192, my - 14, 228, my + 10), 20, 160, fill=LINE, width=lw)
    # knight helmet: dome, visor pushed up, rim, little plume
    d.chord(B(80, 58 + bob, 340, 278 + bob), 180, 360, fill=HELM, outline=LINE, width=lw)
    d.rounded_rectangle(B(72, 156 + bob, 348, 184 + bob), radius=int(12 * k), fill=HELM_D, outline=LINE, width=lw)
    d.rounded_rectangle(B(120, 108 + bob, 300, 140 + bob), radius=int(14 * k), fill=HELM_D, outline=LINE, width=lw)
    for vx in range(140, 300, 30):
        d.line([P(vx, 114 + bob), P(vx, 134 + bob)], fill=LINE, width=max(2, lw // 2))
    sway = math.sin(dr(t) / 12 * 3.0) * 6
    d.polygon([P(206, 64 + bob), P(222, 64 + bob), P(250 + sway, 10 + bob), P(226 + sway, 4 + bob), P(196 + sway, 18 + bob)],
              fill=PLUME, outline=LINE, width=max(2, lw // 2))
    w2, h2 = int(W_ / SS), int(H_ / SS)
    lay = lay.resize((w2, h2), Image.LANCZOS)
    img.paste(lay, (int(cx - w2 / 2), int(by - h2 * 446 / 460)), lay)


if __name__ == "__main__":
    from draw import INK, NAVY, paper, text
    img = paper().copy(); d = ImageDraw.Draw(img)
    poses = [("listen", 0.0, 0.0, "happy", "listening"), ("talk", 0.8, 0.0, "happy", "talking (mouth open)"),
             ("talk", 0.4, 1.0, "happy", "magnifier up"), ("listen", 0.0, 0.0, "worried", "worried"),
             ("cheer", 0.0, 1.0, "happy", "re-check passed!")]
    for i, (mood, m, lf, emo, label) in enumerate(poses):
        shieldy(img, i * 0.3 + 1, 210 + i * 375, 900, 430, m, mood, lf, emo=emo)
        text(ImageDraw.Draw(img), label, 210 + i * 375, 960, 34, INK)
    text(ImageDraw.Draw(img), "Shieldy, the data guard of Shield", 960, 110, 72, NAVY, "mm", "impact.ttf")
    out = HERE / "review"; out.mkdir(exist_ok=True)
    img.save(out / "shieldy_sheet.png"); print("ok")
