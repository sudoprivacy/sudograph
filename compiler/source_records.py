"""Bounded live records for an already-authorized, operator-registered source.

This is a private data adapter, not an authorization service. The host must
authorize the model and its complete registered source before each request.
Scoped customer grants must use a host-side projection/gateway; passing a
different catalogue or a prompt never establishes row or field permission.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime

from . import bind, business, catalog, source_schema
from .model_contract import Refused
from .query import quote

MAX_PAGE = 100
MAX_BYTES = 4 * 1024 * 1024


class SourceRecords:
    def __init__(self, model, sources):
        self.schema = model["source_schema"]
        source_schema.validate(self.schema)
        self.objects = {
            obj["id"]: obj for source in self.schema["sources"] for obj in source["objects"]
        }
        known = {source["id"] for source in self.schema["sources"]}
        if not isinstance(sources, dict) or set(sources) - known:
            raise ValueError("live sources must map registered source IDs to operator-owned DSNs")
        self.sources = dict(sources)
        for identity, dsn in self.sources.items():
            if not isinstance(dsn, str) or source_schema.source_id(dsn, ".") != identity:
                raise ValueError("live source identity differs from its registered binding")

    @staticmethod
    def _validate(obj, actual):
        expected = [
            (field["column"], field["declared_type"], field["primary_key"], field["default"])
            for field in obj["fields"]
        ]
        columns = [
            (col["name"], col["type"], col["pk"], col["dflt_value"]) for col in actual["columns"]
        ]
        if (
            obj["object_kind"] != actual["kind"]
            or obj["definition"] != actual["definition"]
            or expected != columns
            or obj["foreign_keys"] != actual["foreign_keys"]
        ):
            raise Refused(
                "SOURCE_SCHEMA_CHANGED",
                "Registered source structure has changed",
                "Rescan the registered source and reconcile the model before reading records",
                409,
            )

    def page(self, identity, *, offset=0, limit=20):
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= MAX_PAGE
        ):
            raise Refused(
                "READ_CONTRACT",
                "Records require offset >= 0 and limit 1..100",
                "Use a bounded page request",
            )
        obj = self.objects.get(identity)
        if obj is None or obj["source"] not in self.sources:
            raise Refused(
                "SOURCE_NOT_REGISTERED",
                "Live records are not registered for this object",
                "Use a source object ID from the authorized catalogue",
            )
        try:
            with closing(bind.connect(self.sources[obj["source"]])) as conn:
                remote = bool(getattr(conn, "provider", None))
                if not remote:
                    conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_BYTES)
                conn.execute("BEGIN")
                definition = conn.describe(obj["name"]) if remote else conn.execute(
                    "SELECT name,type,sql FROM sqlite_master "
                    "WHERE name = ? AND type IN ('table','view')",
                    (obj["name"],),
                ).fetchone()
                if definition is None:
                    raise Refused(
                        "SOURCE_SCHEMA_CHANGED",
                        "Registered source object no longer exists",
                        "Rescan the registered source and reconcile the model",
                        409,
                    )
                self._validate(obj, definition if remote else catalog.describe(conn, definition))
                columns = [field["column"] for field in obj["fields"]]
                keys = [
                    field["column"]
                    for field in sorted(obj["fields"], key=lambda field: field["primary_key"])
                    if field["primary_key"]
                ]
                table = quote(obj["name"])
                if keys:
                    missing = " OR ".join(quote(key) + " IS NULL" for key in keys)
                    if conn.execute(f"SELECT 1 FROM {table} WHERE {missing} LIMIT 1").fetchone():
                        raise Refused(
                            "SOURCE_IDENTITY",
                            "A declared source key contains NULL",
                            "Review the source identity; do not invent a replacement key",
                            409,
                        )
                total = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                # A keyless result has only request-local positions. Ordering
                # makes paging repeatable on unchanged data, not a durable ID.
                order = ",".join(map(quote, keys or columns))
                selected = ",".join(map(quote, columns))
                rows, size = [], 0
                # Beyond the current count is an empty page, including offsets
                # larger than SQLite can bind. Do not sort the entire source.
                source_rows = ()
                if offset < total:
                    source_rows = conn.execute(
                        f"SELECT {selected} FROM {table} ORDER BY {order} LIMIT ? OFFSET ?",
                        (limit, offset),
                    )
                for row in source_rows:
                    values = [source_schema.wire(value) for value in row]
                    size += len(json.dumps(values, ensure_ascii=False).encode("utf8"))
                    if size > MAX_BYTES:
                        raise Refused(
                            "RECORD_PAGE_TOO_LARGE",
                            "Record page exceeds the byte limit",
                            "Request fewer rows; use authorized export "
                            "for oversized single records",
                        )
                    rows.append(values)
        except bind.SourceUnavailable as error:
            raise Refused(
                "SOURCE_UNAVAILABLE",
                "The registered source is unavailable",
                "Restore the registered source connection; do not substitute another source",
                503,
            ) from error
        except sqlite3.DataError as error:
            raise Refused(
                "RECORD_PAGE_TOO_LARGE",
                "A source record exceeds the byte limit",
                "Use an authorized export for oversized records",
            ) from error
        except sqlite3.Error as error:
            raise Refused(
                "SOURCE_READ_FAILED",
                "The registered source could not produce this page",
                "Check the registered connection and source schema; the last model is unchanged",
                503,
            ) from error
        return {
            "source_object": identity,
            "source_digest": business.digest(self.schema),
            "columns": columns,
            "keys": keys,
            "identity": "declared_key" if keys else "request_position",
            "offset": offset,
            "total": total,
            "catalog_total": obj["count"],
            "rows": rows,
            "next_offset": offset + len(rows) if offset + len(rows) < total and rows else None,
            "data_kind": "live_source_page",
            "observation": str(uuid.uuid4()),
            "observed_at": datetime.now(UTC).isoformat(),
            "consistency": "one read transaction; separate pages can observe source changes",
        }
