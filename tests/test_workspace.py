"""Ordinary multi-session authoring without a GitLab approval dependency."""

import copy
import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
import yaml

from compiler import business, workspace
from compiler.model_contract import Refused
from tools.gitlab_stack import fixture_baseline


@pytest.fixture
def registered(tmp_path):
    baseline = fixture_baseline(tmp_path)
    store = workspace.Workspace.create(
        tmp_path / "model.db", baseline, namespace="tickets", language="en"
    )
    return store, baseline


def document(baseline, *, key="refund", concept="refund policy", statement="Refunds need review"):
    return {
        "format": business.FORMAT,
        "namespace": "tickets",
        "baseline": {"manifest": "registered-source-baseline", "sha256": business.digest(baseline)},
        "definitions": {
            key: {
                "concept": concept,
                "category": "meaning",
                "role": "business",
                "purpose": {"stakeholder": "Support manager", "decision": "Decide refund policy"},
                "label": concept,
                "statement": statement,
                "origin": "inferred",
                "contributor": "model",
                "version": 1,
                "targets": [],
            }
        },
    }


def request(store, doc, op="edit-1", base=None):
    return {
        "base_revision": base or store.contract()["revision"],
        "operation_id": op,
        "model": yaml.safe_dump(doc),
    }


def test_model_graph_context_and_retry_share_one_committed_revision(registered):
    store, baseline = registered
    before = store.contract()["revision"]
    edit = request(store, document(baseline))
    receipt = store.apply(edit, actor="alice")
    assert receipt["revision"] != before
    assert store.contract()["revision"] == receipt["revision"]
    packet = store.read()
    assert packet["revision"] == receipt["revision"]
    assert packet["inventory"]["definitions"] == 1
    assert packet["inventory"]["record_rows_preloaded"] == 0
    assert "refund policy" in store.read(product="html")
    assert receipt["revision"] in store.read(product="html")
    assert store.read(product="model")["projection"]["model_revision"] == receipt["revision"]
    assert store.read(revision=before)["inventory"]["definitions"] == 0
    assert workspace.Workspace(store.path).apply(edit, actor="alice") == receipt
    with pytest.raises(Refused, match="already used"):
        store.apply(edit, actor="bob")
    changed = {**edit, "model": yaml.safe_dump(document(baseline, statement="Different"))}
    with pytest.raises(Refused, match="already used"):
        store.apply(changed, actor="alice")


def test_invalid_identity_source_and_render_failure_preserve_all_products(registered, monkeypatch):
    store, baseline = registered
    before = store.contract()
    doc = document(baseline)
    doc["namespace"] = "another"
    with pytest.raises(Refused, match="namespace"):
        store.apply(request(store, doc), actor="alice")
    doc["namespace"] = "tickets"
    doc["baseline"]["sha256"] = "f" * 64
    with pytest.raises(Refused, match="source baseline"):
        store.apply(request(store, doc), actor="alice")
    monkeypatch.setattr(
        workspace.app,
        "render",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("renderer failed")),
    )
    with pytest.raises(RuntimeError, match="renderer failed"):
        store.apply(request(store, document(baseline)), actor="alice")
    assert store.contract() == before
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 0


def test_two_independent_writers_merge_distinct_concepts_from_same_revision(registered):
    store, baseline = registered
    base = store.contract()["revision"]
    edits = [
        request(store, document(baseline, key=key, concept=key), key, base)
        for key in ("refund", "revenue")
    ]

    def submit(edit):
        return workspace.Workspace(store.path).apply(edit, actor=edit["operation_id"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(submit, edits))
    assert sorted(r["merged"] for r in receipts) == [False, True]
    model = store.read(product="model")
    assert len(model["business"]["definitions"]) == 2
    assert store.apply(edits[0], actor="refund") == receipts[0]


def test_same_concept_renamed_key_conflicts_instead_of_allocating_duplicate(registered):
    store, baseline = registered
    seed = document(baseline)
    store.apply(request(store, seed), actor="alice")
    base = store.contract()["revision"]
    first = copy.deepcopy(seed)
    first["definitions"]["refund"]["version"] = 2
    first["definitions"]["refund"]["statement"] = "Exclude refunds"
    store.apply(request(store, first, "alice-2", base), actor="alice")
    second = copy.deepcopy(seed)
    second["definitions"]["renamed"] = second["definitions"].pop("refund")
    second["definitions"]["renamed"]["version"] = 2
    second["definitions"]["renamed"]["statement"] = "Include refunds"
    before = store.contract()["revision"]
    with pytest.raises(Refused) as error:
        store.apply(request(store, second, "bob-1", base), actor="bob")
    assert error.value.code == "MODEL_CONFLICT"
    assert error.value.recovery["paths"][0].startswith("definitions.")
    assert store.contract()["revision"] == before


def test_protocol_restores_persisted_store_and_refuses_caller_paths(registered):
    store, _baseline = registered
    requests = [
        {"operation": "contract"},
        {"operation": "apply", "request": {"path": "other.yaml"}},
        {"operation": "read", "product": "context"},
    ]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "compiler.workspace",
            "--store",
            str(store.path),
            "--actor",
            "alice",
        ],
        input="".join(json.dumps(r) + "\n" for r in requests),
        text=True,
        encoding="utf8",
        capture_output=True,
        check=True,
    )
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert [r["ok"] for r in replies] == [True, False, True]
    assert replies[0]["result"]["revision"] == replies[2]["result"]["revision"]
    assert replies[1]["error"]["code"] == "WRITE_CONTRACT"


