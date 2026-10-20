"""Knowledge fidelity, dependency completeness, pagination and version boundaries."""

import copy

import pytest
from test_business import base as business_fixture

from compiler import app, business, html_export
from compiler.context import Reader


@pytest.fixture
def reader(tmp_path):
    model, doc = business_fixture.__wrapped__(tmp_path)
    subject = doc["definitions"]["observed-total"]
    doc["definitions"]["policy"] = {
        "concept": "budget precision", "category": "rule", "role": "business",
        "label": "Precision", "statement": "Retain source precision until display.",
        "origin": "inferred", "contributor": "model", "version": 1,
        "targets": subject["targets"], "applies_to": ["observed-total"],
    }
    doc["views"]["meaning"]["definitions"].append("policy")
    return Reader(business.build(doc, model)), model, doc


def test_exact_knowledge_uses_existing_identities_and_keeps_proposal_state(reader):
    r, baseline, _ = reader
    pack = r.pack()
    assert pack == r.pack()
    assert pack["inventory"] == {
        "objects": 2, "fields": 3, "definitions": 3, "record_rows_preloaded": 0,
    }
    assert "SUM(amount)" in pack["text"]
    for key, node in r.definitions.items():
        assert key in pack["text"] and node["statement"] in pack["text"]
        assert node["review_status"] == "unreviewed"
    assert "gzip" not in pack["text"] and "dictionaries:" not in pack["text"]
    assert "dsn:" not in pack["text"] and "raw:" not in pack["text"]
    assert pack["sudocode"]["_meta"]["sudocode"]["appendSystemPrompt"] == pack["text"]
    assert r.model["source_schema"] == baseline["source_schema"]
    assert r.read("catalog")["business_views"] == r.model["business"]["views"]


def test_reader_preview_uses_the_same_context_compiler_without_record_preload(reader, tmp_path):
    r, _, _ = reader
    path = tmp_path / 'reader.html'
    path.write_text(app.render(r.model), encoding='utf8')
    preview = html_export.model(path)['ui']['agent_context']
    packet = r.pack()
    assert preview == {k: v for k, v in packet.items() if k not in {'text', 'sudocode'}}
    assert preview['inventory']['record_rows_preloaded'] == 0
    assert 'unreviewed' in next(b['text'] for b in preview['blocks']
                                if b['id'] == 'business_definitions')


def test_lookup_follows_both_forward_references_and_attached_rules(reader):
    r, _, _ = reader
    metric = next(k for k, n in r.definitions.items() if n["key"] == "observed-total")
    policy = next(k for k, n in r.definitions.items() if n["key"] == "policy")
    assert policy in r.read(metric)["related"]
    assert metric in r.read(policy)["related"]
    assert r.read(metric)["definition"] == r.definitions[metric]
    with pytest.raises(ValueError, match="unknown identity"):
        r.read("a-name-that-is-not-a-canonical-id")


def test_paged_snapshot_retains_columns_primary_key_null_and_view_values(reader):
    r, _, _ = reader
    ticket = next(o["id"] for o in r.objects.values() if o["name"] == "Tickets")
    totals = next(o["id"] for o in r.objects.values() if o["name"] == "Totals")
    page = r.page(ticket, limit=1)
    assert page["columns"] == ["id", "amount"] and page["keys"] == ["id"]
    assert page["rows"] == [[1, 7.0]] and page["next_offset"] == 1
    assert r.page(ticket, offset=1)["rows"] == [[2, None]]
    assert r.page(totals)["rows"] == [[7.0]]
    assert r.page(ticket, offset=999)["rows"] == []
    for params in [{"limit": 101}, {"limit": True}, {"offset": -1}]:
        with pytest.raises(ValueError, match="limit"):
            r.page(ticket, **params)
    with pytest.raises(ValueError, match="source object"):
        r.page(next(iter(r.fields)))


def test_changed_business_reuses_identity_and_preserves_source_prompt_prefix(reader):
    original, baseline, doc = reader
    doc = copy.deepcopy(doc)
    doc["definitions"]["observed-total"].update(statement="A revised budget proposal.", version=2)
    changed = Reader(business.build(doc, baseline))
    assert original.pack()["blocks"][0] == changed.pack()["blocks"][0]
    assert set(original.definitions) == set(changed.definitions)
    assert original.digest != changed.digest
    tampered = copy.deepcopy(original.model)
    next(iter(tampered["business"]["definitions"].values()))["review_status"] = "confirmed"
    with pytest.raises(ValueError, match=r"rebuild through compiler\.business"):
        Reader(tampered)


def test_checked_structure_alone_works_and_missing_record_pointer_is_explicit(reader):
    _, baseline, _ = reader
    r = Reader(baseline)
    assert r.pack()["inventory"]["definitions"] == 0
    bare = copy.deepcopy(baseline)
    bare["source_schema"].update(record_complete=False, snapshots={}, segments={}, dictionaries={})
    r = Reader(bare)
    with pytest.raises(ValueError, match="not registered"):
        r.page(next(iter(r.objects)))


def test_operator_pointers_expose_discovery_without_database_credentials(reader):
    original, _, _ = reader
    pointer = {"name": "customer-records", "kind": "data_gateway",
               "uri": "https://data.example/v1", "description": "Discover authorised data views."}
    r = Reader(original.model, pointers=[pointer])
    assert pointer["uri"] in r.pack()["text"]
    assert original.digest != r.digest
    for uri in ["sqlite:///private.db", "https://user:password@data.example/v1",
                "https://data.example/v1?token=secret", "http://data.example/v1"]:
        with pytest.raises(ValueError, match="credential-free"):
            Reader(original.model, pointers=[{**pointer, "uri": uri}])
