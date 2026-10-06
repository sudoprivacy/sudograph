"""Adversarial coverage, language and authorised-view boundaries on a non-demo DB."""

import base64
import copy
import gzip
import hashlib
import json
import sqlite3
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_relations import shop as shop_fixture

from compiler import app, bind, blind, browse, catalog, expr, spec
from compiler import gateway as gateway_module
from compiler.compile import compile_spec
from compiler.gateway import Denied, FileCapabilities, Gateway, NexusAuthority, View
from compiler.nexus import NexusClient
from compiler.serve import handler


@pytest.fixture
def shop(tmp_path):
    return shop_fixture.__wrapped__(tmp_path)


def test_coverage_requires_missing_columns_tables_and_refs(shop):
    load, _, _ = shop
    s = load()
    assert catalog.coverage(s)[0]["complete"]

    def omit(d):
        d["raw"]["R"]["coverage"] = "complete"
        del d["types"]["Category"]["props"]["name"]

    with pytest.raises(spec.SpecError, match=r"Category\.name"):
        load(omit)

    def ref(d):
        d["raw"]["R"]["coverage"] = "complete"
        d["types"]["Product"]["props"]["category"] = {
            "type": "number",
            "owner": "source",
            "column": "category",
        }

    with pytest.raises(spec.SpecError, match="no ref"):
        load(ref)


def test_identity_refuses_any_duplicate_source_key(shop):
    load, db, _ = shop
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE Duplicate AS SELECT 1 id UNION ALL SELECT 1")

    def change(d):
        d["types"]["Bad"] = {
            "label": "Bad",
            "backing": {"from": "R", "table": "Duplicate", "key": ["id"]},
            "props": {"id": {"type": "number", "owner": "source"}},
        }

    with pytest.raises(spec.SpecError, match="unique"):
        load(change)


def test_backing_filter_cannot_bypass_sql_parser(shop):
    load, _, _ = shop
    for sql in ["1=1; DROP TABLE Line", "id IN (SELECT id FROM Category)", "random() > 0"]:
        with pytest.raises(spec.SpecError, match="where"):
            load(lambda d, sql=sql: d["types"]["Category"]["backing"].update(where=sql))


def test_full_coverage_cannot_hide_filtered_rows(shop):
    load, _, _ = shop

    def change(d):
        d["raw"]["R"]["coverage"] = "complete"
        d["types"]["Line"]["backing"]["where"] = "market = 'A'"

    with pytest.raises(spec.SpecError, match="source rows outside bindings"):
        load(change)


def test_complete_source_with_no_bindings_is_refused(shop):
    load, _, _ = shop
    def omit_all(d):
        d['raw']['R']['coverage'] = 'complete'
        d['types'], d['nodes'], d['checks'] = {}, {}, {}
    with pytest.raises(spec.SpecError, match='no object binding'):
        load(omit_all)
    with pytest.raises(spec.SpecError, match='coverage must be'):
        load(lambda d: d['raw']['R'].update(coverage='compelete'))


def test_shared_source_projections_get_an_automatic_relationship(shop):
    load, _, _ = shop

    def change(d):
        d["types"]["ProductView"] = copy.deepcopy(d["types"]["Product"])

    view = compile_spec(load(change)).view
    assert any(
        e["rel"] == "same_source_key" and e["from"] == "Product" and e["to"] == "ProductView"
        for e in view["edges"]
    )


def test_private_oracle_cannot_be_exported_as_questions():
    with pytest.raises(ValueError, match="private oracle"):
        blind.public_only({"q1": {"answer": 42}})
    with pytest.raises(ValueError, match="answers"):
        blind.public_only(
            {
                "protocol": "test",
                "questions": [
                    {
                        "id": "1",
                        "source_object": "T",
                        "kind": "count",
                        "question": "Count?",
                        "answer": 42,
                    }
                ],
            }
        )


def test_empty_table_does_not_hide_a_misspelled_column(shop):
    load, _, _ = shop
    def change(d):
        d['types']['Line']['backing']['where'] = 'ord < 0'
        d['nodes']['sales']['op'] = 'SELECT SUM(typo) FROM Line'
    with pytest.raises(spec.SpecError, match='no property'):
        load(change)


