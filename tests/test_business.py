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
                "label": "Source total",
                "statement": "The source sums amount.",
                "origin": "provided",
                "version": 1,
                "targets": [obj["id"]],
                "evidence": [{"kind": "source_sql", "ref": obj["id"], "quote": "SUM(amount)"}],
            },
            "refund-question": {
                "concept": "refund policy",
                "label": "Refunds",
                "statement": "Should refunds reduce this amount?",
                "origin": "inferred",
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
    item["evidence"] = [{"kind": "document", "ref": "instructions", "quote": "every Friday"}]
    business.build(doc, model)
    item["evidence"][0]["quote"] = "every Monday"
    with pytest.raises(ValueError, match="quote is absent"):
        business.build(doc, model)
    item["evidence"][0]["quote"] = "every Friday"
    doc["documents"]["instructions"]["text"] += " edited"
    with pytest.raises(ValueError, match="SHA-256"):
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
