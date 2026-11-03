"""Lineage and ownership: who is affected when a table breaks.

Two implementations share one small interface:

* `MockCatalog` reads `catalog/lineage.yaml`. It is what the demo uses, so the
  project runs on a laptop or a free Codespace with no extra services.
* `OpenMetadataCatalog` speaks the OpenMetadata REST API (tables, lineage and
  feed threads). It is unit tested against recorded response shapes, not
  against a live OpenMetadata server; point `OPENMETADATA_URL` and
  `OPENMETADATA_TOKEN` at your instance to use it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import yaml


@dataclass
class Asset:
    name: str
    kind: str
    owners: list[str]
    downstream: list[str] = field(default_factory=list)


class Catalog(Protocol):
    def asset(self, name: str) -> Asset | None: ...

    def downstream(self, name: str) -> list[Asset]: ...

    def record_incident(self, name: str, title: str, body: str) -> str: ...


class MockCatalog:
    """Lineage from a YAML file, incidents appended to a JSON lines file."""

    def __init__(self, path: str | Path, incidents_path: str | Path | None = None):
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        self._assets = {
            name: Asset(name=name, kind=a.get("kind", "table"), owners=a.get("owners", []),
                        downstream=a.get("downstream", []))
            for name, a in data["assets"].items()
        }
        self.incidents_path = Path(incidents_path) if incidents_path else None
        self.incidents: list[dict] = []

    def asset(self, name: str) -> Asset | None:
        if name in self._assets:
            return self._assets[name]
        # upstream files are catalogued by pattern, e.g. "upstream:payments_*"
        for key, asset in self._assets.items():
            if key.endswith("*") and name.startswith(key[:-1]):
                return asset
        return None

    def names(self) -> list[str]:
        return [n for n in self._assets if not n.endswith("*")]

    def downstream(self, name: str) -> list[Asset]:
        seen: list[Asset] = []
        queue = list(self.asset(name).downstream) if self.asset(name) else []
        while queue:
            nxt = queue.pop(0)
            if any(a.name == nxt for a in seen):
                continue
            asset = self.asset(nxt)
            if asset:
                seen.append(asset)
                queue.extend(asset.downstream)
        return seen

    def record_incident(self, name: str, title: str, body: str) -> str:
        incident = {"id": f"INC-{len(self.incidents) + 1}", "asset": name, "title": title, "body": body}
        self.incidents.append(incident)
        if self.incidents_path:
            self.incidents_path.parent.mkdir(parents=True, exist_ok=True)
            with self.incidents_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(incident) + "\n")
        return incident["id"]


class OpenMetadataCatalog:
    """Adapter for the OpenMetadata REST API (v1).

    `fqn_prefix` maps Shield's short names to OpenMetadata fully qualified
    names, e.g. "shield_demo.warehouse" + "sales.orders".
    """

    def __init__(self, base_url: str, token: str, fqn_prefix: str = "", session=None, bot_name: str = "shield"):
        import requests

        self.base = base_url.rstrip("/") + "/api/v1"
        self.prefix = fqn_prefix.strip(".")
        self.bot = bot_name
        self.http = session or requests.Session()
        self.http.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})

    def _fqn(self, name: str) -> str:
        return f"{self.prefix}.{name}" if self.prefix and not name.startswith(self.prefix) else name

    def _short(self, fqn: str) -> str:
        return fqn[len(self.prefix) + 1:] if self.prefix and fqn.startswith(self.prefix + ".") else fqn

    def asset(self, name: str) -> Asset | None:
        r = self.http.get(f"{self.base}/tables/name/{self._fqn(name)}", params={"fields": "owners"})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        body = r.json()
        owners = [o.get("name") or o.get("displayName") for o in body.get("owners") or []]
        return Asset(name=name, kind="table", owners=[o for o in owners if o],
                     downstream=[a.name for a in self.downstream(name)])

    def downstream(self, name: str) -> list[Asset]:
        r = self.http.get(
            f"{self.base}/lineage/table/name/{self._fqn(name)}",
            params={"upstreamDepth": 0, "downstreamDepth": 3},
        )
        r.raise_for_status()
        body = r.json()
        nodes = {n["id"]: n for n in body.get("nodes", [])}
        out = []
        for edge in body.get("downstreamEdges", []):
            node = nodes.get(edge.get("toEntity"))
            if node:
                owners = [o.get("name") for o in node.get("owners") or [] if o.get("name")]
                out.append(Asset(name=self._short(node["fullyQualifiedName"]), kind=node.get("type", "table"),
                                 owners=owners))
        return out

    def record_incident(self, name: str, title: str, body: str) -> str:
        """Open a conversation thread on the table so the incident is visible in OpenMetadata."""
        payload = {
            "message": f"**{title}**\n\n{body}",
            "from": self.bot,
            "about": f"<#E::table::{self._fqn(name)}>",
        }
        r = self.http.post(f"{self.base}/feed", data=json.dumps(payload))
        r.raise_for_status()
        return r.json().get("id", "")


def owners_affected(catalog: Catalog, name: str) -> tuple[list[str], list[Asset]]:
    """Owners of the asset and of everything downstream, in a stable order."""
    asset = catalog.asset(name)
    downstream = catalog.downstream(name)
    owners: list[str] = []
    for a in ([asset] if asset else []) + downstream:
        for o in a.owners:
            if o not in owners:
                owners.append(o)
    return owners, downstream