def test_registration_never_rebinds_existing_store(registered):
    store, baseline = registered
    before = store.contract()
    with pytest.raises(FileExistsError):
        workspace.Workspace.create(store.path, baseline, namespace="other")
    assert store.contract() == before


def test_exact_context_reads_are_version_bound_and_keep_unbound_identity_when_bound(registered):
    store, baseline = registered
    doc = document(baseline)
    first = store.apply(request(store, doc), actor="alice")
    packet = store.read()
    identity = next(iter(store.read(product="model")["business"]["definitions"]))
    read = {
        "revision": first["revision"],
        "context_digest": packet["context_digest"],
        "id": identity,
    }
    assert store.context_read(read)["definition"]["statement"] == "Refunds need review"
    with pytest.raises(Refused, match="digest"):
        store.context_read({**read, "context_digest": "stale"})
    obj = baseline["source_schema"]["sources"][0]["objects"][0]
    doc["definitions"]["refund"].update(version=2, targets=[obj["id"]])
    store.apply(request(store, doc, "bind-1"), actor="alice")
    assert list(store.read(product="model")["business"]["definitions"]) == [identity]
    assert store.context_read(read)["definition"]["targets"] == []


def test_worker_crash_before_commit_keeps_head_and_allows_same_operation_retry(registered):
    store, baseline = registered
    before = store.contract()
    edit = request(store, document(baseline))
    script = """
import json, os, sys
from compiler.workspace import Workspace
insert = Workspace._insert
def interrupted(*args, **kwargs):
    insert(*args, **kwargs)
    os._exit(91)
Workspace._insert = staticmethod(interrupted)
Workspace(sys.argv[1]).apply(json.loads(sys.argv[2]), actor="alice")
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(store.path), json.dumps(edit)],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 91
    assert store.contract() == before
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 0
    receipt = workspace.Workspace(store.path).apply(edit, actor="alice")
    assert store.contract()["revision"] == receipt["revision"]


def test_malformed_exact_reads_return_contract_errors_without_changing_head(registered):
    store, _baseline = registered
    packet = store.read()
    read = {
        "revision": packet["revision"],
        "context_digest": packet["context_digest"],
        "id": "catalog",
    }
    for bad in (
        {"id": []},
        {"revision": {}},
        {"context_digest": {}},
        {"offset": True},
        {"limit": []},
        {"records": "yes"},
    ):
        with pytest.raises(Refused):
            store.context_read({**read, **bad})
    with pytest.raises(Refused, match="product"):
        store.read(product=[])
    assert store.contract()["revision"] == packet["revision"]


def test_context_compiles_pointers_for_the_actual_mcp_tool_contract(registered):
    store, _baseline = registered
    packet = store.read()
    block = next(block for block in packet["blocks"] if block["id"] == "pointers")
    pointers = yaml.safe_load(block["text"].split("\n", 1)[1])
    assert pointers["transport"]["protocol"] == "mcp"
    request = pointers["requests"]["catalog"]
    assert request["tool"] == "sudograph_context_read"
    assert "operation" not in request["arguments"]
    assert store.context_read(request["arguments"])["sources"]
    assert pointers["requests"]["refresh"] == {"tool": "sudograph_context", "arguments": {}}
    assert packet["context_digest"] in store.read(product="html")
