import json

from shield.catalog import MockCatalog, OpenMetadataCatalog, owners_affected
from shield.switch_client import SwitchAgentClient, parse_sse


def test_mock_catalog_walks_lineage(catalog):
    owners, downstream = owners_affected(catalog, "sales.orders")
    assert owners == ["orders-team", "finance-analytics", "ml-platform", "bi-team"]
    assert [a.name for a in downstream] == ["finance.revenue_daily", "ml.churn_features",
                                            "dashboard.daily_revenue"]


def test_mock_catalog_matches_upstream_file_patterns(catalog):
    owners, _ = owners_affected(catalog, "upstream:payments_2026-11-05.csv")
    assert owners[0] == "payments-team"


def test_mock_catalog_writes_incidents(tmp_path):
    from pathlib import Path

    cat = MockCatalog(Path(__file__).resolve().parents[1] / "catalog" / "lineage.yaml", tmp_path / "inc.jsonl")
    assert cat.record_incident("sales.orders", "t", "b") == "INC-1"
    assert json.loads((tmp_path / "inc.jsonl").read_text())["asset"] == "sales.orders"


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body or {}
        self.text, self.content = json.dumps(self._body), b"x"

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, routes):
        self.routes, self.calls, self.headers = routes, [], {}

    def _hit(self, method, url, **kw):
        self.calls.append((method, url, kw))
        for (m, suffix), resp in self.routes.items():
            if m == method and url.endswith(suffix):
                return resp
        return FakeResponse(404)

    def get(self, url, **kw):
        return self._hit("GET", url, **kw)

    def post(self, url, **kw):
        return self._hit("POST", url, **kw)


def test_openmetadata_adapter_shapes():
    lineage = {
        "nodes": [{"id": "n1", "fullyQualifiedName": "demo.wh.finance.revenue_daily", "type": "table",
                   "owners": [{"name": "finance-analytics"}]}],
        "downstreamEdges": [{"fromEntity": "n0", "toEntity": "n1"}],
    }
    s = FakeSession({
        ("GET", "/tables/name/demo.wh.sales.orders"): FakeResponse(body={"owners": [{"name": "orders-team"}]}),
        ("GET", "/lineage/table/name/demo.wh.sales.orders"): FakeResponse(body=lineage),
        ("POST", "/feed"): FakeResponse(body={"id": "thread-1"}),
    })
    om = OpenMetadataCatalog("http://om:8585", "tok", fqn_prefix="demo.wh", session=s)
    owners, downstream = owners_affected(om, "sales.orders")
    assert owners == ["orders-team", "finance-analytics"]
    assert downstream[0].name == "finance.revenue_daily"
    assert om.record_incident("sales.orders", "Shield F-1", "stale") == "thread-1"
    method, url, kw = s.calls[-1]
    assert url == "http://om:8585/api/v1/feed"
    assert json.loads(kw["data"])["about"] == "<#E::table::demo.wh.sales.orders>"
    assert s.headers["Authorization"] == "Bearer tok"


def test_parse_sse_frames_and_keepalives():
    lines = [
        "event: connection_state", 'data: {"cursor": 7}', "",
        ": keepalive", "",
        "id: 8", "event: message", 'data: {"payload": {"body": "@shield scan", "addressed": true}}', "",
    ]
    events = list(parse_sse(iter(lines)))
    assert [e.event for e in events] == ["connection_state", "message"]
    assert events[0].data["cursor"] == 7 and events[1].id == 8
    assert events[1].data["payload"]["addressed"] is True


def test_register_sends_an_always_on_custom_profile():
    s = FakeSession({("POST", "/agents"): FakeResponse(body={"id": "a1", "api_key": "k1"})})
    assert SwitchAgentClient.register("http://sw:8000/", "reg", "shield", "d", session=s) == ("a1", "k1")
    _, url, kw = s.calls[0]
    assert url == "http://sw:8000/agents"
    assert kw["json"]["integration_profile"]["connection_model"] == "always_on"
    assert kw["headers"]["Authorization"] == "Bearer reg"
