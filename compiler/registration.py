"""Private host registration: one source observation, checked model and durable receipt.

The embedding host authorizes the source and supplies every argument. This is
not an agent-facing source/path registration tool or a second connection store.
The per-target SQLite mutex serializes creation; the model itself owns its sole
registration receipt. An interrupted publication is recovered from that receipt.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
from contextlib import closing, contextmanager
from pathlib import Path

import yaml

from . import app, bind, business, project, source_schema, spec
from .model_contract import Refused
from .workspace import Workspace

FORMAT = "sudograph-source-registration/v1"


def _identity(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
        raise Refused(
            "REGISTRATION_CONTRACT", f"Invalid {name}", "Use a host-owned opaque identity"
        )


def _existing(path, digest):
    store = Workspace(path)
    receipt = store.registration()
    if receipt is None or receipt.get("request_digest") != digest:
        raise Refused(
            "REGISTRATION_CONFLICT",
            "A different registration already owns this model",
            "Open the registered project; source replacement requires a checked migration",
            409,
        )
    return store


@contextmanager
def _creation_lock(path):
    with closing(sqlite3.connect(path, timeout=1, isolation_level=None)) as control:
        try:
            control.execute("CREATE TABLE IF NOT EXISTS mutex (id INTEGER PRIMARY KEY)")
            control.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as error:
            if getattr(error, "sqlite_errorcode", None) in {
                sqlite3.SQLITE_BUSY,
                sqlite3.SQLITE_LOCKED,
            }:
                raise Refused(
                    "REGISTRATION_BUSY",
                    "This model's registration is running",
                    "Retry the same registration operation",
                    409,
                ) from error
            raise
        yield


def register(
    path, *, source, namespace, operation_id, actor, language="zh", snapshot_records=False
):
    """Host-only SQLite registration. Retries never replace a committed model."""
    _identity(operation_id, "registration operation")
    if (
        not isinstance(actor, str)
        or not actor.strip()
        or not isinstance(namespace, str)
        or not namespace.strip()
        or not isinstance(language, str)
        or language not in {"en", "zh"}
        or type(snapshot_records) is not bool
    ):
        raise Refused(
            "REGISTRATION_CONTRACT",
            "Invalid registration settings",
            "Use the deployment's actor, namespace, locale and record-delivery mode",
        )
    if not isinstance(source, str) or not source.startswith("sqlite:///"):
        raise Refused(
            "SOURCE_PROVIDER_UNSUPPORTED",
            "Complete registration currently requires SQLite",
            "Use a supported complete-scan provider; connection success is not coverage",
        )
    path = Path(path).resolve()
    if path.is_dir():
        raise Refused(
            "REGISTRATION_CONTRACT",
            "Model storage must name a file",
            "Use the host-owned model store path",
        )
    source_path = Path(bind._path_of(source, ".")).resolve()
    lock = path.with_name(path.name + ".registration-lock")
    if source_path in {path, lock} or any(
        target.exists() and source_path.exists() and os.path.samefile(source_path, target)
        for target in (path, lock)
    ):
        raise Refused(
            "REGISTRATION_CONTRACT",
            "Source and model storage overlap",
            "Select a source database separate from this model's private storage",
        )
    dsn = "sqlite:///" + source_path.as_posix()
    identity = source_schema.source_id(dsn, ".")
    request = {
        "operation_id": operation_id,
        "actor": actor,
        "source": identity,
        "namespace": namespace,
        "language": language,
        "snapshot_records": snapshot_records,
    }
    digest = business.digest(request)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _creation_lock(lock):
            if path.exists():
                return _existing(path, digest)
            with tempfile.TemporaryDirectory(
                prefix=".sudograph-register-", dir=path.parent
            ) as temporary:
                folder = Path(temporary)
                with bind.observation(dsn) as observation:
                    try:
                        config = folder / "source.yaml"
                        config.write_text(yaml.safe_dump(project.draft(dsn)), encoding="utf8")
                        baseline = app.bundle(
                            spec.load(str(config), expected_mode="source_projection"),
                            records=snapshot_records,
                        )
                    except Refused:
                        raise
                    except (ValueError, bind.BindingError, sqlite3.Error) as error:
                        detail = str(error)
                        for private in (dsn, str(source_path), source_path.as_posix(), str(folder)):
                            detail = detail.replace(private, "<registered-source>")
                        raise Refused(
                            "SCAN_INCOMPLETE",
                            "The connected source failed projection checks",
                            {
                                "connection": "connected",
                                "scan": "partial",
                                "compiler": detail,
                                "action": "Repair the provider and rescan",
                            },
                        ) from error
                schema = baseline["source_schema"]
                source_schema.validate(schema)
                failed = [
                    check
                    for view in baseline["views"].values()
                    for check in view["checks"]
                    if not check["ok"]
                ]
                if failed:
                    raise Refused(
                        "SCAN_INCOMPLETE",
                        "Source projection compiler checks failed",
                        {"checks": failed, "action": "Repair the provider and rescan"},
                    )
                objects = [obj for item in schema["sources"] for obj in item["objects"]]
                unresolved = [obj["id"] for obj in objects if obj.get("dependency_error")]
                if unresolved:
                    raise Refused(
                        "SCAN_INCOMPLETE",
                        "Some source SQL dependencies are unresolved",
                        {"objects": unresolved, "action": "Extend the provider and rescan"},
                    )
                baseline["projection"]["source_observation"] = observation
                receipt = {
                    "format": FORMAT,
                    "operation_id": operation_id,
                    "request_digest": digest,
                    "connection": {
                        "status": "connected",
                        "provider": "sqlite",
                        "source": identity,
                        "observed_at": observation["completed_at"],
                    },
                    "scan": {
                        "status": "complete",
                        "scope": "complete registered SQLite source",
                        "inventory_exhausted": True,
                        "structure_complete": True,
                        "objects": len(objects),
                        "tables": sum(obj["object_kind"] == "table" for obj in objects),
                        "database_views": sum(obj["object_kind"] == "view" for obj in objects),
                        "fields": sum(len(obj["fields"]) for obj in objects),
                        "observation": observation,
                    },
                    "records": {
                        "delivery": "snapshot" if snapshot_records else "live",
                        "export_complete": schema["record_complete"],
                        "rows_embedded": sum(s["count"] for s in schema["snapshots"].values()),
                    },
                }
                sources = {} if snapshot_records else {identity: dsn}
                staged = Workspace.create(
                    folder / "model.db",
                    baseline,
                    namespace=namespace,
                    language=language,
                    record_sources=sources,
                    registration=receipt,
                    actor=actor,
                )
                os.chmod(staged.path, 0o600)
                # All connections are closed: SQLite has checkpointed its WAL.
                # Link is an atomic no-replace publication on the same volume.
                # A lost response after this point is recovered from the model.
                os.link(staged.path, path)
            return Workspace(path)
    except bind.SourceUnavailable as error:
        raise Refused(
            "SOURCE_UNAVAILABLE",
            "The registered source is unavailable",
            "Restore the host source connection and retry the same operation",
            503,
        ) from error
    except sqlite3.OperationalError as error:
        if getattr(error, "sqlite_errorcode", None) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            raise Refused(
                "SOURCE_BUSY",
                "The registered source is busy",
                "Retry the same source registration when the source is available",
                409,
            ) from error
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True)
    parser.add_argument("--actor", required=True)
    args = parser.parse_args()
    try:
        payload = sys.stdin.read(65537)
        if len(payload.encode("utf8")) > 65536:
            raise Refused(
                "REGISTRATION_CONTRACT",
                "Registration request exceeds 64 KiB",
                "Supply a registered host source and its metadata only",
            )
        request = json.loads(payload)
        if not isinstance(request, dict) or set(request) != {
            "source",
            "namespace",
            "operation_id",
            "language",
            "snapshot_records",
        }:
            raise Refused(
                "REGISTRATION_CONTRACT",
                "Unknown or missing registration arguments",
                "Use the host registration contract; coverage cannot be supplied",
            )
        store = register(args.store, actor=args.actor, **request)
        result = {"contract": store.contract(), "registration": store.registration()}
        response = {"ok": True, "result": result}
    except (ValueError, bind.BindingError, OSError, sqlite3.Error) as error:
        response = {
            "ok": False,
            "error": {
                "code": getattr(error, "code", "SOURCE_REGISTRATION_FAILED"),
                "reason": (
                    error.reason
                    if isinstance(error, Refused)
                    else "The source could not produce a complete registered model"
                ),
                "recovery": getattr(
                    error, "recovery", "Check the host source registration and retry"
                ),
            },
        }
    print(json.dumps(response, ensure_ascii=False))


if __name__ == "__main__":
    main()
