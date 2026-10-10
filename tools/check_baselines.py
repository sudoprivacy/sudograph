"""Check frozen phase-one examples; optionally compare every value to SQLite.

The default CI check needs no source database. It verifies the locked files and
the source contract inside the artifact. --source additionally audits the actual
read-only database, rather than treating a completeness flag as evidence.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import sqlite3
import struct
import sys
from pathlib import Path

from compiler import html_export, source_schema

ROOT = Path(__file__).resolve().parents[1]
FORMAT = "sudograph-phase-one-baseline/v1"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def bundle(path: Path) -> dict:
    text = html_export.unpack(path.read_text(encoding="utf-8"))
    marker = "const BUNDLE = "
    if marker not in text:
        raise ValueError("artifact has no native compiler bundle")
    return json.JSONDecoder().raw_decode(text.split(marker, 1)[1])[0]


def coverage(model: dict) -> dict:
    source_schema.validate(model)
    if not model.get("sources") or not all(
        model.get(key) is True for key in ("schema_complete", "record_complete")
    ):
        raise ValueError("baseline requires complete source structure and records")
    objects = [obj for src in model["sources"] for obj in src["objects"]]
    if any(obj["object_kind"] not in ("table", "view") for obj in objects):
        raise ValueError("unsupported source object kind")
    return {
        "objects": len(objects),
        "tables": sum(obj["object_kind"] == "table" for obj in objects),
        "views": sum(obj["object_kind"] == "view" for obj in objects),
        "fields": sum(len(obj["fields"]) for obj in objects),
        "table_rows": sum(obj["count"] for obj in objects if obj["object_kind"] == "table"),
        "result_rows": sum(obj["count"] for obj in objects),
        "values": sum(obj["count"] * len(obj["fields"]) for obj in objects),
    }


def _values(model, snapshot, pool):
    for page in snapshot["chunks"]:
        columns = []
        for identity in page:
            segment = model["segments"][identity]
            data = gzip.decompress(base64.b64decode(segment["data"], validate=True))
            if len(data) % 4:
                raise ValueError("source segment has incomplete uint32 codes")
            count = len(data) // 4
            if segment["codec"] != "u32le":
                data = bytes(data[byte * count + row] for row in range(count) for byte in range(4))
            codes = list(struct.unpack("<" + "I" * count, data))
            if segment["codec"] == "delta-byteplane":
                for row in range(1, count):
                    codes[row] = (codes[row] + codes[row - 1]) & 0xFFFFFFFF
            raw = struct.pack("<" + "I" * count, *codes)
            if hashlib.sha256(raw).hexdigest() != identity:
                raise ValueError("source segment content differs from its identity")
            columns.append([pool[code] for code in codes])
        yield from zip(*columns, strict=True)


def _value(value):
    if not isinstance(value, dict):
        return value
    if "$binary" in value:
        raw = base64.b64decode(value["$binary"], validate=True)
        if len(raw) != value["size"] or hashlib.sha256(raw).hexdigest() != value["sha256"]:
            raise ValueError("binary value differs from its size/hash")
        return raw
    if "$integer" in value:
        return int(value["$integer"])
    if "$float" in value:
        return float(value["$float"])
    raise ValueError("unknown source wire value")


def audit_sqlite(model: dict, path: Path) -> dict:
    """Compare all objects, columns, rows and typed values; never write the DB."""
    expected = coverage(model)
    if len(model["sources"]) != 1:
        raise ValueError("--source requires a single-source baseline")
    source = model["sources"][0]
    pool = json.loads(gzip.decompress(base64.b64decode(model["dictionaries"][source["id"]])))
    before = digest(path)
    def quote(name):
        return '"' + name.replace('"', '""') + '"'
    rows = values = binary_values = 0
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only = ON")
        conn.execute("BEGIN")
        actual = dict(conn.execute(
            "SELECT name, type FROM sqlite_master "
            "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'"
        ))
        objects = source["objects"]
        if actual != {obj["name"]: obj["object_kind"] for obj in objects}:
            raise ValueError("source object inventory differs from raw database")
        for obj in objects:
            snap = model["snapshots"][obj["id"]]
            columns = [row[1] for row in conn.execute(
                "PRAGMA table_xinfo(" + quote(obj["name"]) + ")"
            ) if row[6] != 1]
            if columns != snap["columns"]:
                raise ValueError(f"{obj['name']}: source field inventory differs")
            query = "SELECT " + ",".join(map(quote, columns)) + " FROM " + quote(obj["name"])
            if snap["keys"]:
                query += " ORDER BY " + ",".join(map(quote, snap["keys"]))
            cursor = conn.execute(query)
            count = 0
            for exported in _values(model, snap, pool):
                raw = cursor.fetchone()
                if raw is None:
                    raise ValueError(f"{obj['name']}: extra snapshot row {count}")
                for column, left, encoded in zip(columns, raw, exported, strict=True):
                    right = _value(encoded)
                    same = type(left) is type(right) and left == right
                    if same and isinstance(left, float):
                        same = struct.pack("<d", left) == struct.pack("<d", right)
                    if not same:
                        raise ValueError(f"{obj['name']}.{column}: value differs at row {count}")
                    values += 1
                    binary_values += isinstance(left, bytes)
                count += 1
            if cursor.fetchone() is not None or count != obj["count"]:
                raise ValueError(f"{obj['name']}: record count differs")
            rows += count
    finally:
        conn.close()
    if digest(path) != before:
        raise ValueError("source file changed during audit")
    if rows != expected["result_rows"] or values != expected["values"]:
        raise ValueError("audit totals differ from source manifest")
    return {**expected, "binary_values": binary_values, "source_sha256": before}


def check(path: Path, *, source: Path | None = None) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest["format"] != FORMAT:
        raise ValueError("unsupported baseline format")
    locked = set()
    parent = path.resolve().parent
    for item in manifest["files"]:
        target = (parent / item["path"]).resolve()
        if not target.is_relative_to(parent) or item["path"] in locked:
            raise ValueError("duplicate or escaping baseline file path")
        locked.add(item["path"])
        if target.stat().st_size != item["bytes"] or digest(target) != item["sha256"]:
            raise ValueError(f"{item['path']}: frozen file size/hash differs")
    if manifest["artifact"] not in locked:
        raise ValueError("artifact is not locked by baseline manifest")
    b = bundle(parent / manifest["artifact"])
    if (
        "renderer" in manifest
        and b.get("ui", {}).get("language") != manifest["renderer"]["language"]
    ):
        raise ValueError("export language differs from baseline declaration")
    if b["projection"]["mode"] != "source_projection" or not b["projection"]["source_read_only"]:
        raise ValueError("baseline must be a read-only phase-one projection")
    if b["projection"]["generated_at"] != manifest["projection_generated_at"]:
        raise ValueError("snapshot extraction time differs from manifest")
    found = coverage(b["source_schema"])
    if found != manifest["coverage"]:
        raise ValueError("coverage declaration differs from artifact")
    result = {"manifest": str(path), "coverage": found, "frozen_files": len(locked)}
    if source is not None:
        if digest(source) != manifest["source"]["sha256"]:
            raise ValueError("source file hash differs from pinned baseline")
        result["source_audit"] = audit_sqlite(b["source_schema"], source)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="*", type=Path)
    parser.add_argument("--source", type=Path, help="read-only SQLite file for one baseline")
    args = parser.parse_args(argv)
    paths = args.manifests or sorted((ROOT / "examples").rglob("baseline.json"))
    if not paths or (args.source is not None and len(paths) != 1):
        print("FAIL: provide one baseline with --source; empty checks are refused", file=sys.stderr)
        return 1
    failed = False
    for path in paths:
        try:
            print(json.dumps(check(path, source=args.source), ensure_ascii=False))
        except (OSError, ValueError, KeyError, TypeError, IndexError, sqlite3.Error) as exc:
            print(f"FAIL {path}: {exc}", file=sys.stderr)
            failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
