"""The host registers facts once; neither a retry nor an incomplete scan can replace them."""

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest

from compiler import app, bind, catalog, project, registration, source_schema
from compiler.model_contract import Refused
from compiler.workspace import Workspace


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source #registered.db"
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
            CREATE TABLE Tickets(id INTEGER PRIMARY KEY, amount REAL, picture BLOB);
            CREATE VIEW Totals AS SELECT sum(amount) amount FROM Tickets;
        """)
        db.executemany(
            "INSERT INTO Tickets VALUES (?, ?, X'00FF')",
            [(i, None if i == 1 else i * 2.5) for i in range(1, 16)],
        )
    return path, "sqlite:///" + path.as_posix(), tmp_path / "models" / "support.db"


def create(fixture_source, **changes):
    _, dsn, target = fixture_source
    return registration.register(
        target,
        **{
            "source": dsn,
            "namespace": "support",
            "operation_id": "connect-1",
            "actor": "host-alice",
            "language": "en",
            **changes,
        },
    )


def test_whole_registration_shares_one_read_transaction_without_copying_source(source, monkeypatch):
    path, dsn, _ = source
    opened, original_open, draft = [], bind._open, project.draft

    def track(*args):
        conn = original_open(*args)
        opened.append(conn)
        return conn

    def concurrent_writer(*args, **kwargs):
        result = draft(*args, **kwargs)
        with closing(sqlite3.connect(path)) as writer, writer:
            writer.execute("INSERT INTO Tickets VALUES (16, 99, NULL)")
        return result

    monkeypatch.setattr(bind, "_open", track)
    monkeypatch.setattr(project, "draft", concurrent_writer)
    store = create(source)
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")
    model = store.read(product="model")
    objects = {o["name"]: o for s in model["source_schema"]["sources"] for o in s["objects"]}
    assert objects["Tickets"]["count"] == 15
    assert next(o for o in model["coverage"][0]["objects"] if o["name"] == "Tickets")["count"] == 15
    assert catalog.scan(dsn)[0]["count"] == 16
    receipt = store.registration()
    assert receipt["scan"]["structure_complete"] and receipt["scan"]["inventory_exhausted"]
    assert receipt["scan"]["objects"] == 2 and receipt["scan"]["fields"] == 4
    assert receipt["scan"]["observation"] == model["projection"]["source_observation"]
    assert receipt["initial_revision"] == store.head()["revision"]
    with store._db() as registered:
        assert registered.execute("SELECT actor FROM revisions").fetchone()[0] == "host-alice"
    assert receipt["records"] == {"delivery": "live", "export_complete": False, "rows_embedded": 0}
    assert not model["source_schema"]["snapshots"] and not model["records"]
    packet = store.read()
    page = store.context_read(
        {
            "revision": packet["revision"],
            "context_digest": packet["context_digest"],
            "id": objects["Tickets"]["id"],
            "records": True,
        }
    )
    assert page["total"] == 16 and page["catalog_total"] == 15
    for value in (json.dumps(receipt), store.read(product="html"), packet["text"]):
        assert str(path) not in value and dsn not in value


def test_observation_leases_keep_snapshot_and_release_on_error(source):
    path, dsn, _ = source
    with bind.observation(dsn) as proof:
        with closing(bind.connect(dsn)) as first:
            assert first.execute("SELECT count(*) FROM Tickets").fetchone()[0] == 15
        with closing(sqlite3.connect(path)) as writer, writer:
            writer.execute("ALTER TABLE Tickets ADD COLUMN added TEXT")
        with bind.connect(dsn) as second:
            assert len(second.execute("PRAGMA table_info(Tickets)").fetchall()) == 3
        with pytest.raises(bind.BindingError, match="active observation"):
            bind.connect("sqlite:///unregistered.db")
        with pytest.raises(bind.BindingError, match="nested"), bind.observation(dsn):
            pass
    assert "completed_at" in proof
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        first.execute("SELECT 1")
    with pytest.raises(RuntimeError), bind.observation(dsn):
        raise RuntimeError("cancelled scan")
    with closing(bind.connect(dsn)) as fresh:
        assert len(fresh.execute("PRAGMA table_info(Tickets)").fetchall()) == 4


def test_retry_returns_original_receipt_without_rescanning_or_changing_source(source, monkeypatch):
    path, _, target = source
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    store = create(source)
    receipt, head = store.registration(), store.head()
    assert receipt["connection"]["source"] == source_schema.source_id(source[1], ".")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before

    def unexpected(*_args, **_kwargs):
        raise AssertionError("an accepted registration was scanned twice")

    monkeypatch.setattr(project, "draft", unexpected)
    assert create(source).registration() == receipt
    assert Workspace(target).head() == head
    if os.name != "nt":
        assert target.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("snapshot_records", [False, True])
def test_native_overview_does_not_transport_model_rows(source, monkeypatch, snapshot_records):
    store = create(source, snapshot_records=snapshot_records)
    receipt, head = store.registration(), store.head()

    def unexpected(*_args, **_kwargs):
        raise AssertionError("metadata must not read a complete model revision or rescan")

    monkeypatch.setattr(store, "_row", unexpected)
    monkeypatch.setattr(project, "draft", unexpected)
    overview = store.overview()
    assert overview == {**head, "source_registration": receipt}
    assert overview["source_registration"]["records"]["rows_embedded"] == (
        16 if snapshot_records else 0
    )
    assert str(source[0]) not in json.dumps(overview)
    assert len(json.dumps(overview)) < 4096


@pytest.mark.parametrize(
    "changes",
    [
        {"operation_id": "another"},
        {"actor": "host-bob"},
        {"namespace": "another"},
        {"language": "zh"},
        {"snapshot_records": True},
    ],
)
def test_an_existing_model_cannot_be_rebound_by_registration(source, changes):
    store = create(source)
    before = store.contract()
    with pytest.raises(Refused) as error:
        create(source, **changes)
    assert error.value.code == "REGISTRATION_CONFLICT"
    assert store.contract() == before


def test_identical_copy_is_not_automatically_the_same_source(source, tmp_path):
    store = create(source)
    copy = tmp_path / "independent-copy.db"
    shutil.copyfile(source[0], copy)
    with pytest.raises(Refused) as error:
        create(source, source="sqlite:///" + copy.as_posix())
    assert error.value.code == "REGISTRATION_CONFLICT"
    assert store.registration()["connection"]["source"] == source_schema.source_id(source[1], ".")


def test_lost_response_after_atomic_publication_recovers_the_committed_receipt(source, monkeypatch):
    link = registration.os.link

    def interrupted(staged, target):
        link(staged, target)
        raise OSError("lost response after publication")

    monkeypatch.setattr(registration.os, "link", interrupted)
    with pytest.raises(OSError, match="lost response"):
        create(source)
    receipt = Workspace(source[2]).registration()

    def unexpected(*_args, **_kwargs):
        raise AssertionError("published model must not be rebuilt")

    monkeypatch.setattr(project, "draft", unexpected)
    assert create(source).registration() == receipt


def test_partial_scan_and_failed_compile_never_publish_a_model(source, monkeypatch):
    with monkeypatch.context() as scope:
        scope.setattr(source_schema, "_dependencies", lambda *_: ([], "unsupported source SQL"))
        with pytest.raises(Refused) as error:
            create(source)
        assert error.value.code == "SCAN_INCOMPLETE" and not source[2].exists()
    with monkeypatch.context() as scope:

        def broken(*_args, **_kwargs):
            raise ValueError("compiler rejected this source")

        scope.setattr(Workspace, "create", broken)
        with pytest.raises(ValueError, match="compiler rejected"):
            create(source)
        assert not source[2].exists()
    assert create(source).head()["revision"]


def test_target_lock_serializes_one_registration_without_blocking_other_models(source, tmp_path):
    path, dsn, target = source
    target.parent.mkdir()
    lock = target.with_name(target.name + ".registration-lock")
    with closing(sqlite3.connect(lock)) as owner:
        owner.execute("CREATE TABLE mutex(id INTEGER PRIMARY KEY)")
        owner.execute("BEGIN IMMEDIATE")
        with pytest.raises(Refused) as error:
            create(source)
        assert error.value.code == "REGISTRATION_BUSY"
        other = registration.register(
            tmp_path / "other.db",
            source=dsn,
            namespace="other",
            operation_id="other",
            actor="host-alice",
        )
        assert other.registration()["scan"]["status"] == "complete"
    assert not target.exists() and path.exists()


def test_failed_projection_check_cannot_be_published_as_a_complete_scan(source, monkeypatch):
    bundle = app.bundle

    def failed(*args, **kwargs):
        result = bundle(*args, **kwargs)
        next(iter(result["views"].values()))["checks"].append({"name": "source-check", "ok": False})
        return result

    monkeypatch.setattr(app, "bundle", failed)
    with pytest.raises(Refused) as error:
        create(source)
    assert error.value.code == "SCAN_INCOMPLETE" and not source[2].exists()


def test_operator_worker_rejects_forged_coverage_and_supports_typed_registration(source):
    _, dsn, target = source
    request = {
        "source": dsn,
        "namespace": "support",
        "operation_id": "connect-1",
        "language": "en",
        "snapshot_records": False,
    }

    def invoke(body):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "compiler.registration",
                "--store",
                str(target),
                "--actor",
                "host-alice",
            ],
            input=json.dumps(body),
            text=True,
            encoding="utf8",
            capture_output=True,
            check=True,
        )
        return json.loads(result.stdout)

    refused = invoke({**request, "complete": True})
    assert not refused["ok"] and refused["error"]["code"] == "REGISTRATION_CONTRACT"
    assert not target.exists()
    accepted = invoke(request)
    assert accepted["ok"] and accepted["result"]["registration"]["scan"]["structure_complete"]
    assert invoke(request) == accepted


def test_source_cannot_overlap_private_model_storage(source):
    _, dsn, _ = source
    with pytest.raises(Refused, match="overlap"):
        registration.register(
            source[0], source=dsn, namespace="support", operation_id="connect-1", actor="host-alice"
        )


def test_explicit_snapshot_and_unsupported_provider_do_not_masquerade_as_live_scans(source):
    store = create(source, snapshot_records=True)
    receipt = store.registration()
    assert receipt["records"] == {
        "delivery": "snapshot",
        "export_complete": True,
        "rows_embedded": 16,
    }
    with pytest.raises(Refused) as error:
        create(source, source="postgresql://unregistered")
    assert error.value.code == "SOURCE_PROVIDER_UNSUPPORTED"


def test_connected_but_unsupported_structure_is_partial_not_a_failed_connection(source):
    with closing(sqlite3.connect(source[0])) as db, db:
        db.executescript("""
            CREATE TABLE Parent(a INTEGER, b INTEGER, PRIMARY KEY(a,b));
            CREATE TABLE Child(id INTEGER PRIMARY KEY, a INTEGER, b INTEGER,
                FOREIGN KEY(a,b) REFERENCES Parent(a,b));
        """)
    with pytest.raises(Refused) as error:
        create(source)
    assert error.value.code == "SCAN_INCOMPLETE"
    assert error.value.recovery["connection"] == "connected"
    assert error.value.recovery["scan"] == "partial"
    assert "composite" in error.value.recovery["compiler"]
    assert str(source[0]) not in json.dumps(error.value.recovery)
    assert not source[2].exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"language": {}},
        {"snapshot_records": 1},
        {"actor": []},
        {"namespace": None},
    ],
)
def test_malformed_host_settings_are_typed_refusals(source, changes):
    with pytest.raises(Refused) as error:
        create(source, **changes)
    assert error.value.code == "REGISTRATION_CONTRACT" and not source[2].exists()
