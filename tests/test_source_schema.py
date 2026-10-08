"""Source addresses survive author renaming; keyless and binary facts remain intact."""

import base64
import copy
import gzip
import hashlib
import json
import sqlite3
import struct

import pytest
import yaml

from compiler import app, gateway, project, source_schema, spec


def decoded(model, snapshot):
    pool = json.loads(gzip.decompress(base64.b64decode(model["dictionaries"][snapshot["source"]])))
    result = []
    for page in snapshot["chunks"]:
        columns = []
        for identity in page:
            segment = model["segments"][identity]
            data = gzip.decompress(base64.b64decode(segment["data"]))
            count = len(data) // 4
            if segment["codec"] != "u32le":
                data = bytes(data[byte * count + row] for row in range(count) for byte in range(4))
            codes = list(struct.unpack("<" + "I" * count, data))
            if segment["codec"] == "delta-byteplane":
                for row in range(1, count):
                    codes[row] = (codes[row] + codes[row - 1]) & 0xFFFFFFFF
            columns.append([pool[code] for code in codes])
        result.extend(map(list, zip(*columns, strict=True)))
    return result


@pytest.fixture
def raw(tmp_path):
    db = tmp_path / "unrelated.db"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
          CREATE TABLE Teams(id INTEGER PRIMARY KEY, name TEXT, picture BLOB);
          CREATE TABLE Events(team INTEGER REFERENCES Teams(id), seq INTEGER, amount REAL,
                              PRIMARY KEY(team,seq));
          INSERT INTO Teams VALUES(1,'One',X'00FF3C2F7363726970743E'),(2,'Two',NULL);
          INSERT INTO Events VALUES(1,1,NULL),(1,2,7),(2,1,7);
          CREATE VIEW NoIdentity AS SELECT amount FROM Events;
          CREATE VIEW ViaCTE AS WITH Temp AS (SELECT name FROM Teams) SELECT * FROM Temp;
        """)
    path = tmp_path / "projection.yaml"
    doc = project.draft("sqlite:///" + db.as_posix())
    path.write_text(yaml.safe_dump(doc), encoding="utf8")
    return db, path, doc


def test_all_source_fields_views_duplicate_rows_binary_and_null_preserved(raw):
    db, path, _ = raw
    before = hashlib.sha256(db.read_bytes()).digest()
    b = app.bundle(spec.load(str(path)), records=True)
    model = b["source_schema"]
    objects = {o["name"]: o for o in model["sources"][0]["objects"]}
    assert set(objects) == {"Teams", "Events", "NoIdentity", "ViaCTE"}
    assert [f["column"] for f in objects["Teams"]["fields"]] == ["id", "name", "picture"]
    assert objects["ViaCTE"]["dependencies"] == ["Teams"]
    assert objects["NoIdentity"]["dependencies"] == ["Events"]
    snap = model["snapshots"][objects["NoIdentity"]["id"]]
    assert snap["identity"] == "snapshot_position" and snap["keys"] == []
    assert decoded(model, snap) == [
        [None],
        [7.0],
        [7.0],
    ]
    teams = model["snapshots"][objects["Teams"]["id"]]
    rows = decoded(model, teams)
    assert base64.b64decode(rows[0][2]["$binary"]) == bytes.fromhex("00FF3C2F7363726970743E")
    assert rows[1][2] is None
    assert model["schema_complete"] and model["record_complete"]
    assert hashlib.sha256(db.read_bytes()).digest() == before


def test_lossless_wire_values_do_not_merge_types_or_round_large_integers(raw):
    db, path, _ = raw
    values = [1, 1.0, 2**63 - 1, -(2**63), -0.0, float("inf"), float("-inf")]
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE WireValues(value)")
        conn.executemany("INSERT INTO WireValues VALUES(?)", [(v,) for v in values])
    path.write_text(yaml.safe_dump(project.draft("sqlite:///" + db.as_posix())), encoding="utf8")
    model = source_schema.build(spec.load(str(path)), records=True)
    obj = next(o for o in model["sources"][0]["objects"] if o["name"] == "WireValues")
    rows = decoded(model, model["snapshots"][obj["id"]])
    assert type(rows[0][0]) is int and type(rows[1][0]) is float
    assert rows[2:4] == [[{"$integer": str(values[2])}], [{"$integer": str(values[3])}]]
    assert struct.pack("<d", rows[4][0]) == struct.pack("<d", -0.0)
    assert rows[5:] == [[{"$float": "inf"}], [{"$float": "-inf"}]]


def test_native_render_refuses_missing_compressed_source_segment(raw):
    _, path, _ = raw
    b = app.bundle(spec.load(str(path)), records=True)
    b["source_schema"]["segments"].pop(next(iter(b["source_schema"]["segments"])))
    with pytest.raises(ValueError, match="segments are incomplete"):
        app.render(b)


def test_generated_source_column_is_preserved_as_source_fact(raw):
    db, path, _ = raw
    with sqlite3.connect(db) as conn:
        conn.executescript("""
          CREATE TABLE Computed(id INTEGER PRIMARY KEY, amount INTEGER,
                                total INTEGER GENERATED ALWAYS AS(amount * 2) VIRTUAL);
          INSERT INTO Computed(id,amount) VALUES(1,3);
        """)
    path.write_text(yaml.safe_dump(project.draft("sqlite:///" + db.as_posix())), encoding="utf8")
    model = source_schema.build(spec.load(str(path)), records=True)
    obj = next(o for o in model["sources"][0]["objects"] if o["name"] == "Computed")
    assert [f["column"] for f in obj["fields"]] == ["id", "amount", "total"]
    assert decoded(model, model["snapshots"][obj["id"]]) == [[1, 3, 6]]


def test_filtered_alias_does_not_reuse_unfiltered_record_pages(raw):
    _, path, doc = raw
    doc["types"]["SelectedTeam"] = copy.deepcopy(doc["types"]["Teams"])
    doc["types"]["SelectedTeam"]["backing"]["where"] = "id = 1"
    path.write_text(yaml.safe_dump(doc), encoding="utf8")
    b = app.bundle(spec.load(str(path)), records=True)
    r = b["records"]["SelectedTeam"]
    assert "source_object" not in r
    rows = json.loads(gzip.decompress(base64.b64decode(r["chunks"][0])))
    assert len(rows) == 1 and rows[0][r["columns"].index("id")] == 1


def test_source_ids_ignore_ontology_aliases_labels_data_and_language(raw):
    db, path, doc = raw
    first = source_schema.build(spec.load(str(path)))
    doc["types"]["Renamed"] = doc["types"].pop("Teams")
    doc["types"]["Renamed"]["label"] = "Completely different label"
    doc["types"]["Renamed"]["props"]["caption"] = doc["types"]["Renamed"]["props"].pop("name")
    doc["types"]["Renamed"]["props"]["caption"]["column"] = "name"
    doc["types"]["Renamed"]["display"] = "caption"
    doc["types"]["Events"]["props"]["team"]["to"] = "Renamed"
    doc["raw"]["DATA"] = doc["raw"].pop("SOURCE")
    for definition in doc["types"].values():
        definition["backing"]["from"] = "DATA"
    path.write_text(yaml.safe_dump(doc), encoding="utf8")
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE Teams SET name='Changed data'")
    second = source_schema.build(spec.load(str(path)))

    def identities(model):
        return [(o["id"], [f["id"] for f in o["fields"]]) for o in model["sources"][0]["objects"]]

    assert identities(first) == identities(second)
    b = app.bundle(spec.load(str(path)))
    group = next(g for g in b["views"]["|"]["groups"] if g["type"] == "Renamed")
    field = next(
        f
        for o in second["sources"][0]["objects"]
        if o["name"] == "Teams"
        for f in o["fields"]
        if f["column"] == "name"
    )
    assert group["field_ids"]["caption"] == field["id"]


def test_native_render_refuses_missing_or_replaced_source_identity(raw):
    _, path, _ = raw
    b = app.bundle(spec.load(str(path)))
    changed = copy.deepcopy(b)
    changed["source_schema"]["sources"][0]["objects"][0]["fields"][0]["id"] = "author-picked-id"
    with pytest.raises(ValueError, match="source field identity"):
        app.render(changed)
    omitted = copy.deepcopy(b)
    omitted["source_schema"]["sources"][0]["objects"][0]["fields"].pop()
    with pytest.raises(ValueError, match="field inventory is incomplete"):
        app.render(omitted)
    changed.pop("source_schema")
    with pytest.raises(ValueError, match="requires a compiler-generated"):
        app.render(changed)


def test_authorised_graph_does_not_expand_into_whole_source_catalogue(raw):
    _, path, doc = raw
    doc["mode"] = "business"
    doc["raw"]["SOURCE"].pop("coverage")
    doc["raw"]["SOURCE"].pop("exclude")
    doc["types"].pop("Events")
    path.write_text(yaml.safe_dump(doc), encoding="utf8")

    class Authority:
        def require(self, *args):
            return "reader"

    g = gateway.Gateway({"limited": gateway.View(str(path))}, Authority())
    b = g.execute("credential", "limited", "graph")
    assert not b.get("source_schema")
    encoded = json.dumps(b)
    assert "NoIdentity" not in encoded and "picture" not in encoded and "ViaCTE" not in encoded
    group = next(g for g in b["views"]["|"]["groups"] if g["type"] == "Teams")
    assert set(group["field_ids"]) == {"id", "name"}
