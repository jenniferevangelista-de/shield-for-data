"""A small client for the Switch agent protocol (protocol 9, Switch 0.31).

Down: one server-sent event stream. Up: plain HTTP. See
https://docs.switchagents.ai/flintai/switch/internals/agent-protocol

Only what Shield needs is here: register, open the stream, beat, call
operations and post messages.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterator

import requests

CLIENT_NAME = "shield"
CLIENT_VERSION = "0.1.0"


@dataclass
class SseEvent:
    event: str
    data: dict
    id: int | None = None


class SwitchError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"Switch returned {status}: {body[:300]}")
        self.status = status


def parse_sse(lines: Iterator[str]) -> Iterator[SseEvent]:
    """Turn raw SSE lines into events. Comments (keepalives) are skipped."""
    event, data, ev_id = "message", [], None
    for raw in lines:
        line = raw.rstrip("\r")
        if line == "":
            if data:
                payload = "\n".join(data)
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    parsed = {"raw": payload}
                yield SseEvent(event=event, data=parsed, id=ev_id)
            event, data, ev_id = "message", [], None
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field == "event":
            event = value
        elif field == "data":
            data.append(value)
        elif field == "id":
            ev_id = int(value) if value.isdigit() else None


class SwitchAgentClient:
    def __init__(self, base_url: str, agent_id: str, api_key: str, session: requests.Session | None = None):
        self.base = base_url.rstrip("/")
        self.agent_id = agent_id
        self.http = session or requests.Session()
        self.http.headers.update({"Authorization": f"Bearer {api_key}"})

    # ---- registration (out of band, with the registration token) --------
    @staticmethod
    def register(base_url: str, registration_token: str, name: str, description: str,
                 overwrite: bool = True, session: requests.Session | None = None) -> tuple[str, str]:
        """Register a custom always-on agent. Returns (agent_id, api_key); the key is shown once."""
        http = session or requests.Session()
        body = {
            "name": name,
            "description": description,
            "connector_type": "custom-python",
            "integration_profile": {
                "connection_model": "always_on",
                "message_exchange": True,
                "pre_invocation_mediation": [],
                "post_invocation_mediation": [],
                "event_reporting": [],
                "command_capabilities": {"reset": "unsupported", "compact": "unsupported",
                                         "interrupt": "unsupported"},
            },
            "tools": [],
            "models": [],
            "metadata": {"project": "shield-for-data"},
            "overwrite": overwrite,
        }
        r = http.post(f"{base_url.rstrip('/')}/agents", json=body,
                      headers={"Authorization": f"Bearer {registration_token}"}, timeout=30)
        if r.status_code >= 300:
            raise SwitchError(r.status_code, r.text)
        data = r.json()
        return data["id"], data["api_key"]

    # ---- the stream -------------------------------------------------------
    def events(self, connection_id: str, rooms: list[str] | None = None, last_event_id: int | None = None,
               filter_: str = "addressed", read_timeout: float = 60.0) -> Iterator[SseEvent]:
        params = {
            "connection_id": connection_id,
            "scope": "single" if rooms and len(rooms) == 1 else "all",
            "filter": filter_,
            "start_from": "head",
            "client": CLIENT_NAME,
            "client_version": CLIENT_VERSION,
        }
        if rooms:
            params["rooms"] = ",".join(rooms)
        headers = {"Accept": "text/event-stream"}
        if last_event_id is not None:
            headers["Last-Event-ID"] = str(last_event_id)
        r = self.http.get(f"{self.base}/agents/{self.agent_id}/events", params=params, headers=headers,
                          stream=True, timeout=(10, read_timeout))
        if r.status_code >= 300:
            raise SwitchError(r.status_code, r.text)
        try:
            yield from parse_sse(r.iter_lines(decode_unicode=True))
        finally:
            r.close()

    def beat(self, connection_id: str, cursor: int | None) -> dict:
        body = {"connection_id": connection_id}
        if cursor is not None:
            body["cursor"] = cursor
        r = self.http.post(f"{self.base}/agents/{self.agent_id}/connection/beat", json=body, timeout=10)
        if r.status_code >= 300:
            raise SwitchError(r.status_code, r.text)
        return r.json()

    # ---- operations ---------------------------------------------------------
    def op(self, name: str, args: dict | None = None, connection_id: str | None = None):
        headers = {"X-Switch-Connection-Id": connection_id} if connection_id else {}
        r = self.http.post(f"{self.base}/agents/{self.agent_id}/ops/{name}", json=args or {},
                           headers=headers, timeout=60)
        if r.status_code >= 300:
            raise SwitchError(r.status_code, r.text)
        return r.json().get("result")

    def post(self, room_id: str, content: str) -> dict:
        """Post to a room without needing a claimed connection."""
        r = self.http.post(f"{self.base}/agents/{self.agent_id}/message",
                           json={"room_id": room_id, "content": content}, timeout=30)
        if r.status_code >= 300:
            raise SwitchError(r.status_code, r.text)
        return r.json() if r.content else {}
