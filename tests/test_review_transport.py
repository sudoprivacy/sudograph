"""Canonical review uses the committed model and reauthorizes every source page."""

import copy
import hashlib
import json
import sqlite3
import subprocess
import sys
import threading
from contextlib import closing, contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
import yaml

from compiler import app, business, project, spec
from compiler.gateway import Denied, FileCapabilities
from compiler.model_contract import Refused
from compiler.review import ReviewGateway
from compiler.review_host import execute as host_review
from compiler.serve import handler
from compiler.workspace import Workspace
from tools.gitlab_stack import fixture_baseline

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "review-test-capability"


def test_private_host_review_reuses_the_registered_model_and_keeps_export_separate(registered):
    _, store, _, source, objects = registered
    head = host_review(store, "host-alice", "support", {"operation": "head"})
    html = host_review(store, "host-alice", "support", {
        "operation": "html", "endpoint": "/review/binding_123/v1",
    })
    assert head["revision"] in html and '"endpoint": "/review/binding_123/v1"' in html
    assert str(source) not in html and "source-only-value-1" not in html
    page = host_review(store, "host-alice", "support", {
        "operation": "page", "params": {**head, "id": objects["Tickets"], "limit": 2},
    })
    assert len(page["rows"]) == 2 and page["rows"][0][1] == "source-only-value-1"
    with pytest.raises(Denied):
        host_review(store, "host-alice", "support", {"operation": "export"})
    assert '"review_transport"' not in host_review(
        store, "host-alice", "support", {"operation": "export"}, export=True,
    )


def test_legacy_inline_source_records_cannot_bypass_the_export_grant(registered, tmp_path):
    gateway, original, policy, _, _ = registered
    baseline = copy.deepcopy(original.read(product="model"))
    view = baseline["views"][next(iter(baseline["views"]))]
    view["groups"][0]["members"] = [{"id": 1, "props": {"note": "legacy-row-marker"}}]
    # Retained old history can contain scalar-view members without a separate
    # snapshot payload. Do not silently alter that history or treat it as live.
    legacy = Workspace.create(tmp_path / "legacy.db", baseline, namespace="support")
    protected = ReviewGateway({"support": legacy}, gateway.authority)
    for operation in (lambda: protected.html(TOKEN, "support"),
                      lambda: protected.execute(TOKEN, "support", "graph")):
        with pytest.raises(Denied):
            operation()
    grants = json.loads(policy.read_text())
    grants["credentials"][0]["grants"]["support"].append("export")
    policy.write_text(json.dumps(grants))
    assert "legacy-row-marker" in protected.html(TOKEN, "support")


@pytest.mark.parametrize("endpoint", [
    "https://evil.test/v1", "//evil.test/v1", "/review/../v1", "/review/a/v1?token=x",
    "/review/a/v1#x", "/review/a%2fb/v1", "/review/a/../../v1", None,
])
def test_review_transport_refuses_untrusted_routes(registered, endpoint):
    _, store, _, _, _ = registered
    with pytest.raises(ValueError):
        host_review(store, "host-alice", "support", {"operation": "html", "endpoint": endpoint})


def test_private_review_worker_does_not_accept_browser_selected_bindings(registered):
    _, store, _, source, _ = registered
    def call(request):
        result = subprocess.run(
            [sys.executable, "-m", "compiler.review_host", "--store", str(store.path),
             "--actor", "host-alice", "--resource", "support"],
            input=request, text=True, capture_output=True, check=True, cwd=ROOT,
            encoding="utf8",
        )
        return json.loads(result.stdout)

    assert call('{"operation":"head"}')["result"] == store.head()
    for request in [
        {"operation": "head", "store": str(source)},
        {"operation": "head", "actor": "other"},
        {"operation": "head", "resource": "other"},
        {"operation": "apply", "params": {}},
        {"operation": "page", "params": {"source": str(source)}},
    ]:
        response = call(json.dumps(request))
        assert response["ok"] is False and str(source) not in json.dumps(response)
    assert call('{"operation":"export"}')["error"]["code"] == "ACCESS_DENIED"
    assert call(" " * 65537)["error"]["code"] == "READ_CONTRACT"


@pytest.fixture
def registered(tmp_path):
    source = tmp_path / "private #source.db"
    with closing(sqlite3.connect(source)) as db, db:
        db.executescript("""
            CREATE TABLE Tickets(id INTEGER PRIMARY KEY, note TEXT, picture BLOB);
            CREATE VIEW Notes AS SELECT note FROM Tickets;
        """)
        db.executemany("INSERT INTO Tickets VALUES (?, ?, X'00FF')",
                       [(i, f"source-only-value-{i}") for i in range(1, 112)])
    dsn = "sqlite:///" + source.as_posix()
    config = tmp_path / "source.yaml"
    config.write_text(yaml.safe_dump(project.draft(dsn)), encoding="utf8")
    baseline = app.bundle(spec.load(str(config)), records=False)
    schema = baseline["source_schema"]["sources"][0]
    store = Workspace.create(tmp_path / "model.db", baseline, namespace="support", language="en",
                             record_sources={schema["id"]: dsn})
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"credentials": [{
        "sha256": hashlib.sha256(TOKEN.encode()).hexdigest(),
        "subject": "reviewer", "grants": {"support": ["read"]},
    }]}), encoding="utf8")
    gateway = ReviewGateway({"support": store, "hidden": store}, FileCapabilities(policy))
    objects = {obj["name"]: obj["id"] for obj in schema["objects"]}
    return gateway, store, policy, source, objects


