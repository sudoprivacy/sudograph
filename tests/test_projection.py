"""Phase-one source contract on unrelated data, including NULL and invented links."""

import base64
import copy
import gzip
import hashlib
import json
import os
import sqlite3
import subprocess
import sys

import pytest
import yaml

from compiler import app, bind, browse, cli, project, spec


@pytest.fixture
def source(tmp_path):
    db = tmp_path / "source.db"
    with sqlite3.connect(db) as c:
        c.executescript("""
          CREATE TABLE Teams(id INTEGER PRIMARY KEY, name TEXT);
          CREATE TABLE Items(team INTEGER REFERENCES Teams(id), seq INTEGER,
                             amount REAL, PRIMARY KEY(team,seq));
          CREATE VIEW Summary AS SELECT COUNT(*) n FROM Items;
          INSERT INTO Teams VALUES(1,'One'),(2,'Two');
          INSERT INTO Items VALUES(1,1,NULL),(1,2,7),(2,1,11);
        """)
    return db, tmp_path / "projection.yaml"


def load_doc(source, change=None):
    db, path = source
    d = project.draft("sqlite:///" + db.as_posix())
    if change:
        change(d)
    path.write_text(yaml.safe_dump(d), encoding="utf-8")
    return spec.load(str(path))


def test_source_projection_preserves_null_composite_identity_and_read_only_source(source):
    db, _ = source
    before = hashlib.sha256(db.read_bytes()).digest()
    s = load_doc(source)
    assert s.id_props("Items") == ["team", "seq"]
    assert s.links_of("Items") == {"team": "Teams"}
    b = app.bundle(s, records=True)
    r = b["records"]["Items"]
    rows = json.loads(gzip.decompress(base64.b64decode(r["chunks"][0])))
    assert rows[0][r["columns"].index("amount")] is None
    assert b["projection"]["mode"] == "source_projection"
    assert b["coverage"][0]["complete"]
    assert next(o for o in b["coverage"][0]["objects"] if o["name"] == "Summary")["excluded"]
    assert hashlib.sha256(db.read_bytes()).digest() == before


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(instances={"Teams": [{"id": 99, "name": "invented"}]}),
        lambda d: d["types"]["Items"]["props"].update(total={"type": "number", "op": "amount * 2"}),
        lambda d: d["types"]["Items"]["props"]["amount"].update(absent="zero"),
        lambda d: d["types"]["Items"]["props"]["seq"].update(type="ref", to="Teams"),
        lambda d: d["types"]["Items"]["backing"].update(key=["seq"]),
        lambda d: d["types"]["Items"].update(id="seq"),
    ],
)
def test_projection_refuses_authored_facts_and_guessed_relationships(source, change):
    with pytest.raises(
        spec.SpecError, match=r"source_projection|primary key|carries rows inline|op hides"
    ):
        load_doc(source, change)


def test_record_export_honours_registered_source_row_scope(source):
    s = load_doc(source)
    s = copy.deepcopy(s)
    s.types["Items"]["backing"]["where"] = "team = 1"
    r = browse.snapshot(s)["Items"]
    rows = json.loads(gzip.decompress(base64.b64decode(r["chunks"][0])))
    assert len(rows) == 2
    assert {row[r["columns"].index("team")] for row in rows} == {1}


def test_failed_renderer_keeps_previous_deliverable(source, monkeypatch, capsys):
    load_doc(source)
    _, path = source
    target = path.with_suffix(".html")
    target.write_text("previous verified graph", encoding="utf-8")

    def missing(*args, **kwargs):
        raise ValueError("UI translation missing: [untranslated label]")

    monkeypatch.setattr(app, "render", missing)
    assert cli.main([str(path), "--app", str(target)]) == 2
    assert "UI translation missing" in capsys.readouterr().err
    assert target.read_text(encoding="utf-8") == "previous verified graph"


def test_native_template_is_reproducible_across_python_hash_seeds():
    command = (
        "from compiler.app import render; import hashlib; "
        "print(hashlib.sha256(render({}).encode()).hexdigest())"
    )
    hashes = [
        subprocess.check_output(
            [sys.executable, "-c", command], env={**os.environ, "PYTHONHASHSEED": seed}
        )
        for seed in ("1", "2")
    ]
    assert hashes[0] == hashes[1]


def test_projection_cli_missing_source_returns_four_without_clobbering_yaml(tmp_path):
    out = tmp_path / "previous.yaml"
    out.write_text("previous valid projection", encoding="utf-8")
    assert project.main(["sqlite:///missing.db", str(out)]) == 4
    assert out.read_text(encoding="utf-8") == "previous valid projection"


def test_projection_cli_generates_from_relative_source_into_other_directory(source, monkeypatch):
    db, _ = source
    monkeypatch.chdir(db.parent)
    folder = db.parent / "delivery"
    folder.mkdir()
    out, html = folder / "projection.yaml", folder / "graph.html"
    assert project.main(["sqlite:///source.db", str(out), "--app", str(html), "--records"]) == 0
    assert spec.load(str(out)).mode == "source_projection"
    assert "source_projection" in html.read_text(encoding="utf-8")


def test_sqlite_dsn_preserves_absolute_posix_root():
    assert bind._path_of("sqlite:////tmp/source.db", ".") == os.path.normpath("/tmp/source.db")
