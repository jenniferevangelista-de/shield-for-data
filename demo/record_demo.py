"""Record the demo: a real Mattermost session with Shield, through Switch.

Each scene is typed into the data-quality channel by the demo user and
recorded by a headless Chromium (Playwright), one .webm per scene. Nothing is
mocked: the replies are Shield's, delivered by Switch.

    pip install playwright==1.47.0 && python -m playwright install chromium
    python demo/record_demo.py out/
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

URL = os.environ.get("MATTERMOST_URL", "http://localhost:18065")
CHANNEL = f"{URL}/switch/channels/{os.environ.get('SHIELD_ROOM', 'data-quality')}"
VIEW = {"width": 1280, "height": 720}  # rendered at 1.5x, so chat text is readable in 1080p
SIZE = {"width": 1920, "height": 1080}

# scene name -> list of (message, text that Shield's reply must contain)
SCENES = {
    "01_stale_scan": [
        ("@shield break stale_business_date", "Demo incident seeded"),
        ("@shield are today's numbers ok to publish?", "Proposed fix"),
    ],
    "02_stale_approve": [
        ("@shield approve F-1", "Re-check passed"),
    ],
    "03_schema_drift": [
        ("@shield break schema_drift", "Demo incident seeded"),
        ("@shield scan", "Proposed fix"),
        ("@shield which team owns the orders table?", "is owned by"),
        ("@shield approve F-1", "Re-check still fails"),
    ],
    "04_duplicates_edit_reject": [
        ("@shield break duplicate_keys", "Demo incident seeded"),
        ("@shield scan", "Proposed fix"),
        ("@shield sure, go ahead with F-1", "exact command"),
        ("@shield approve F-1", "Re-check passed"),
        ("@shield break null_spike", "Demo incident seeded"),
        ("@shield scan", "Proposed fix"),
        ("@shield reject F-1 known test load from the QA team", "rejected"),
    ],
    "05_audit": [
        ("@shield status", "Finding"),
        ("@shield audit", "Shield audit trail"),
    ],
}


def load_env(path: str = ".env") -> None:
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)


def login(page: Page) -> None:
    page.goto(f"{URL}/login")
    page.get_by_text("View in Browser").click(timeout=20_000)
    page.locator("#input_loginId").fill(os.environ.get("MATTERMOST_USER", "user"))
    page.locator("#input_password-input").fill(os.environ["MATTERMOST_USER_PASSWORD"])
    page.keyboard.press("Enter")
    page.wait_for_url("**/switch/**", timeout=30_000)


def open_channel(page: Page) -> None:
    page.goto(CHANNEL)
    page.locator("#post_textbox").wait_for(timeout=30_000)
    page.wait_for_timeout(1500)


def say(page: Page, text: str, expect: str) -> None:
    posts = page.locator("[id^='post_']").filter(has_text=expect)
    before = posts.count()
    box = page.locator("#post_textbox")
    box.click()
    box.press_sequentially(text, delay=45)
    page.wait_for_timeout(400)
    box.press("Enter")
    for _ in range(360):  # up to three minutes for Shield's reply
        if posts.count() > before:
            break
        page.wait_for_timeout(500)
    else:
        raise TimeoutError(f"no reply containing {expect!r} after {text!r}")
    page.wait_for_timeout(3500)  # time to read the reply on screen


def main(out_dir: str) -> None:
    load_env()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        state = out / "state.json"
        ctx = browser.new_context(viewport=VIEW, device_scale_factor=1.5)
        page = ctx.new_page()
        login(page)
        ctx.storage_state(path=str(state))
        ctx.close()
        for name, steps in SCENES.items():
            tmp = out / f"_{name}"
            ctx = browser.new_context(viewport=VIEW, device_scale_factor=1.5, storage_state=str(state),
                                      record_video_dir=str(tmp), record_video_size=SIZE)
            page = ctx.new_page()
            open_channel(page)
            for text, expect in steps:
                say(page, text, expect)
            page.wait_for_timeout(1500)
            page.screenshot(path=str(out / f"{name}.png"))
            video = page.video
            ctx.close()
            shutil.move(video.path(), out / f"{name}.webm")
            shutil.rmtree(tmp, ignore_errors=True)
            print(f"recorded {name}")
        browser.close()
        state.unlink(missing_ok=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out")
