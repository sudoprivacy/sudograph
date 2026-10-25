"""Transactional model authoring, independent of optional GitLab publication.

The embedding host owns authentication and source registration. This store is
not a public endpoint: its path, source baseline, namespace and actor are host
inputs, never tool arguments. YAML is the authority; compiled JSON, HTML and
agent context are immutable products of the same committed revision.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

import yaml

from . import app, business
from .context import Reader, registered_pointers
from .model_contract import SOURCE_REQUEST, Refused, compile_model, parse_document

FORMAT = "sudograph-workspace/v1"
_MISSING = object()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _dump(value):
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False)


def _definitions(doc):
    """Merge by canonical concept, including author keys in conflict detection."""
    result = copy.deepcopy(doc)
    if "definitions" in result:
        result["definitions"] = {
            business.identity_key(doc["namespace"], item["concept"]): {"key": key, "value": item}
            for key, item in doc["definitions"].items()
        }
    return result


def _merge(base, current, incoming, path="", conflicts=None):
    if conflicts is None:
        conflicts = []
    if incoming in (base, current):
        return current
    if current == base:
        return incoming
    # Definitions and evidence are atomic. Editing a shared statement or its
    # evidence concurrently must not silently assemble a third interpretation.
    if base is _MISSING and path in {"definitions", "documents", "views", "translations"}:
        base = {}
    if all(isinstance(v, dict) for v in (base, current, incoming)) and (
        not path or path in {"definitions", "documents", "views"} or path.startswith("translations")
    ):
        result = {}
        for key in sorted(base.keys() | current.keys() | incoming.keys()):
            item = _merge(
                base.get(key, _MISSING),
                current.get(key, _MISSING),
                incoming.get(key, _MISSING),
                f"{path}.{key}".strip("."),
                conflicts,
            )
            if item is not _MISSING:
                result[key] = item
        return result
    conflicts.append(path)
    return current


def merge_documents(base, current, incoming):
    conflicts = []
    result = _merge(*(_definitions(doc) for doc in (base, current, incoming)), conflicts=conflicts)
    if conflicts:
        raise Refused(
            "MODEL_CONFLICT",
            "Concurrent edits affect the same model content",
            {"paths": conflicts, "action": "Read the current model and resolve these edits"},
            409,
        )
    if "definitions" in result:
        entries = list(result["definitions"].values())
        keys = [entry["key"] for entry in entries]
        if len(keys) != len(set(keys)):
            raise Refused(
                "MODEL_CONFLICT",
                "Concurrent definitions reuse an author key",
                "Read the current model and give distinct concepts distinct keys",
                409,
            )
        result["definitions"] = {entry["key"]: entry["value"] for entry in entries}
    return result


class Workspace:
    """One canonical model with process-safe history and idempotent operations."""

    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def _db(self, *, write=False):
        db = sqlite3.connect(self.path.resolve().as_uri() + "?mode=rw", uri=True, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @classmethod
    def create(cls, path, baseline, *, namespace, language="zh", pointers=None):
        """Operator registration. Existing stores and source rebinding are refused."""
        if not isinstance(namespace, str) or not namespace.strip():
            raise ValueError("a registered identity namespace is required")
        pointers = registered_pointers([] if pointers is None else pointers)
        content = _dump(
            {
                "format": SOURCE_REQUEST,
                "baseline": {
                    "manifest": "registered-source-baseline",
                    "sha256": business.digest(baseline),
                },
            }
        )
        model, registry = compile_model(content, baseline, namespace=namespace)
        settings = {
            "format": FORMAT,
            "baseline": baseline,
            "namespace": namespace,
            "language": language,
            "pointers": pointers,
        }
        revision, products = cls._compile(content, model, registry, settings, parent=None)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents accidentally attaching another source to
        # an existing project. The transaction below is its only initial state.
        with path.open("xb"):
            pass
        store = cls(path)
        with store._db() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE settings (id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL);
                CREATE TABLE revisions (id TEXT PRIMARY KEY, parent TEXT REFERENCES revisions(id),
                    content TEXT NOT NULL, registry TEXT NOT NULL, model TEXT NOT NULL,
                    html TEXT NOT NULL, context TEXT NOT NULL, actor TEXT NOT NULL);
                CREATE TABLE head (id INTEGER PRIMARY KEY CHECK (id = 1),
                    revision TEXT NOT NULL REFERENCES revisions(id));
                CREATE TABLE operations (id TEXT PRIMARY KEY,
                    digest TEXT NOT NULL, receipt TEXT NOT NULL);
            """)
            db.execute("INSERT INTO settings VALUES (1, ?)", (_json(settings),))
            store._insert(
                db,
                revision,
                parent=None,
                content=content,
                registry=registry,
                products=products,
                actor="operator",
            )
            db.execute("INSERT INTO head VALUES (1, ?)", (revision,))
        return store

    @staticmethod
    def _compile(content, model, registry, settings, *, parent):
        revision = business.digest(
            {
                "parent": parent,
                "content": content,
                "model": model,
                "registry": registry,
                "language": settings["language"],
                "pointers": settings["pointers"],
                "context_transport": "mcp",
            }
        )
        model = {
            **model,
            "projection": {
                **model["projection"],
                "model_revision": revision,
                "context_transport": "mcp",
                "knowledge_pointers": settings["pointers"],
            },
        }
        packet = Reader(
            model, revision=revision, pointers=settings["pointers"], transport="mcp"
        ).pack()
        html = app.render(model, language=settings["language"])
        return revision, {"model": model, "context": packet, "html": html}

    @staticmethod
    def _insert(db, revision, *, parent, content, registry, products, actor):
        db.execute(
            "INSERT INTO revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                revision,
                parent,
                content,
                _json(registry),
                _json(products["model"]),
                products["html"],
                _json(products["context"]),
                actor,
            ),
        )

    def _row(self, db, revision=None):
        if revision is None:
            revision = db.execute("SELECT revision FROM head WHERE id = 1").fetchone()[0]
        if not isinstance(revision, str) or not revision:
            raise Refused(
                "REVISION_UNKNOWN",
                "Revision must be an opaque string identity",
                "Use the revision returned by this model's contract",
                409,
            )
        row = db.execute("SELECT * FROM revisions WHERE id = ?", (revision,)).fetchone()
        if row is None:
            raise Refused(
                "REVISION_UNKNOWN",
                "Revision does not belong to this model",
                "Read this model's contract and use its current revision",
                409,
            )
        return row

    def contract(self):
        with self._db() as db:
            settings = json.loads(
                db.execute("SELECT payload FROM settings WHERE id = 1").fetchone()[0]
            )
            row = self._row(db)
            return {
                "format": FORMAT,
                "revision": row["id"],
                "namespace": settings["namespace"],
                "baseline": parse_document(row["content"])["baseline"],
                "model": row["content"],
                "write": {
                    "required": ["base_revision", "operation_id", "model"],
                    "accepted_format": business.FORMAT,
                    "effects": "model, graph and context only; source is read-only",
                },
            }

    def read(self, *, revision=None, product="context"):
        if not isinstance(product, str) or product not in {
            "context",
            "html",
            "model",
            "content",
            "registry",
        }:
            raise Refused(
                "PRODUCT_UNKNOWN", "Unknown model product", "Use context, html, model or content"
            )
        with self._db() as db:
            row = self._row(db, revision)
            return row[product] if product in {"html", "content"} else json.loads(row[product])

    def context_read(self, request):
        if (
            not isinstance(request, dict)
            or set(request)
            - {"revision", "context_digest", "id", "records", "offset", "limit", "selection"}
            or not {"revision", "context_digest", "id"} <= set(request)
        ):
            raise Refused(
                "READ_CONTRACT",
                "Exact reads require revision, context_digest and id",
                "Use the pointers in the current context packet",
            )
        if (
            not isinstance(request["id"], str)
            or not request["id"]
            or not isinstance(request["context_digest"], str)
            or ("records" in request and not isinstance(request["records"], bool))
            or any(key in request and type(request[key]) is not int for key in ("offset", "limit"))
        ):
            raise Refused(
                "READ_CONTRACT",
                "Invalid identity, digest or pagination types",
                "Use the typed exact-read pointer in the context packet",
            )
        model = self.read(revision=request["revision"], product="model")
        packet = self.read(revision=request["revision"], product="context")
        if request["context_digest"] != packet["context_digest"]:
            raise Refused(
                "CONTEXT_STALE",
                "Context digest does not match this revision",
                "Refresh the context packet and reuse its exact read pointer",
                409,
            )
        with self._db() as db:
            settings = json.loads(
                db.execute("SELECT payload FROM settings WHERE id = 1").fetchone()[0]
            )
        return Reader(
            model, revision=request["revision"], pointers=settings["pointers"], transport="mcp"
        ).read(
            request["id"],
            **{k: v for k, v in request.items() if k not in {"id", "revision", "context_digest"}},
        )

    def apply(self, request, *, actor):
        """Host-authorized edit. No paths, compiler code or generated products accepted."""
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("the host must supply the authenticated actor")
        if not isinstance(request, dict) or set(request) != {
            "base_revision",
            "operation_id",
            "model",
        }:
            raise Refused(
                "WRITE_CONTRACT",
                "Expected base_revision, operation_id and model only",
                "Read the contract; generated products and source paths are not model inputs",
            )
        if any(
            not isinstance(request[key], str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", request[key])
            for key in ("base_revision", "operation_id")
        ):
            raise Refused(
                "WRITE_CONTRACT",
                "Invalid revision or operation identity",
                "Use opaque IDs from the host",
            )
        parse_document(request["model"])
        digest = business.digest({"request": request, "actor": actor})
        with self._db(write=True) as db:
            operation = db.execute(
                "SELECT * FROM operations WHERE id = ?", (request["operation_id"],)
            ).fetchone()
            if operation:
                if operation["digest"] != digest:
                    raise Refused(
                        "OPERATION_CONFLICT",
                        "Operation ID was already used with another payload or actor",
                        "Reuse the original payload for retry, or allocate a new operation ID",
                        409,
                    )
                return json.loads(operation["receipt"])
            settings = json.loads(
                db.execute("SELECT payload FROM settings WHERE id = 1").fetchone()[0]
            )
            base, current = self._row(db, request["base_revision"]), self._row(db)
            content = request["model"]
            # Validate the author's branch first, before attempting a merge.
            compile_model(
                content,
                settings["baseline"],
                json.loads(base["registry"]),
                namespace=settings["namespace"],
            )
            is_merged = base["id"] != current["id"]
            if is_merged:
                content = _dump(
                    merge_documents(
                        *(
                            parse_document(value)
                            for value in (base["content"], current["content"], content)
                        )
                    )
                )
            try:
                model, registry = compile_model(
                    content,
                    settings["baseline"],
                    json.loads(current["registry"]),
                    namespace=settings["namespace"],
                )
            except ValueError as error:
                if is_merged:
                    raise Refused(
                        "MODEL_CONFLICT",
                        "Merged edits fail the shared compiler",
                        {
                            "compiler": str(error),
                            "action": "Read the current model and resolve dependencies",
                        },
                        409,
                    ) from error
                raise
            revision, products = self._compile(
                content, model, registry, settings, parent=current["id"]
            )
            self._insert(
                db,
                revision,
                parent=current["id"],
                content=content,
                registry=registry,
                products=products,
                actor=actor,
            )
            db.execute("UPDATE head SET revision = ? WHERE id = 1", (revision,))
            receipt = {
                "format": FORMAT,
                "operation_id": request["operation_id"],
                "revision": revision,
                "parent_revision": current["id"],
                "base_revision": base["id"],
                "merged": is_merged,
                "context_digest": products["context"]["context_digest"],
            }
            db.execute(
                "INSERT INTO operations VALUES (?, ?, ?)",
                (request["operation_id"], digest, _json(receipt)),
            )
            return receipt


def main():
    """Private host subprocess protocol; never exposes source registration to agents."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True)
    parser.add_argument("--actor", required=True)
    args = parser.parse_args()
    store = Workspace(args.store)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
            operation = request.get("operation")
            if operation == "contract" and set(request) == {"operation"}:
                result = store.contract()
            elif operation == "apply" and set(request) == {"operation", "request"}:
                result = store.apply(request["request"], actor=args.actor)
            elif operation == "context_read" and set(request) == {"operation", "request"}:
                result = store.context_read(request["request"])
            elif operation == "read" and set(request) <= {"operation", "revision", "product"}:
                result = store.read(**{k: v for k, v in request.items() if k != "operation"})
            else:
                raise Refused(
                    "WRITE_CONTRACT", "Unknown operation or arguments", "Read the contract"
                )
            response = {"ok": True, "result": result}
        except (ValueError, KeyError) as error:
            response = {
                "ok": False,
                "error": {
                    "code": getattr(error, "code", "COMPILER_REJECTED"),
                    "reason": str(error),
                    "recovery": getattr(error, "recovery", "Correct the model and retry"),
                },
            }
        print(_json(response), flush=True)


if __name__ == "__main__":
    main()