def test_graph_context_pages_and_html_use_one_committed_model(registered):
    gateway, store, _, source, objects = registered
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    head = gateway.execute(TOKEN, "support", "head")
    graph = gateway.execute(TOKEN, "support", "graph")
    context = gateway.execute(TOKEN, "support", "context")
    html = gateway.html(TOKEN, "support")
    assert graph == store.read(product="model")
    assert graph["projection"]["model_revision"] == head["revision"] == context["revision"]
    assert not graph["records"] and not graph["source_schema"]["snapshots"]
    assert context["inventory"]["record_rows_preloaded"] == 0
    assert head["revision"] in html and '"review_transport"' in html
    for value in (json.dumps(graph), json.dumps(context), html):
        assert "source-only-value-1" not in value
        assert str(source) not in value and "sqlite:///" not in value
    page = gateway.execute(TOKEN, "support", "page", **head, id=objects["Tickets"],
                           offset=50, limit=50)
    assert page["columns"] == ["id", "note", "picture"]
    assert page["rows"][0][:2] == [51, "source-only-value-51"]
    assert page["rows"][0][2]["$binary"] == "AP8="
    assert page["next_offset"] == 100 and len(page["rows"]) == 50
    assert page["total"] == 111 and page["revision"] == head["revision"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_discovery_export_and_revocation_are_enforced_for_every_read(registered):
    gateway, _, policy, _, objects = registered
    assert gateway.discover(TOKEN)["views"] == ["support"]
    assert gateway.discover("")["views"] == []
    head = gateway.execute(TOKEN, "support", "head")
    for operation in ("head", "graph", "context", "page", "export"):
        with pytest.raises(Denied):
            gateway.execute(TOKEN, "hidden", operation)
    with pytest.raises(Denied):
        gateway.execute(TOKEN, "support", "export")
    payload = json.loads(policy.read_text())
    payload["credentials"][0]["grants"]["support"].append("export")
    policy.write_text(json.dumps(payload))
    exported = gateway.execute(TOKEN, "support", "export")
    assert '"review_transport"' not in exported  # Portable files have no live host binding.
    policy.write_text('{"credentials":[]}')
    with pytest.raises(Denied):
        gateway.html(TOKEN, "support")
    for operation in ("head", "graph", "context", "export"):
        with pytest.raises(Denied):
            gateway.execute(TOKEN, "support", operation)
    with pytest.raises(Denied):
        gateway.execute(TOKEN, "support", "page", **head, id=objects["Tickets"])


def test_frozen_record_bytes_require_export_even_when_requested_as_a_graph(registered, tmp_path):
    gateway, _, policy, _, _ = registered
    fixture = tmp_path / "frozen-fixture"
    fixture.mkdir()
    store = Workspace.create(fixture / "model.db", fixture_baseline(fixture), namespace="frozen")
    frozen = ReviewGateway({"support": store}, gateway.authority)
    for action in (lambda: frozen.html(TOKEN, "support"),
                   lambda: frozen.execute(TOKEN, "support", "graph")):
        with pytest.raises(Denied):
            action()
    assert frozen.execute(TOKEN, "support", "context")["inventory"]["record_rows_preloaded"] == 0
    payload = json.loads(policy.read_text())
    payload["credentials"][0]["grants"]["support"].append("export")
    policy.write_text(json.dumps(payload))
    assert frozen.execute(TOKEN, "support", "graph")["source_schema"]["snapshots"]
    assert '"review_transport"' in frozen.html(TOKEN, "support")


def test_page_version_identity_scope_and_source_drift_cannot_be_substituted(registered):
    gateway, _, _, source, objects = registered
    head = gateway.execute(TOKEN, "support", "head")
    page = {**head, "id": objects["Tickets"]}
    for changes, code in [
        ({"context_digest": "other"}, "CONTEXT_STALE"),
        ({"revision": "other"}, "REVISION_UNKNOWN"),
        ({"source": "sqlite:///another.db"}, "READ_CONTRACT"),
    ]:
        with pytest.raises(Refused) as refused:
            gateway.execute(TOKEN, "support", "page", **{**page, **changes})
        assert refused.value.code == code
    for changes in ({"id": "Tickets"}, {"id": objects["Tickets"] + "/field/note"},
                    {"limit": 101}, {"offset": True}):
        with pytest.raises(ValueError):
            gateway.execute(TOKEN, "support", "page", **{**page, **changes})
    with closing(sqlite3.connect(source)) as db, db:
        db.execute("ALTER TABLE Tickets ADD COLUMN changed TEXT")
    with pytest.raises(Refused) as refused:
        gateway.execute(TOKEN, "support", "page", **page)
    assert refused.value.code == "SOURCE_SCHEMA_CHANGED"
    assert gateway.execute(TOKEN, "support", "head") == head


def test_review_advances_only_after_a_successful_checked_edit(registered):
    gateway, store, _, _, _ = registered
    contract = store.contract()
    # More than ten compiler row-completeness entries must survive JSON storage
    # without changing the baseline pin used by the next ordinary model edit.
    with store._db() as db:
        baseline = json.loads(db.execute("SELECT payload FROM settings").fetchone()[0])["baseline"]
    assert contract["baseline"]["sha256"] == business.digest(baseline)
    doc = {"format": business.FORMAT, "namespace": "support", "baseline": contract["baseline"],
           "definitions": {"policy": {
               "concept": "refund policy", "category": "meaning", "role": "business",
               "purpose": {"stakeholder": "Support manager", "decision": "Review refunds"},
               "label": "Refund policy", "statement": "Refunds need review",
               "origin": "inferred", "contributor": "model", "version": 1, "targets": [],
           }}}
    receipt = store.apply({"base_revision": contract["revision"], "operation_id": "edit-1",
                           "model": yaml.safe_dump(doc)}, actor="host-reviewer")
    assert gateway.execute(TOKEN, "support", "head")["revision"] == receipt["revision"]
    assert "Refunds need review" in gateway.html(TOKEN, "support")
    with pytest.raises(ValueError):
        store.apply({"base_revision": receipt["revision"], "operation_id": "broken",
                     "model": "not valid model input"}, actor="host-reviewer")
    assert gateway.execute(TOKEN, "support", "head")["revision"] == receipt["revision"]


@contextmanager
def running(gateway, **options):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(gateway, **options))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def http(base, path="/v1", body=None, token=TOKEN):
    request = Request(base + path, headers={"Authorization": "Bearer " + token},
                      data=None if body is None else json.dumps(body).encode())
    try:
        return urlopen(request, timeout=5)
    except HTTPError as error:
        return error


