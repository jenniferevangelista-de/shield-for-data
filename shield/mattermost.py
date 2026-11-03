"""The person's side of the demo: post and read in the Mattermost channel.

Used by the end-to-end test (`scripts/e2e.py`) and handy for scripting a
replay. In the real workflow people just type in Mattermost, Slack, Teams,
Discord or Telegram, and Switch carries the message to Shield.
"""

from __future__ import annotations

import os
import time

import requests


class MattermostUser:
    def __init__(self, url: str | None = None, user: str | None = None, password: str | None = None,
                 team: str | None = None):
        self.url = (url or os.environ.get("MATTERMOST_URL", "http://localhost:18065")).rstrip("/")
        self.team_name = team or os.environ.get("MATTERMOST_TEAM", "switch")
        self.http = requests.Session()
        r = self.http.post(f"{self.url}/api/v4/users/login", json={
            "login_id": user or os.environ.get("MATTERMOST_USER", "user"),
            "password": password or os.environ["MATTERMOST_USER_PASSWORD"],
        }, timeout=20)
        r.raise_for_status()
        self.http.headers["Authorization"] = f"Bearer {r.headers['Token']}"
        self.me = r.json()
        self.team = self.http.get(f"{self.url}/api/v4/teams/name/{self.team_name}", timeout=20).json()

    def channel(self, display_name: str) -> dict:
        """Find the channel Switch created for a room (matched on display name or name)."""
        channels = self.http.get(
            f"{self.url}/api/v4/users/me/teams/{self.team['id']}/channels", timeout=20).json()
        wanted = display_name.lower().replace(" ", "-")
        for ch in channels:
            if ch.get("display_name", "").lower() == display_name.lower() or ch.get("name", "") == wanted:
                return ch
        names = ", ".join(c.get("display_name", "") for c in channels)
        raise LookupError(f"no channel named {display_name!r}; I can see: {names}")

    def post(self, channel_id: str, message: str) -> dict:
        r = self.http.post(f"{self.url}/api/v4/posts", json={"channel_id": channel_id, "message": message},
                           timeout=20)
        r.raise_for_status()
        return r.json()

    def posts_since(self, channel_id: str, since_ms: int) -> list[dict]:
        r = self.http.get(f"{self.url}/api/v4/channels/{channel_id}/posts", params={"since": since_ms},
                          timeout=20)
        r.raise_for_status()
        data = r.json()
        posts = [data["posts"][pid] for pid in data.get("order", [])]
        return sorted(posts, key=lambda p: p["create_at"])

    def wait_for(self, channel_id: str, since_ms: int, contains: str, timeout: float = 90) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            for p in self.posts_since(channel_id, since_ms):
                if p["user_id"] != self.me["id"] and contains in p.get("message", ""):
                    return p
            time.sleep(1.5)
        raise TimeoutError(f"no reply containing {contains!r} within {timeout}s")