def test_all_records_browsable_with_composite_identity(shop):
    load, _, _ = shop
    s = load()
    rows = browse.page(s, "Line", offset=2, limit=2)
    assert rows["total"] == 4
    assert [(r["order"], r["product"]) for r in rows["rows"]] == [(2, 20), (3, 10)]
    assert rows["rows"][0]["net"] == 20
    assert browse.page(s, "Line", where={"product": 10})["total"] == 2
    data = browse.snapshot(s, chunk_size=2)["Line"]
    assert len(data["chunks"]) == 2
    assert json.loads(gzip.decompress(base64.b64decode(data["index"]))) == [
        ["1·10", "1·11"],
        ["2·20", "3·10"],
    ]


def authority(tmp_path, grants):
    p = tmp_path / "policy.json"
    p.write_text(
        json.dumps(
            {
                "credentials": [
                    {
                        "sha256": hashlib.sha256(b"test-capability").hexdigest(),
                        "subject": "reader",
                        "grants": grants,
                    }
                ]
            }
        )
    )
    return FileCapabilities(p), p


def test_gateway_deny_discovery_export_and_revocation(shop, tmp_path):
    load, _, path = shop
    load()
    auth, policy = authority(tmp_path, {"public": ["read"]})
    gateway = Gateway({"public": View(str(path)), "secret": View(str(path))}, auth)
    assert gateway.discover("test-capability")["views"] == ["public"]
    for token, view, op in [
        ("", "public", "graph"),
        ("fake", "public", "page"),
        ("test-capability", "secret", "graph"),
        ("test-capability", "public", "export"),
    ]:
        with pytest.raises(Denied):
            gateway.execute(token, view, op)
    b = gateway.execute("test-capability", "public", "graph")
    assert b["coverage"] == []
    assert "shop.db" not in json.dumps(b)
    policy.write_text('{"credentials":[]}')
    with pytest.raises(Denied):
        gateway.execute(
            "test-capability", "public", "query", expression="SELECT COUNT(*) FROM Line"
        )


def test_gateway_scope_applies_to_counts_pages_aggregates_and_unloaded(shop, tmp_path, monkeypatch):
    load, _, path = shop
    load()
    auth, _ = authority(tmp_path, {"A": ["read", "export"]})
    gateway = Gateway({"A": View(str(path), at={"market": "A"})}, auth)
    monkeypatch.setattr(bind, "MAX_ROWS", 1)
    b = gateway.execute("test-capability", "A", "graph")
    view = b["views"]["|"]
    assert next(g["count"] for g in view["groups"] if g["type"] == "Line") == 2
    page = gateway.execute("test-capability", "A", "page", type="Line")
    assert page["total"] == 2
    assert {r["market"] for r in page["rows"]} == {"A"}
    assert (
        gateway.execute("test-capability", "A", "query", expression="SELECT SUM(net) FROM Line")[
            "value"
        ]
        == 29
    )
    with pytest.raises(ValueError):
        gateway.execute("test-capability", "A", "page", type="Line", at={"market": "B"})
    with pytest.raises(expr.ExprError):
        gateway.execute(
            "test-capability",
            "A",
            "query",
            expression="SELECT SUM(price) FROM Line JOIN Category ON 1=1",
        )


def test_registered_scope_is_present_on_the_first_binding_read(shop, tmp_path, monkeypatch):
    load, _, path = shop
    load()
    auth, _ = authority(tmp_path, {"A": ["read"]})
    counts, reads = [], []
    original_count, original_load = bind.count, bind.load

    def counted(s, tn, base):
        if tn == "Line":
            counts.append(s.backing_of(tn).get("where"))
        return original_count(s, tn, base)

    def loaded(s, tn, base):
        if tn == "Line":
            reads.append(s.backing_of(tn).get("where"))
        return original_load(s, tn, base)

    monkeypatch.setattr(bind, "count", counted)
    monkeypatch.setattr(bind, "load", loaded)
    Gateway({"A": View(str(path), at={"market": "A"})}, auth).execute(
        "test-capability", "A", "graph"
    )
    assert counts and reads
    assert all("market" in clause and "'A'" in clause for clause in [*counts, *reads])


