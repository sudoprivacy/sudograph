"""Read live source facts without embedding rows or granting source access in YAML."""

import hashlib
import json
import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest
import yaml

from compiler import app, bind, project, spec, workspace
from compiler.model_contract import Refused
from compiler.source_records import MAX_BYTES, SourceRecords


@pytest.fixture
def live(tmp_path):
    database = tmp_path / "source #current.sqlite"
    with closing(sqlite3.connect(database)) as db, db:
        db.executescript("""
            CREATE TABLE Tickets (id INTEGER PRIMARY KEY, amount REAL, picture BLOB);
            INSERT INTO Tickets VALUES (2, 8.5, X'00FF'), (1, NULL, NULL), (3, 8.5, NULL);
            CREATE VIEW Amounts AS SELECT amount FROM Tickets;
            CREATE TABLE TextKeys (id TEXT PRIMARY KEY, description TEXT);
            INSERT INTO TextKeys VALUES ('one', 'First');
            CREATE TABLE "Quoted;\"\"Object" ("key\"\"name" INTEGER PRIMARY KEY, value TEXT);
            INSERT INTO "Quoted;\"\"Object" VALUES (1, 'literal');
        """)
    dsn = "sqlite:///" + database.as_posix()
    path = tmp_path / "source.yaml"
    path.write_text(yaml.safe_dump(project.draft(dsn)), encoding="utf8")
    model = app.bundle(spec.load(str(path)), records=False)
    source = model["source_schema"]["sources"][0]
    bindings = {source["id"]: dsn}
    objects = {obj["name"]: obj["id"] for obj in source["objects"]}
    return database, model, bindings, objects


def test_pages_keep_row_correspondence_keys_binary_null_and_duplicate_view_results(live):
    database, model, bindings, objects = live
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    reader = SourceRecords(model, bindings)
    first = reader.page(objects["Tickets"], limit=2)
    assert first["columns"] == ["id", "amount", "picture"]
    assert first["rows"][0] == [1, None, None]
    assert first["rows"][1][:2] == [2, 8.5]
    assert first["rows"][1][2]["$binary"] == "AP8="
    assert first["keys"] == ["id"]
    assert first["identity"] == "declared_key"
    assert first["next_offset"] == 2
    assert reader.page(objects["Tickets"], offset=2)["rows"] == [[3, 8.5, None]]
    view = reader.page(objects["Amounts"])
    assert view["rows"] == [[None], [8.5], [8.5]]
    assert view["keys"] == []
    assert view["identity"] == "request_position"
    assert view["data_kind"] == "live_source_page"
    assert reader.page(objects['Quoted;"Object'])["rows"] == [[1, "literal"]]
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    assert not model["records"] and not model["source_schema"]["snapshots"]


def test_each_page_observes_live_data_without_rewriting_the_registered_catalogue(live):
    database, model, bindings, objects = live
    reader = SourceRecords(model, bindings)
    first = reader.page(objects["Tickets"])
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("INSERT INTO Tickets VALUES (4, 25, NULL)")
    second = reader.page(objects["Tickets"])
    assert first["total"] == 3 and second["total"] == 4
    assert second["catalog_total"] == 3
    assert first["observation"] != second["observation"]
    assert first["source_digest"] == second["source_digest"]
    assert second["rows"][-1] == [4, 25, None]


@pytest.mark.parametrize(
    "mutation",
    [
        "ALTER TABLE Tickets ADD COLUMN added TEXT",
        "DROP TABLE Tickets",
        "DROP VIEW Amounts; CREATE VIEW Amounts AS SELECT id AS amount FROM Tickets",
    ],
)
def test_schema_drift_is_refused_instead_of_reading_a_different_meaning(live, mutation):
    database, model, bindings, objects = live
    with closing(sqlite3.connect(database)) as db, db:
        db.executescript(mutation)
    identity = objects["Amounts" if "VIEW" in mutation else "Tickets"]
    with pytest.raises(Refused) as error:
        SourceRecords(model, bindings).page(identity)
    assert error.value.code == "SOURCE_SCHEMA_CHANGED"


