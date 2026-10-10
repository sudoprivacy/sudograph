"""Frozen evidence fails on drift, loss and false coverage, on unrelated data."""

import base64
import copy
import gzip
import json
import sqlite3

import pytest
import yaml

from compiler import app, project, spec
from tools import check_baselines as baseline


@pytest.fixture
def frozen(tmp_path):
    db = tmp_path / "arbitrary.db"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE Facts(id INTEGER PRIMARY KEY, value, photo BLOB);
            INSERT INTO Facts VALUES(1, 9223372036854775807, X'00FF'), (2, NULL, NULL);
            CREATE TABLE Events(id INTEGER PRIMARY KEY, amount REAL);
            INSERT INTO Events VALUES(1, 7), (2, 7), (3, -0.0);
            CREATE VIEW Repeated AS SELECT amount FROM Events;
            CREATE VIEW Empty AS SELECT id FROM Events WHERE 0;
        """)
    config = tmp_path / "source.yaml"
    config.write_text(yaml.safe_dump(project.draft("sqlite:///" + db.as_posix())), encoding="utf-8")
    b = app.bundle(spec.load(str(config)), records=True)
    artifact = tmp_path / "index.html"
    # The small HTML fixture exercises bundle parsing, not vendor libraries.
    artifact.write_text("<script>const BUNDLE = " + json.dumps(b) + ";</script>", encoding="utf-8")
    manifest = {
        "format": baseline.FORMAT, "artifact": "index.html",
        "projection_generated_at": b["projection"]["generated_at"],
        "source": {"sha256": baseline.digest(db)},
        "coverage": baseline.coverage(b["source_schema"]),
        "files": [{"path": "index.html", "sha256": baseline.digest(artifact),
                   "bytes": artifact.stat().st_size}],
    }
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return db, b, artifact, path, manifest


def test_all_rows_types_binary_null_and_duplicate_keyless_rows_audited(frozen):
    db, _, _, path, _ = frozen
    before = baseline.digest(db)
    report = baseline.check(path, source=db)
    assert report["coverage"] == {
        "objects": 4, "tables": 2, "views": 2, "fields": 7,
        "table_rows": 5, "result_rows": 8, "values": 15,
    }
    assert report["source_audit"]["binary_values"] == 1
    assert baseline.digest(db) == before


def test_source_wide_inventory_cannot_be_faked_by_completeness_flag(frozen):
    db, b, _, _, _ = frozen
    model = copy.deepcopy(b["source_schema"])
    model["sources"][0]["objects"].pop()
    with pytest.raises(ValueError, match="object inventory differs"):
        baseline.audit_sqlite(model, db)


def test_decodable_but_incorrect_value_is_found_against_raw_database(frozen):
    db, b, _, _, _ = frozen
    model = copy.deepcopy(b["source_schema"])
    sid = model["sources"][0]["id"]
    pool = json.loads(gzip.decompress(base64.b64decode(model["dictionaries"][sid])))
    for i, value in enumerate(pool):
        if value == 7.0:
            pool[i] = 9.0
    model["dictionaries"][sid] = base64.b64encode(gzip.compress(json.dumps(pool).encode())).decode()
    with pytest.raises(ValueError, match="value differs"):
        baseline.audit_sqlite(model, db)


def test_missing_segment_is_refused_before_audit(frozen):
    db, b, _, _, _ = frozen
    model = copy.deepcopy(b["source_schema"])
    model["segments"].pop(next(iter(model["segments"])))
    with pytest.raises(ValueError, match="segments are incomplete"):
        baseline.audit_sqlite(model, db)


def test_frozen_file_and_source_drift_are_refused(frozen):
    db, _, artifact, path, _ = frozen
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO Events VALUES (4, 99)")
    with pytest.raises(ValueError, match="source file hash differs"):
        baseline.check(path, source=db)
    artifact.write_bytes(artifact.read_bytes() + b" changed")
    with pytest.raises(ValueError, match="frozen file size/hash differs"):
        baseline.check(path)


def test_false_coverage_declaration_is_refused(frozen):
    _, _, _, path, manifest = frozen
    manifest["coverage"]["fields"] += 1
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="coverage declaration differs"):
        baseline.check(path)


def test_manifest_cannot_check_files_outside_its_package(frozen):
    _, _, _, path, manifest = frozen
    manifest["files"][0]["path"] = "../outside.html"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="escaping baseline file"):
        baseline.check(path)


def test_empty_baseline_scan_is_a_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(baseline, "ROOT", tmp_path)
    assert baseline.main([]) == 1