def test_declared_business_language_requires_labels_descriptions_and_properties(shop):
    load, _, _ = shop
    s = load()
    required = {s.name}
    for block in (s.types, s.raw, s.hooks, s.nodes):
        required.update(d.get("label", name) for name, d in block.items())
    required.update(p for t in s.types.values() for p in t.get("props", {}))
    messages = {text: "Translated " + text for text in required}

    def translated(d):
        d["translations"] = {"en": messages}

    translated_spec = load(translated)
    assert compile_spec(translated_spec).values == compile_spec(s).values
    assert app.bundle(translated_spec)["translations"]["en"]["Sales"] == "Translated Sales"
    for missing in ("Sales", "net"):
        def incomplete(d, missing=missing):
            d["translations"] = {"en": {k: v for k, v in messages.items() if k != missing}}

        with pytest.raises(spec.SpecError, match="missing display text"):
            load(incomplete)


def test_nexus_adapter_propagates_caller_and_never_falls_back():
    calls = []

    class Client:
        def read(self, path, *, credential):
            calls.append((path, credential))
            if credential != "alice-token":
                raise PermissionError()
            return SimpleNamespace(
                content=json.dumps({"resource": "view/a", "subject": "alice", "actions": ["read"],
                                    "credential_sha256": hashlib.sha256(
                                        credential.encode()).hexdigest()}),
            )

    a = NexusAuthority(Client(), {"view/a": "/grants/a"})
    assert a.require("alice-token", "view/a", "read") == "alice"
    for token, action in [("bob-token", "read"), ("alice-token", "export")]:
        with pytest.raises(Denied):
            a.require(token, "view/a", action)
    assert calls[0] == ("/grants/a", "alice-token")


def test_nexus_transport_refuses_an_unverified_certificate_identity():
    with pytest.raises(ValueError, match="authenticated loopback"):
        NexusClient("other-host:2126")
    with pytest.raises(ValueError, match="certificate identity"):
        NexusClient("127.0.0.1:2126", tls={"cert": "node-cert.pem"})


def test_nexus_grants_are_bound_to_the_credential_and_actions_are_not_substrings():
    grant = {"resource": "sales", "subject": "alice", "actions": ["read"],
             "credential_sha256": hashlib.sha256(b"alice-token").hexdigest()}

    class Client:
        def read(self, path, *, credential):
            return SimpleNamespace(content=json.dumps(grant))

    authority = NexusAuthority(Client(), {"sales": "/grants/sales"})
    with pytest.raises(Denied):
        authority.require("bob-token", "sales", "read")
    grant["actions"] = "bread"
    with pytest.raises(Denied):
        authority.require("alice-token", "sales", "read")


def test_http_never_discloses_an_operator_spec_failure(tmp_path, monkeypatch):
    auth, _ = authority(tmp_path, {"public": ["read"]})
    gateway = Gateway({"public": View("operator-owned.yaml")}, auth)

    def broken(*args, **kwargs):
        raise spec.SpecError("PRIVATE SOURCE TABLE: 999 forbidden rows and hidden field")

    monkeypatch.setattr(gateway_module, "load", broken)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(gateway))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/v1",
            data=json.dumps({"operation": "graph", "view": "public"}).encode(),
            headers={"Authorization": "Bearer test-capability"},
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=5)
        assert error.value.code == 503
        result = json.load(error.value)
        assert result["error"] == "VIEW_UNAVAILABLE"
        assert "PRIVATE" not in json.dumps(result) and "999" not in json.dumps(result)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_blind_questions_come_from_raw_not_graph(shop, tmp_path):
    load, _, _ = shop
    s = load()
    public, oracle = blind.generate(s.raw["R"]["dsn"], s.source_base)
    assert len(public["questions"]) > 10
    assert all(set(q) == {"id", "source_object", "kind", "question"} for q in public["questions"])
    assert all("answer" not in q and "sql" not in q for q in public["questions"])
    q = next(
        q for q in public["questions"] if q["source_object"] == "Line" and q["kind"] == "count"
    )
    assert oracle[q["id"]]["answer"] == 4
    assert blind.grade(oracle, {})["passed"] == 0
    with pytest.raises(ValueError, match="separate"):
        blind.write_challenge(
            s.raw["R"]["dsn"], tmp_path / "q.json", tmp_path / "a.json", s.source_base
        )


def test_renderer_automatic_language_and_refuses_missing_translation(shop, tmp_path):
    load, _, _ = shop
    b = app.bundle(load())
    html = app.render(b)
    assert '"language": "auto"' in html and "navigator.language" in html
    template = tmp_path / "bad.html"
    template.write_text(
        Path(app.TEMPLATE).read_text(encoding="utf-8") + "<script>t('UNTRANSLATED')</script>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="UNTRANSLATED"):
        app.render(b, str(template))
