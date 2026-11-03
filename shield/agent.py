"""Run Shield as a Switch agent.

    python -m shield.agent --bootstrap   # register the agent and create the room (once)
    python -m shield.agent               # listen in the room and work with the team

Settings come from environment variables (see `.env.example`) and the state
file `.shield/agent.json` that `--bootstrap` writes.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import threading
import time
import uuid
from pathlib import Path

from .catalog import MockCatalog, OpenMetadataCatalog
from .desk import Desk
from .switch_client import SseEvent, SwitchAgentClient, SwitchError
from .warehouse import Warehouse

log = logging.getLogger("shield")

STATE_DIR = Path(os.environ.get("SHIELD_STATE_DIR", ".shield"))
STATE_FILE = STATE_DIR / "agent.json"
ROOM_NAME = os.environ.get("SHIELD_ROOM", "data-quality")
AGENT_NAME = os.environ.get("SHIELD_AGENT_NAME", "shield")
AUDIT_DOC = "Shield audit trail"
ROOM_INSTRUCTIONS = (
    "This room is where the data team and Shield keep sales.orders trustworthy. "
    "Shield scans, explains what it found and proposes a fix. A person approves, edits or rejects it here. "
    "Shield never changes data without an approval in this room."
)


def switch_url() -> str:
    return os.environ.get("SWITCH_URL", "http://localhost:18000")


def load_state() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))
    try:
        STATE_FILE.chmod(0o600)
    except OSError:
        pass


def make_catalog():
    if os.environ.get("OPENMETADATA_URL"):
        return OpenMetadataCatalog(os.environ["OPENMETADATA_URL"], os.environ.get("OPENMETADATA_TOKEN", ""),
                                   fqn_prefix=os.environ.get("OPENMETADATA_FQN_PREFIX", ""))
    return MockCatalog(os.environ.get("SHIELD_LINEAGE", "catalog/lineage.yaml"), STATE_DIR / "incidents.jsonl")


def open_to_room_members(agent_id: str) -> None:
    """Let the people in the room address Shield.

    Switch makes a newly registered agent answer only its owner. An agent
    registered with the server's registration token is owned by a bootstrap
    account, so nobody could talk to it. The Gateway admin clears that policy;
    who can reach Shield is then decided by who is in the room.
    """
    import requests

    email, password = os.environ.get("GATEWAY_ADMIN_EMAIL"), os.environ.get("GATEWAY_ADMIN_PASSWORD")
    if not (email and password):
        log.warning("GATEWAY_ADMIN_EMAIL/PASSWORD not set: only the agent owner can address Shield")
        return
    http = requests.Session()
    r = http.post(f"{switch_url()}/gateway/auth/login", json={"email": email, "password": password}, timeout=20)
    r.raise_for_status()
    r = http.put(f"{switch_url()}/gateway/agents/{agent_id}/addressing-policy", json={"policy": None}, timeout=20)
    r.raise_for_status()
    log.info("room members can now address %s", AGENT_NAME)


def bootstrap() -> dict:
    token = os.environ["AGENT_REGISTRATION_TOKEN"]
    humans = [u for u in os.environ.get("SHIELD_ROOM_USERS", "user").split(",") if u]
    agent_id, api_key = SwitchAgentClient.register(
        switch_url(), token, AGENT_NAME,
        "Data quality teammate: business-date gate, schema, volume, nulls, duplicates and upstream files.")
    client = SwitchAgentClient(switch_url(), agent_id, api_key)
    conn = str(uuid.uuid4())
    # Creating a room needs a live connection, so hold a stream open briefly.
    stream = client.events(conn, filter_="all", read_timeout=15)
    first = next(stream)
    assert first.event == "connection_state", first
    room = client.op("create_room", {
        "name": ROOM_NAME,
        "description": "Shield and the data team: data quality incidents for sales.orders",
        "agent_names": [AGENT_NAME],
        "user_names": humans,
        "channel_type": "channel_public",
        "instructions": ROOM_INSTRUCTIONS,
    }, connection_id=conn)
    stream.close()
    open_to_room_members(agent_id)
    state = {"agent_id": agent_id, "api_key": api_key, "room_id": room["id"],
             "connection_id": str(uuid.uuid4()), "audit_doc_id": None}
    save_state(state)
    log.info("registered %s (%s) and created room %s", AGENT_NAME, agent_id, room["id"])
    return state


class ShieldAgent:
    def __init__(self, state: dict, desk: Desk):
        self.state = state
        self.client = SwitchAgentClient(switch_url(), state["agent_id"], state["api_key"])
        self.room = state["room_id"]
        self.conn = state["connection_id"]
        self.desk = desk
        self.cursor: int | None = None
        self.inbox: queue.Queue[SseEvent] = queue.Queue()
        self.stop = threading.Event()
        desk.on_audit_change = self.publish_audit

    # ---- room context and the shared audit document ------------------------
    def join(self) -> None:
        ctx = self.client.op("connect_to_room", {"room_id": self.room}, connection_id=self.conn)
        for doc in ctx.get("documents") or []:
            if doc.get("name") == AUDIT_DOC:
                self.state["audit_doc_id"] = doc.get("id") or doc.get("document_id")
        save_state(self.state)
        log.info("connected to room %s with %d participants", self.room, len(ctx.get("participants") or []))

    def publish_audit(self, markdown: str) -> None:
        try:
            doc_id = self.state.get("audit_doc_id")
            if doc_id:
                self.client.op("update_room_document", {"document_id": doc_id, "content": markdown},
                               connection_id=self.conn)
            else:
                res = self.client.op("create_room_document", {
                    "name": AUDIT_DOC,
                    "description": "Every scan, approval, rejection and fix Shield ran in this room.",
                    "instructions": "Written by Shield. Read it to see who approved what and when.",
                    "content": markdown,
                }, connection_id=self.conn)
                self.state["audit_doc_id"] = res.get("document_id")
                save_state(self.state)
        except SwitchError as exc:  # the audit table in DuckDB stays the source of truth
            log.warning("could not update the room document: %s", exc)

    # ---- loops ---------------------------------------------------------------
    def heartbeat(self) -> None:
        while not self.stop.is_set():
            try:
                res = self.client.beat(self.conn, self.cursor)
                self.cursor = res.get("cursor", self.cursor)
            except SwitchError as exc:
                if exc.status in (404, 409):  # connection gone: the reader reopens the stream
                    pass
                else:
                    log.warning("heartbeat: %s", exc)
            except Exception as exc:  # network blip
                log.warning("heartbeat: %s", exc)
            self.stop.wait(2.0)

    def reader(self) -> None:
        last_id = None
        while not self.stop.is_set():
            try:
                for ev in self.client.events(self.conn, rooms=[self.room], last_event_id=last_id):
                    if ev.id is not None:
                        last_id = ev.id
                    if ev.event == "connection_state":
                        self.cursor = ev.data.get("cursor")
                        self.join()
                    elif ev.event == "message":
                        self.inbox.put(ev)
                    elif ev.event == "evicted":
                        log.warning("evicted: %s", ev.data.get("reason"))
                        break
            except Exception as exc:
                log.warning("stream closed (%s); reconnecting", exc)
            self.stop.wait(1.0)

    def worker(self) -> None:
        while not self.stop.is_set():
            try:
                ev = self.inbox.get(timeout=0.5)
            except queue.Empty:
                continue
            p = ev.data.get("payload", {})
            if not p.get("addressed") or ev.data.get("room_id") != self.room:
                continue
            sender = p.get("sender_name") or p.get("sender") or "someone"
            body = p.get("body", "")
            log.info("%s: %s", sender, body)
            try:
                replies = self.desk.handle(body, sender)
            except Exception as exc:  # never go silent in the room
                log.exception("desk failed")
                replies = [type("R", (), {"body": f":x: Shield hit an error: {exc}"})()]
            for reply in replies:
                self.say(reply.body)

    def say(self, text: str) -> None:
        for attempt in range(3):
            try:
                self.client.post(self.room, text)
                return
            except Exception as exc:
                log.warning("post failed (%s), retrying", exc)
                time.sleep(1 + attempt)

    def run(self) -> None:
        threads = [threading.Thread(target=t, daemon=True) for t in (self.heartbeat, self.reader, self.worker)]
        for t in threads:
            t.start()
        log.info("Shield is listening in room %s. Mention @%s in the channel.", self.room, AGENT_NAME)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop.set()


def load_dotenv(path: str = ".env") -> None:
    """Read KEY=VALUE lines written by scripts/up.sh without overriding the environment."""
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Shield, a data quality agent for Switch rooms")
    parser.add_argument("--bootstrap", action="store_true", help="register the agent and create the room")
    args = parser.parse_args()
    if args.bootstrap or not STATE_FILE.exists():
        bootstrap()
        if args.bootstrap:
            return
    wh = Warehouse.open(STATE_DIR / "warehouse.duckdb")
    if not wh.scalar("SELECT count(*) FROM sales.orders"):
        wh.reset()
    ShieldAgent(load_state(), Desk(wh, make_catalog())).run()


if __name__ == "__main__":
    main()