def test_source_identity_null_keys_and_oversized_records_fail_explicitly(live, tmp_path):
    database, model, bindings, objects = live
    with pytest.raises(ValueError, match="source identity"):
        SourceRecords(
            model, {next(iter(bindings)): "sqlite:///" + (tmp_path / "other.db").as_posix()}
        )
    reader = SourceRecords(model, bindings)
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("INSERT INTO TextKeys VALUES (NULL, 'Invalid key')")
    with pytest.raises(Refused) as error:
        reader.page(objects["TextKeys"])
    assert error.value.code == "SOURCE_IDENTITY"
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE Tickets SET picture = zeroblob(?) WHERE id = 2", (MAX_BYTES + 1,))
    with pytest.raises(Refused) as error:
        reader.page(objects["Tickets"])
    assert error.value.code == "RECORD_PAGE_TOO_LARGE"


def test_bounded_ranges_and_registered_binding_are_enforced(live):
    _database, model, bindings, objects = live
    reader = SourceRecords(model, bindings)
    for params in ({"limit": 101}, {"offset": -1}, {"offset": True}, {"limit": "1"}):
        with pytest.raises(Refused) as error:
            reader.page(objects["Tickets"], **params)
        assert error.value.code == "READ_CONTRACT"
    with pytest.raises(Refused, match="not registered"):
        reader.page("SELECT * FROM Tickets")
    with pytest.raises(Refused, match="not registered"):
        SourceRecords(model, {}).page(objects["Tickets"])
    assert reader.page(objects["Tickets"], offset=100)["rows"] == []
    assert reader.page(objects["Tickets"], offset=10**80)["rows"] == []


def test_page_byte_budget_never_silently_truncates_values(live):
    database, model, bindings, objects = live
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE Tickets SET picture = zeroblob(?) WHERE id IN (1,2)", (MAX_BYTES // 2,))
    reader = SourceRecords(model, bindings)
    with pytest.raises(Refused) as error:
        reader.page(objects["Tickets"], limit=2)
    assert error.value.code == "RECORD_PAGE_TOO_LARGE"
    one = reader.page(objects["Tickets"], limit=1)
    assert one["rows"][0][2]["size"] == MAX_BYTES // 2


def test_unavailable_source_does_not_expose_operator_path(live, monkeypatch):
    database, model, bindings, objects = live

    def unavailable(*_args, **_kwargs):
        raise bind.SourceUnavailable(f"no database at {database}")

    monkeypatch.setattr(bind, "connect", unavailable)
    with pytest.raises(Refused) as error:
        SourceRecords(model, bindings).page(objects["Tickets"])
    assert error.value.code == "SOURCE_UNAVAILABLE"
    assert str(database) not in error.value.reason


def test_workspace_worker_reads_registered_live_rows_without_exposing_dsn(live, tmp_path):
    database, model, bindings, objects = live
    store = workspace.Workspace.create(
        tmp_path / "model.db", model, namespace="support", language="en", record_sources=bindings
    )
    packet = store.read()
    assert packet["inventory"]["record_rows_preloaded"] == 0
    assert "live pages" in packet["text"]
    assert str(database) not in packet["text"]
    assert str(database) not in store.read(product="html")
    assert str(database) not in json.dumps(store.contract())
    request = {
        "revision": packet["revision"],
        "context_digest": packet["context_digest"],
        "id": objects["Tickets"],
        "records": True,
        "limit": 1,
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "compiler.workspace",
            "--store",
            str(store.path),
            "--actor",
            "host-user",
        ],
        input=json.dumps({"operation": "context_read", "request": request}) + "\n",
        text=True,
        encoding="utf8",
        capture_output=True,
        check=True,
    )
    response = json.loads(result.stdout)
    assert response["ok"] is True
    assert response["result"]["rows"] == [[1, None, None]]
    assert response["result"]["data_kind"] == "live_source_page"
    with pytest.raises(Refused, match="Exact reads"):
        store.context_read({**request, "dsn": "sqlite:///another.db"})


def test_special_filename_connection_is_read_only_and_does_not_create_a_sibling(live):
    database, _model, bindings, _objects = live
    with closing(bind.connect(next(iter(bindings.values())))) as db:
        assert db.execute("SELECT count(*) FROM Tickets").fetchone()[0] == 3
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute("DELETE FROM Tickets")
    assert not (database.parent / "source ").exists()
