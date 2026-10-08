"""Compiler-owned source identities, structure and lossless read-only snapshots.

Source names are addresses, never business assertions. A keyless result has
snapshot positions, not guessed row identities. YAML cannot supply these IDs.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import math
import os
import struct
import sys
from array import array
from urllib.parse import quote

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from . import bind, catalog
from .query import quote as sql_quote

CONTRACT = "source-object-field/v1"


def source_id(dsn, base):
    # Resolve relative paths and symlinks; aliases/labels and changing data do
    # not participate. Moving the registered database is a source migration.
    path = os.path.normcase(os.path.realpath(bind._path_of(dsn, base)))
    return "sg-source/" + hashlib.sha256(path.encode()).hexdigest()[:32]


def object_id(source, name):
    return source + "/object/" + quote(name, safe="")


def field_id(obj, column):
    return obj + "/field/" + quote(column, safe="")


def bound_fields(s, tname):
    """The same source IDs are supplied to phase-two/authorised properties."""
    backing = s.backing_of(tname)
    if not backing:
        return {}
    obj = object_id(source_id(s.raw[backing["from"]]["dsn"], s.source_base), backing["table"])
    return {
        pn: field_id(obj, s.column_of(tname, pn))
        for pn, prop in s.types[tname]["props"].items()
        if "op" not in prop
    }


def wire(value):
    if isinstance(value, bytes):
        return {
            "$binary": base64.b64encode(value).decode(),
            "size": len(value),
            "sha256": hashlib.sha256(value).hexdigest(),
        }
    if isinstance(value, int) and abs(value) > 2**53 - 1:
        return {"$integer": str(value)}
    if isinstance(value, float) and not math.isfinite(value):
        return {"$float": repr(value)}
    return value


def _segment(values, segments):
    data = array("I", values)
    if sys.byteorder != "little":
        data.byteswap()
    raw = data.tobytes()
    identity = hashlib.sha256(raw).hexdigest()
    if identity not in segments:
        delta = array("I", values)
        for i in range(len(delta) - 1, 0, -1):
            delta[i] = (delta[i] - delta[i - 1]) & 0xFFFFFFFF
        if sys.byteorder != "little":
            delta.byteswap()
        difference = delta.tobytes()
        variants = {
            "u32le": raw,
            "byteplane": b"".join(raw[i::4] for i in range(4)),
            "delta-byteplane": b"".join(difference[i::4] for i in range(4)),
        }
        compressed = {k: gzip.compress(v, mtime=0) for k, v in variants.items()}
        codec = min(compressed, key=lambda k: len(compressed[k]))
        segments[identity] = {"codec": codec, "data": base64.b64encode(compressed[codec]).decode()}
    return identity


def _snapshot(conn, obj, pool, codes, *, source, segments, chunk_size=5000):
    names = [c["name"] for c in obj["columns"]]
    keys = [c["name"] for c in sorted(obj["columns"], key=lambda c: c["pk"]) if c["pk"]]
    order = " ORDER BY " + ",".join(map(sql_quote, keys)) if keys else ""
    cur = conn.execute(
        f"SELECT {','.join(map(sql_quote, names))} FROM {sql_quote(obj['name'])}{order}"
    )
    chunks, count = [], 0

    def code(value):
        key = (
            type(value).__name__,
            struct.pack("<d", value) if isinstance(value, float) else value,
        )
        if key not in codes:
            codes[key] = len(pool)
            pool.append(wire(value))
        return codes[key]

    while rows := cur.fetchmany(chunk_size):
        count += len(rows)
        # Identical column pages share bytes, including across source views.
        # Every row position remains present; this never deduplicates rows.
        chunks.append(
            [_segment([code(row[col]) for row in rows], segments) for col in range(len(names))]
        )
    return {
        "columns": names,
        "keys": keys,
        "identity": "declared_key" if keys else "snapshot_position",
        "chunk_size": chunk_size,
        "chunks": chunks,
        "count": count,
        "encoding": "dictionary-u32le-segments/v1",
        "source": source,
    }


def record_adapters(s, model):
    """Business aliases reference source pages rather than copying the same rows."""
    result = {}
    filtered = {tn for tn in s.types if s.backing_of(tn).get("where")}
    if filtered:
        from . import browse  # noqa: PLC0415 — scoped legacy pages use the checked query path

        result.update(browse.snapshot(s, only=filtered))
    for tn, definition in s.types.items():
        if tn in filtered:
            continue
        backing = s.backing_of(tn)
        oid = object_id(source_id(s.raw[backing["from"]]["dsn"], s.source_base), backing["table"])
        snapshot = model["snapshots"][oid]
        props = list(definition["props"])
        result[tn] = {
            "source_object": oid,
            "columns": props,
            "positions": [snapshot["columns"].index(s.column_of(tn, p)) for p in props],
            "chunk_size": snapshot["chunk_size"],
            "ids": s.id_props(tn),
            "refs": s.links_of(tn),
            "display": definition.get("display"),
        }
    return result


def _dependencies(definition, names):
    try:
        tree = sqlglot.parse_one(definition, read="sqlite")
        # Scope resolution distinguishes CTE aliases from actual source objects.
        found = {
            src.name
            for scope in traverse_scope(tree)
            for src in scope.sources.values()
            if isinstance(src, exp.Table) and src.name in names
        }
        return sorted(found), None
    except sqlglot.errors.SqlglotError as error:
        return [], str(error)


def build(s, *, records=False):
    """Whole-source review is reserved for the complete phase-one contract.

    Permission-limited Gateway projections do not call this whole-source path.
    Their existing operator-registered property and row boundary stays intact.
    """
    if s.mode != "source_projection":
        return None
    sources, snapshots, dictionaries, segments, done = [], {}, {}, {}, set()
    for raw_name, raw in s.raw.items():
        if not raw.get("dsn"):
            continue
        sid = source_id(raw["dsn"], s.source_base)
        if sid in done:
            continue
        done.add(sid)
        # One transaction covers catalogue, counts and portable source records.
        with bind.connect(raw["dsn"], s.source_base) as conn:
            conn.execute("BEGIN")
            inventory = catalog.inventory(conn)
            names = {obj["name"] for obj in inventory}
            objects, pool, codes = [], [], {}
            table_flags = {r["name"]: r for r in conn.execute("PRAGMA table_list")}
            for obj in inventory:
                oid = object_id(sid, obj["name"])
                projections = [
                    tn
                    for tn in s.types
                    if s.backing_of(tn).get("table") == obj["name"]
                    and s.backing_of(tn).get("from") == raw_name
                ]
                fields = []
                primary = [c for c in obj["columns"] if c["pk"]]
                indexed_key = any(
                    r["origin"] == "pk"
                    for r in conn.execute(f"PRAGMA index_list({sql_quote(obj['name'])})")
                )
                rowid_key = (
                    len(primary) == 1
                    and primary[0]["type"].upper() == "INTEGER"
                    and not indexed_key
                )
                flags = table_flags.get(obj["name"])
                required_key = bool(flags and (flags["wr"] or flags["strict"])) or rowid_key
                for col in obj["columns"]:
                    mappings = [
                        {"type": tn, "property": pn, "description": p.get("description")}
                        for tn in projections
                        for pn, p in s.types[tn]["props"].items()
                        if "op" not in p and s.column_of(tn, pn) == col["name"]
                    ]
                    fields.append(
                        {
                            "id": field_id(oid, col["name"]),
                            "parent": oid,
                            "kind": "schema_field",
                            "label": mappings[0]["property"] if mappings else col["name"],
                            "column": col["name"],
                            "declared_type": col["type"],
                            "primary_key": col["pk"],
                            "nullable": not (col["notnull"] or (col["pk"] and required_key)),
                            "default": col["dflt_value"],
                            "ordinal": col["cid"],
                            "mappings": mappings,
                        }
                    )
                dependencies, error = (
                    _dependencies(obj["definition"], names) if obj["kind"] == "view" else ([], None)
                )
                objects.append(
                    {
                        "id": oid,
                        "kind": "schema_object",
                        "object_kind": obj["kind"],
                        "source": sid,
                        "name": obj["name"],
                        "label": s.types[projections[0]].get("label", projections[0])
                        if projections
                        else obj["name"],
                        "count": obj["count"],
                        "definition": obj["definition"],
                        "fields": fields,
                        "field_count": len(obj["columns"]),
                        "foreign_keys": obj["foreign_keys"],
                        "dependencies": dependencies,
                        "dependency_error": error,
                        "projections": projections,
                    }
                )
                if records:
                    snapshots[oid] = _snapshot(
                        conn, obj, pool, codes, source=sid, segments=segments
                    )
                    if snapshots[oid]["count"] != obj["count"]:
                        raise ValueError(
                            f"{obj['name']}: source snapshot count differs from catalogue"
                        )
            sources.append({"id": sid, "label": raw.get("label", raw_name), "objects": objects})
            if records:
                dictionaries[sid] = base64.b64encode(
                    gzip.compress(
                        json.dumps(pool, ensure_ascii=False, separators=(",", ":")).encode(),
                        mtime=0,
                    )
                ).decode()
    result = {
        "identity_contract": CONTRACT,
        "sources": sources,
        "snapshots": snapshots,
        "dictionaries": dictionaries,
        "segments": segments,
        "schema_complete": True,
        "record_complete": records,
    }
    validate(result)
    return result


def validate(model):
    """Native rendering refuses missing, duplicate or author-substituted IDs."""
    if model.get("identity_contract") != CONTRACT:
        raise ValueError("source schema requires compiler-owned source-object-field/v1 identities")
    if any(
        segment.get("codec") not in ("u32le", "byteplane", "delta-byteplane")
        for segment in model.get("segments", {}).values()
    ):
        raise ValueError("unsupported source column segment codec")
    seen = set()
    for source in model["sources"]:
        for obj in source["objects"]:
            if obj["id"] != object_id(source["id"], obj["name"]):
                raise ValueError("source object identity differs from its source address")
            for node in [obj, *obj["fields"]]:
                if node["id"] in seen:
                    raise ValueError("duplicate source object/field identity")
                seen.add(node["id"])
            for field in obj["fields"]:
                if (
                    field["id"] != field_id(obj["id"], field["column"])
                    or field["parent"] != obj["id"]
                ):
                    raise ValueError(
                        "source field identity differs from its source column; "
                        "regenerate with compiler"
                    )
            if len(obj["fields"]) != obj["field_count"]:
                raise ValueError("source field inventory is incomplete; regenerate with compiler")
            snapshot = model.get("snapshots", {}).get(obj["id"])
            if snapshot and (
                snapshot.get("encoding") != "dictionary-u32le-segments/v1"
                or snapshot.get("source") not in model.get("dictionaries", {})
            ):
                raise ValueError("unsupported source snapshot codec or missing dictionary")
            if snapshot and any(
                len(page) != len(obj["fields"])
                or any(identity not in model.get("segments", {}) for identity in page)
                for page in snapshot["chunks"]
            ):
                raise ValueError("source column segments are incomplete; regenerate with --records")
            if model.get("record_complete") and (
                not snapshot
                or snapshot["count"] != obj["count"]
                or snapshot["columns"] != [f["column"] for f in obj["fields"]]
            ):
                raise ValueError("source snapshot is incomplete; regenerate with --records")
            if (
                snapshot
                and len(snapshot["chunks"])
                != (snapshot["count"] + snapshot["chunk_size"] - 1) // snapshot["chunk_size"]
            ):
                raise ValueError("source record chunks are incomplete; regenerate with --records")
