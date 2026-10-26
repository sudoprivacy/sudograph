"""Provenance and canonical definition contracts on unrelated source data."""

import copy
import hashlib
import json
import sqlite3

import pytest
import yaml

from compiler import app, business, project, spec


@pytest.fixture
def base(tmp_path):
    db = tmp_path / "unrelated.db"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE Tickets(id INTEGER PRIMARY KEY, amount REAL);
            INSERT INTO Tickets VALUES(1,7),(2,NULL);
            CREATE VIEW Totals AS SELECT SUM(amount) total FROM Tickets;
        """)
    path = tmp_path / "source.yaml"
    path.write_text(yaml.safe_dump(project.draft("sqlite:///" + db.as_posix())), encoding="utf8")
    model = app.bundle(spec.load(str(path)), records=True)
    obj = next(o for o in model["source_schema"]["sources"][0]["objects"] if o["name"] == "Totals")
    doc = {
        "format": business.FORMAT,
        "namespace": "support",
        "baseline": {"manifest": "baseline.json", "sha256": "example-pin"},
        "definitions": {
            "observed-total": {
                "concept": "source total",
                "category": "meaning",
                "role": "business",
                "purpose": {
                    "stakeholder": "Support manager",
                    "decision": "Review the available support budget.",
                },
                "label": "Source total",
                "statement": "The source sums amount.",
                "origin": "provided",
                "contributor": "source",
                "version": 1,
                "targets": [obj["id"]],
                "evidence": [{"kind": "source_sql", "ref": obj["id"], "quote": "SUM(amount)"}],
            },
            "refund-question": {
                "concept": "refund policy",
                "category": "meaning",
                "role": "business",
                "purpose": {
                    "stakeholder": "Support manager",
                    "decision": "Choose the refund treatment for the support budget.",
                },
                "label": "Refunds",
                "statement": "Should refunds reduce this amount?",
                "origin": "inferred",
                "contributor": "model",
                "version": 1,
                "targets": [obj["id"]],
            },
        },
        "views": {
            "meaning": {"label": "Meaning", "definitions": ["observed-total", "refund-question"]},
            "questions": {"label": "Questions", "definitions": ["refund-question"]},
        },
    }
    return model, doc


def test_separate_view_preserves_every_source_value_and_reuses_definition_identity(base):
    model, doc = base
    old = copy.deepcopy(model)
    overlay = business.build(doc, model)
    business.validate(overlay)
    assert model == old and overlay["source_schema"] == old["source_schema"]
    assert overlay["views"] == old["views"] and overlay["records"] == old["records"]
    for key in ("source_schema", "views", "records"):
        assert overlay[key] is model[key]
    views = overlay["business"]["views"]
    assert views["questions"]["definitions"][0] == views["meaning"]["definitions"][1]
    assert len(overlay["business"]["definitions"]) == 2
    assert {n["review_status"] for n in overlay["business"]["definitions"].values()} == {
        "unreviewed"
    }


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("origin", None, "origin"),
        ("origin", "confirmed", "origin"),
        ("contributor", "model", "contributor"),
        ("contributor", None, "contributor"),
        ("contributor", "business_user", "supplied document quote"),
        ("targets", ["invented/field"], "source ID"),
        ("version", 0, "positive integer"),
        ("evidence", [], "provided claims"),
        (
            "evidence",
            [{"kind": "source_sql", "ref": "wrong", "quote": "SUM(amount)"}],
            "quote is absent",
        ),
    ],
)
def test_missing_origin_unknown_refs_and_uncited_provided_claims_are_refused(
    base, field, value, error
):
    model, doc = base
    doc["definitions"]["observed-total"][field] = value
    with pytest.raises(ValueError, match=error):
        business.build(doc, model)


def test_cannot_claim_business_approval_or_silently_duplicate_a_definition(base):
    model, doc = base
    doc["definitions"]["observed-total"]["review_status"] = "confirmed"
    with pytest.raises(ValueError, match="allowed keys"):
        business.build(doc, model)
    del doc["definitions"]["observed-total"]["review_status"]
    doc["definitions"]["again"] = copy.deepcopy(doc["definitions"]["observed-total"])
    doc["definitions"]["again"]["concept"] = " SOURCE TOTAL "
    with pytest.raises(ValueError, match="duplicate concept"):
        business.build(doc, model)


def test_renaming_display_and_author_key_keeps_id_but_edits_require_new_version(base):
    model, doc = base
    first = business.build(doc, model)
    saved = business.registry(first, {})
    previous_id = first["business"]["views"]["questions"]["definitions"][0]
    item = doc["definitions"].pop("refund-question")
    doc["definitions"]["refund-policy"] = item
    for view in doc["views"].values():
        view["definitions"] = [
            "refund-policy" if v == "refund-question" else v for v in view["definitions"]
        ]
    assert (
        business.build(doc, model)["business"]["views"]["questions"]["definitions"][0]
        == previous_id
    )
    item["label"] = "Refund policy"
    second = business.build(doc, model)
    with pytest.raises(ValueError, match="new version"):
        business.registry(second, saved)
    item["version"] = 2
    second = business.build(doc, model)
    assert business.registry(second, saved)["definitions"][previous_id]["version"] == 2


def test_document_evidence_quotes_and_digest_are_checked(base):
    model, doc = base
    supplied = "Invoices are checked every Friday."
    doc["documents"] = {
        "instructions": {
            "uri": "https://example.org/instructions",
            "text": supplied,
            "sha256": hashlib.sha256(supplied.encode()).hexdigest(),
        }
    }
    item = doc["definitions"]["observed-total"]
    item["contributor"] = "business_user"
    item["evidence"] = [{"kind": "document", "ref": "instructions", "quote": "every Friday"}]
    compiled = business.build(doc, model)["business"]
    for view in compiled["views"].values():
        for edge in view["edges"]:
            definition = compiled["definitions"][edge["to"]]
            for key in ("origin", "contributor", "review_status"):
                assert edge[key] == definition[key]
    assert {n["contributor"] for n in compiled["definitions"].values()} == {
        "business_user", "model"
    }
    item["evidence"][0]["quote"] = "every Monday"
    with pytest.raises(ValueError, match="quote is absent"):
        business.build(doc, model)
    item["evidence"][0]["quote"] = "every Friday"
    doc["documents"]["instructions"]["text"] += " edited"
    with pytest.raises(ValueError, match="SHA-256"):
        business.build(doc, model)


def test_missing_contributor_and_obsolete_contract_cannot_skip_enforcement(base):
    model, doc = base
    del doc["definitions"]["observed-total"]["contributor"]
    with pytest.raises(ValueError, match=r"requires.*contributor"):
        business.build(doc, model)
    doc["format"] = "sudograph-business-overlay/v1"
    with pytest.raises(ValueError, match="use format"):
        business.build(doc, model)


def test_native_renderer_cannot_skip_origin_enforcement_or_change_source_contract(base):
    model, doc = base
    overlay = business.build(doc, model)
    first = next(iter(overlay["business"]["definitions"].values()))
    first["origin"] = "inferred"
    with pytest.raises(ValueError, match=r"rebuild through compiler.business"):
        app.render(overlay)
    overlay = business.build(doc, model)
    overlay["projection"]["mode"] = "source_projection"
    with pytest.raises(ValueError, match="phase-one export"):
        app.render(overlay)


def test_cli_requires_pinned_baseline_and_registry_version_before_writing(base, tmp_path):
    from tools.check_baselines import FORMAT, coverage, digest  # noqa: PLC0415

    model, doc = base
    html = tmp_path / "source.html"
    html.write_text(app.render(model), encoding="utf8")
    manifest = {
        "format": FORMAT,
        "artifact": "source.html",
        "coverage": coverage(model["source_schema"]),
        "projection_generated_at": model["projection"]["generated_at"],
        "files": [{"path": "source.html", "bytes": html.stat().st_size, "sha256": digest(html)}],
    }
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(manifest), encoding="utf8")
    doc["baseline"]["sha256"] = digest(baseline)
    config = tmp_path / "business.yaml"
    config.write_text(yaml.safe_dump(doc), encoding="utf8")
    output = tmp_path / "business.html"
    assert business.main([str(config), "--app", str(output), "--lang", "en"]) == 0
    before = output.read_bytes()
    assert business.main([str(config), "--check-app", str(output), "--lang", "en"]) == 0
    assert business.main([str(config), "--check-app", str(output), "--lang", "zh"]) == 2
    doc["definitions"]["refund-question"]["statement"] = "Changed without a version increment."
    config.write_text(yaml.safe_dump(doc), encoding="utf8")
    assert business.main([str(config)]) == 2
    assert business.main([str(config), "--app", str(output)]) == 2
    assert output.read_bytes() == before
    doc["baseline"]["sha256"] = "wrong"
    config.write_text(yaml.safe_dump(doc), encoding="utf8")
    assert business.main([str(config)]) == 2


def test_rule_requires_named_subject_and_metric_requires_scope_and_source_grain(base):
    model, doc = base
    field = next(n for n in business.source_nodes(model["source_schema"]).values()
                 if n["kind"] == "schema_field")
    metric = {
        "concept": "ticket total", "category": "metric", "label": "Total tickets",
        "statement": "Sum included ticket amounts.", "origin": "inferred", "contributor": "model",
        "version": 1, "targets": [field["id"]], "grain": [field["id"]], "scope": "All tickets",
        "role": "business",
        "purpose": {"stakeholder": "Support manager", "decision": "Review ticket spend."},
    }
    rule = doc["definitions"]["refund-question"]
    rule["category"] = "rule"
    del rule["purpose"]
    with pytest.raises(ValueError, match="named business"):
        business.build(doc, model)
    doc["definitions"]["ticket-total"] = metric
    rule["applies_to"] = ["ticket-total"]
    compiled = business.build(doc, model)["business"]
    question_view = compiled["views"]["questions"]
    assert len(question_view["definitions"]) == 2
    edge = next(e for e in question_view["edges"] if e["rel"] == "business_applies_to")
    assert compiled["definitions"][edge["from"]]["category"] == "rule"
    assert compiled["definitions"][edge["to"]]["category"] == "metric"
    metric["grain"] = []
    with pytest.raises(ValueError, match="grain"):
        business.build(doc, model)
    metric["grain"] = [field["id"]]
    del metric["scope"]
    with pytest.raises(ValueError, match="scope"):
        business.build(doc, model)


def test_missing_categories_unknown_purposes_and_cycles_are_refused(base):
    model, doc = base
    item = doc["definitions"]["refund-question"]
    del item["category"]
    with pytest.raises(ValueError, match="category"):
        business.build(doc, model)
    item["category"] = "issue"
    del item["purpose"]
    item["applies_to"] = ["invented-definition"]
    with pytest.raises(ValueError, match="canonical definitions"):
        business.build(doc, model)
    item["applies_to"] = ["observed-total"]
    doc["definitions"]["observed-total"]["applies_to"] = ["refund-question"]
    with pytest.raises(
        ValueError, match=r"cycle: observed-total -> refund-question -> observed-total"
    ):
        business.build(doc, model)


def test_evidence_and_arithmetic_notes_cannot_be_business_view_nodes(base):
    model, doc = base
    source = doc["definitions"]["observed-total"]
    source["role"] = "source_evidence"
    source.pop("purpose")
    source["applies_to"] = ["refund-question"]
    with pytest.raises(ValueError, match="belong in details"):
        business.build(doc, model)
    doc["views"]["meaning"]["definitions"] = ["refund-question"]
    first = business.build(doc, model)
    view = first["business"]["views"]["meaning"]
    assert len(view["definitions"]) == len(view["supporting"]) == 1
    source_id = view["supporting"][0]
    assert source_id not in view["definitions"]
    assert not any(source_id in {e["from"], e["to"]} for e in view["edges"])
    previous = business.registry(first, {})
    source["role"] = "implementation_note"
    source["version"] += 1
    second = business.build(doc, model)
    assert second["business"]["views"]["meaning"]["supporting"] == [source_id]
    business.registry(second, previous)
    del source["applies_to"]
    with pytest.raises(ValueError, match="attach supporting"):
        business.build(doc, model)


def test_business_purpose_and_question_subject_cannot_be_omitted(base):
    model, doc = base
    item = doc["definitions"]["refund-question"]
    purpose = item.pop("purpose")
    with pytest.raises(ValueError, match=r"purpose.*stakeholder"):
        business.build(doc, model)
    item["purpose"] = {**purpose, "decision": " "}
    with pytest.raises(ValueError, match=r"decision.*non-empty"):
        business.build(doc, model)
    item.pop("purpose")
    item["category"] = "issue"
    with pytest.raises(ValueError, match="named business"):
        business.build(doc, model)


def test_old_contract_and_rendered_role_tampering_cannot_bypass_business_boundaries(base):
    model, doc = base
    overlay = business.build(doc, model)
    next(iter(overlay["business"]["definitions"].values()))["role"] = "source_evidence"
    with pytest.raises(ValueError, match=r"rebuild through compiler.business"):
        app.render(overlay)
    doc["format"] = "sudograph-business-overlay/v3"
    with pytest.raises(ValueError, match="use format"):
        business.build(doc, model)


def source_question(model):
    obj = next(o for o in model["source_schema"]["sources"][0]["objects"] if o["name"] == "Tickets")
    return {
        "concept": "missing ticket amounts", "category": "issue", "role": "source_review",
        "label": "Check empty amounts", "statement": "Is a missing amount expected for a ticket?",
        "origin": "inferred", "contributor": "model", "version": 1,
        "targets": [next(f["id"] for f in obj["fields"] if f["column"] == "amount")],
        "verification": "Inspect the source NULL count and the corresponding real ticket records.",
    }


def test_phase_one_questions_work_without_business_definitions_and_preserve_source(base):
    model, doc = base
    question = source_question(model)
    doc["definitions"] = {"missing-amount": question}
    doc["views"] = {}
    overlay = business.build(doc, model)
    business.validate(overlay)
    assert overlay["views"] is model["views"] and overlay["records"] is model["records"]
    assert overlay["source_schema"] is model["source_schema"]
    review = overlay["business"]["source_review"]
    identity = review["definitions"][0]
    assert overlay["business"]["views"] == {}
    assert review["edges"][0]["from"] == question["targets"][0]
    assert review["edges"][0]["to"] == identity
    assert overlay["business"]["definitions"][identity]["review_status"] == "unreviewed"
    # Direct rendering is checked too; removing the plan from the DTO cannot
    # bypass the parser by submitting precompiled graph data.
    app.render(overlay)
    overlay["business"]["definitions"][identity].pop("verification")
    with pytest.raises(ValueError, match=r"rebuild through compiler.business"):
        app.render(overlay)


def test_source_questions_cannot_be_business_nodes_or_depend_on_business(base):
    model, doc = base
    doc["definitions"]["missing-amount"] = source_question(model)
    doc["views"]["meaning"]["definitions"].append("missing-amount")
    with pytest.raises(ValueError, match="source_review belongs in phase one"):
        business.build(doc, model)
    doc["views"]["meaning"]["definitions"].pop()
    question = doc["definitions"]["missing-amount"]
    question["applies_to"] = ["refund-question"]
    with pytest.raises(ValueError, match="phase one must not depend"):
        business.build(doc, model)
    question.pop("applies_to")
    verification = question.pop("verification")
    with pytest.raises(ValueError, match=r"verification.*non-empty"):
        business.build(doc, model)
    question["verification"] = verification
    question["category"] = "rule"
    with pytest.raises(ValueError, match="not a business policy"):
        business.build(doc, model)


def test_moving_existing_note_to_phase_one_keeps_identity_and_requires_new_version(base):
    model, doc = base
    note = source_question(model)
    note.update(role="implementation_note", applies_to=["refund-question"])
    plan = note.pop("verification")
    doc["definitions"]["missing-amount"] = note
    first = business.build(doc, model)
    saved = business.registry(first, {})
    old_id = first["business"]["views"]["questions"]["supporting"][0]
    note.update(role="source_review", verification=plan)
    note.pop("applies_to")
    second = business.build(doc, model)
    assert second["business"]["source_review"]["definitions"] == [old_id]
    assert second["business"]["views"]["questions"]["supporting"] == []
    with pytest.raises(ValueError, match="content changed without a new version"):
        business.registry(second, saved)
    note["version"] += 1
    business.registry(business.build(doc, model), saved)


def test_top_down_concept_late_binding_preserves_identity_views_comments_and_versions(base):
    from compiler.context import Reader  # noqa: PLC0415

    model, doc = base
    doc.pop("views")
    item = doc["definitions"]["refund-question"]
    targets = item["targets"]
    item["targets"] = []
    first = business.build(doc, model)
    previous = business.registry(first, {})
    identity = next(i for i, n in first["business"]["definitions"].items()
                    if n["key"] == "refund-question")
    view = next(k for k, v in first["business"]["views"].items() if v["subject"] == identity)
    assert first["business"]["definitions"][identity]["binding_status"] == "unbound"
    assert Reader(first).read(identity)["definition"]["binding_status"] == "unbound"
    app.render(first)
    for revision, binding in [(2, targets), (3, []), (4, [next(
        n["id"] for n in business.source_nodes(model["source_schema"]).values()
        if n["kind"] == "schema_field")])]:
        item["targets"] = binding
        with pytest.raises(ValueError, match="new version"):
            business.registry(business.build(doc, model, previous=previous), previous)
        item["version"] = revision
        changed = business.build(doc, model, previous=previous)
        previous = business.registry(changed, previous)
        assert changed["business"]["views"][view]["subject"] == identity
        assert changed["business"]["definitions"][identity]["targets"] == binding
        assert changed["source_schema"] is model["source_schema"]


def test_unbound_metrics_do_not_invent_grain_and_invalid_bindings_still_fail(base):
    model, doc = base
    doc.pop("views")
    item = doc["definitions"]["refund-question"]
    item.update(category="metric", targets=[], scope="Annual shipped orders")
    compiled = business.build(doc, model)
    metric = next(n for n in compiled["business"]["definitions"].values()
                  if n["category"] == "metric")
    assert metric["grain"] == [] and metric["binding_status"] == "unbound"
    app.render(compiled)
    item["grain"] = ["invented-field"]
    with pytest.raises(ValueError, match="grain"):
        business.build(doc, model)
    item["targets"] = ["invented-field"]
    with pytest.raises(ValueError, match="source ID"):
        business.build(doc, model)
    doc["definitions"] = {"data-question": source_question(model)}
    doc["definitions"]["data-question"]["targets"] = []
    with pytest.raises(ValueError, match="targets"):
        business.build(doc, model)


def test_source_free_concepts_are_checked_without_inventing_source_objects(base):
    model, doc = base
    doc.pop("views")
    item = doc["definitions"]["refund-question"]
    item["targets"] = []
    doc["definitions"] = {"refund-question": item}
    schema = {**model["source_schema"], "sources": [], "schema_complete": False,
              "record_complete": False}
    checked = business.compile_document(doc, schema)
    assert len(checked["definitions"]) == 1
    assert all(not v["targets"] and not v["edges"] for v in checked["views"].values())


def test_legacy_migration_preserves_existing_ids_and_retargeting_cannot_bypass_registry(base):
    model, doc = base
    doc["format"] = business.BOUND_FORMAT
    old = business.build(doc, model)
    legacy = business.registry(old, {})
    # Reproduce the exact v1 ledger used before this upgrade.
    legacy = {"format": business.OLD_REGISTRY, "definitions": {
        i: {k: v for k, v in entry.items() if k != "identity"}
        for i, entry in legacy["definitions"].items()
    }}
    upgraded = business.registry(old, legacy)
    doc["format"] = business.FORMAT
    with pytest.raises(ValueError, match="upgrade the registry"):
        business.build(doc, model, previous=legacy)
    current = business.build(doc, model, previous=upgraded)
    assert set(current["business"]["definitions"]) == set(old["business"]["definitions"])
    business.registry(current, upgraded)
    business.validate(current)
    item = doc["definitions"]["refund-question"]
    item.update(targets=[], version=2)
    bound = business.build(doc, model, previous=upgraded)
    assert set(bound["business"]["definitions"]) == set(old["business"]["definitions"])
    business.registry(bound, upgraded)
    # Forgetting the canonical ledger is refused, not interpreted as a new object.
    with pytest.raises(ValueError, match="already has an identity"):
        business.registry(business.build(doc, model), upgraded)


def test_duplicate_concepts_cannot_be_recreated_for_different_fields_or_views(base):
    model, doc = base
    clone = copy.deepcopy(doc["definitions"]["refund-question"])
    clone.update(targets=[], label="A renamed duplicate")
    doc["definitions"]["duplicate"] = clone
    with pytest.raises(ValueError, match="duplicate concept"):
        business.build(doc, model)


def test_retired_reservations_and_rendered_identity_proofs_remain_enforced(base):
    model, doc = base
    doc.pop("views")
    initial = business.build(doc, model)
    previous = business.registry(initial, {})
    retired = doc["definitions"].pop("refund-question")
    without = business.build(doc, model, previous=previous)
    previous = business.registry(without, previous)
    assert len(previous["definitions"]) == 2
    retired.update(targets=[], version=2)
    doc["definitions"]["returned"] = retired
    restored = business.build(doc, model, previous=previous)
    assert set(restored["business"]["definitions"]) == set(initial["business"]["definitions"])
    business.registry(restored, previous)
    anchor = next(iter(restored["business"]["identities"].values()))
    anchor["concept"] = "a different concept"
    with pytest.raises(ValueError, match="compiler-owned reservation"):
        app.render(restored)
