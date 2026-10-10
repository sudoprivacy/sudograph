"""Portable packing preserves native bytes, source facts and compiler refusals."""

import copy
import json
import sqlite3

import pytest
import yaml

from compiler import app, html_export, project, spec
from tools import check_baselines


def test_packing_round_trips_unicode_script_text_and_all_native_bytes():
    native = '<!doctype html>\r\n<p>Source: 客户 & €</p><script>const BUNDLE = {};</script>\r\n'
    packed = html_export.pack(native, language="en")
    assert html_export.unpack(packed) == native
    assert html_export.unpack(native) == native
    with pytest.raises(ValueError, match="already packed"):
        html_export.pack(packed, language="en")


def test_size_hash_and_format_changes_are_refused():
    packed = html_export.pack("<p>Native source</p>", language="en")
    payload = json.JSONDecoder().raw_decode(packed.split(html_export.MARKER, 1)[1])[0]
    for key, value in (("bytes", 1), ("sha256", "wrong"), ("format", "unknown")):
        altered = {**payload, key: value}
        corrupt = packed.replace(json.dumps(payload, separators=(",", ":")), json.dumps(altered))
        with pytest.raises(ValueError, match=r"unsupported|size/hash differs"):
            html_export.unpack(corrupt)


def test_source_entry_point_exports_english_packed_records_without_loss(tmp_path):
    db = tmp_path / "facts.db"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE Facts(id INTEGER PRIMARY KEY, note TEXT, picture BLOB);
            INSERT INTO Facts VALUES (1,'</script>客户',X'00FF'),(2,NULL,NULL);
            CREATE VIEW Keyless AS SELECT note FROM Facts;
        """)
    config, output = tmp_path / "source.yaml", tmp_path / "source.html"
    assert project.main([
        "sqlite:///" + db.as_posix(), str(config), "--name", "Source facts",
        "--app", str(output), "--records", "--lang", "en", "--pack-html",
    ]) == 0
    exported = check_baselines.bundle(output)
    assert exported["ui"]["language"] == "en"
    assert exported["projection"]["mode"] == "source_projection"
    report = check_baselines.audit_sqlite(exported["source_schema"], db)
    assert report["objects"] == 2 and report["result_rows"] == 4
    assert report["binary_values"] == 1
    original = app.bundle(spec.load(str(config)), records=True)
    assert exported["source_schema"] == original["source_schema"]
    assert (
        html_export.unpack(output.read_text(encoding="utf8"))
        == app.render(exported, language="en")
    )
    missing = copy.deepcopy(exported)
    missing["source_schema"]["segments"].pop(next(iter(missing["source_schema"]["segments"])))
    with pytest.raises(ValueError, match="segments are incomplete"):
        app.render(missing, language="en", packed=True)


def test_packing_requires_an_export_target_before_writing_config(tmp_path):
    config = tmp_path / "should-not-exist.yaml"
    with pytest.raises(SystemExit) as exc:
        project.main(["sqlite:///missing.db", str(config), "--pack-html"])
    assert exc.value.code == 2 and not config.exists()


def test_baseline_refuses_false_language_declaration(tmp_path):
    config = tmp_path / "empty.yaml"
    config.write_text(yaml.safe_dump({"ontology": "Example", "types": {}}), encoding="utf8")
    exported = app.bundle(spec.load(str(config)))
    # Check language before source completeness, so a false public-language
    # declaration cannot silently fall through to a different display locale.
    artifact = tmp_path / "index.html"
    artifact.write_text(app.render(exported, language="en", packed=True), encoding="utf8")
    manifest = {
        "format": check_baselines.FORMAT, "artifact": "index.html",
        "renderer": {"language": "zh"},
        "files": [{"path": "index.html", "bytes": artifact.stat().st_size,
                   "sha256": check_baselines.digest(artifact)}],
    }
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(manifest), encoding="utf8")
    with pytest.raises(ValueError, match="export language differs"):
        check_baselines.check(path)