def test_real_http_keeps_typed_refusals_and_does_not_expose_ungranted_html(registered):
    gateway, _, _, _, objects = registered
    with running(gateway) as base:
        with http(base, "/review/support") as reply:
            assert reply.status == 200 and reply.headers["Cache-Control"] == "no-store"
            assert reply.headers["Content-Type"].startswith("text/html")
            assert b"review_transport" in reply.read()
        for path, token in (("/review/support", ""), ("/review/hidden", TOKEN)):
            with http(base, path, token=token) as reply:
                assert reply.status == 403 and "source-only-value" not in reply.read().decode()
        head = gateway.execute(TOKEN, "support", "head")
        body = {"view": "support", "operation": "page", "params": {
            **head, "context_digest": "stale", "id": objects["Tickets"],
        }}
        with http(base, body=body) as reply:
            assert reply.status == 409
            assert json.load(reply)["error"] == "CONTEXT_STALE"
        body["params"]["context_digest"] = head["context_digest"]
        with http(base, body=body) as reply:
            assert json.load(reply)["result"]["rows"][0][:2] == [1, "source-only-value-1"]
        with http(base, body={**body, "source": "arbitrary"}) as reply:
            assert reply.status == 400


def test_trusted_host_can_reuse_existing_session_resolution(registered):
    gateway, _, _, _, _ = registered
    def session(request):
        return TOKEN if request.headers.get("Cookie") == "host-session=bound" else ""

    with running(gateway, credential_resolver=session) as base:
        with http(base, "/review/support") as reply:
            assert reply.status == 403  # The host resolver remains the sole identity source.
        with urlopen(Request(base + "/review/support", headers={
            "Cookie": "host-session=bound",
        }), timeout=5) as reply:
            assert reply.status == 200


def test_browser_page_request_is_exact_and_rejects_mixed_revisions():
    script = """
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const packet={revision:'r1',context_digest:'d1'};
global.BUNDLE={ui:{review_transport:{endpoint:'/v1',resource:'support'},agent_context:packet}};
vm.runInThisContext(fs.readFileSync('./app/schema.js','utf8'));
(async()=>{
 let request;
 global.fetch=async(url,options)=>{request={url,options};return {ok:true,json:async()=>({result:{
   ...packet,source_object:'obj1',offset:50,rows:[[51,'same row']]}})}};
 assert.equal((await reviewSourcePage('obj1',50,50)).rows[0][0],51);
 assert.equal(request.url,'/v1');assert.equal(request.options.credentials,'same-origin');
 assert.deepEqual(JSON.parse(request.options.body),{view:'support',operation:'page',params:{
   ...packet,id:'obj1',offset:50,limit:50}});
 global.fetch=async()=>({ok:true,json:async()=>({result:{...packet,revision:'r2',rows:[]}})});
 await assert.rejects(()=>reviewSourcePage('obj1',50,50),/displayed model/);
 global.fetch=async()=>({ok:false,status:403});
 await assert.rejects(()=>reviewSourcePage('obj1',50,50),/unavailable/);
 console.log('passed');
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True,
                            text=True, check=True, timeout=10)
    assert result.stdout.strip() == "passed"
