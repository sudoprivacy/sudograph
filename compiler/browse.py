"""Bounded record browsing and portable, compressed drill-down pages."""

from __future__ import annotations

import base64
import gzip
import json

from . import bind
from .query import Builder

PAGE_SIZE = 100


def page(s, tname, *, offset=0, limit=PAGE_SIZE, where=None, basis=None, at=None):
    if tname not in s.types or not 1 <= limit <= 500 or offset < 0:
        raise ValueError("unknown type or invalid page range (limit 1..500, offset >= 0)")
    props = s.types[tname]["props"]
    where = where or {}
    if set(where) - set(props):
        raise ValueError("record filter names an unknown property")
    if not s.backing_of(tname):
        rows = [
            r for r in s.instances.get(tname, []) if all(r.get(p) == v for p, v in where.items())
        ]
        return {"offset": offset, "total": len(rows), "rows": rows[offset : offset + limit]}
    b = Builder(s, dict(at or {}), basis=basis)
    joins = []
    row = b.row(tname, joins)
    columns = list(props)
    select = ",".join(row.property(p) for p in columns)
    filters = [
        *row.filters(),
        *(f"{row.property(p)} IS {b.parameter(v)}" for p, v in where.items()),
    ]
    tail = " WHERE " + " AND ".join(filters) if filters else ""
    order = ",".join(row.property(p) for p in s.id_props(tname))
    source = f"FROM {row.source()} {' '.join(joins)}{tail}"
    with bind.connect(b.dsn, s.source_base) as conn:
        total = conn.execute("SELECT count(*) " + source, b.params).fetchone()[0]
        data = conn.execute(
            f"SELECT {select} {source} ORDER BY {order} LIMIT :limit OFFSET :offset",
            {**b.params, "limit": limit, "offset": offset},
        ).fetchall()
    return {
        "offset": offset,
        "total": total,
        "rows": [dict(zip(columns, r, strict=True)) for r in data],
    }


def snapshot(s, *, chunk_size=1000):
    """Stream source once, decode one chunk in the UI; never materialise a huge graph.

    A portable export contains all authorised records, not an access-control boundary.
    Permission-sensitive delivery must use Gateway, whose views are separate resources.
    """
    result = {}
    for tn, t in s.types.items():
        props = list(t["props"])
        chunks = []
        keys = []

        def add(rows, keys=keys, tn=tn, props=props, chunks=chunks):
            if not rows:
                return
            keys.append([s.identify(tn, dict(zip(props, r, strict=True))) for r in rows])
            payload = json.dumps(
                [list(r) for r in rows], ensure_ascii=False, separators=(",", ":")
            ).encode()
            chunks.append(base64.b64encode(gzip.compress(payload, mtime=0)).decode())

        if s.backing_of(tn):
            b = Builder(s)
            joins = []
            row = b.row(tn, joins)
            select = ",".join(row.property(p) for p in props)
            order = ",".join(row.property(p) for p in s.id_props(tn))
            filters = row.filters()
            tail = " WHERE " + " AND ".join(filters) if filters else ""
            sql = f"SELECT {select} FROM {row.source()} {' '.join(joins)}{tail} ORDER BY {order}"
            with bind.connect(b.dsn, s.source_base) as conn:
                cur = conn.execute(sql, b.params)
                while rows := cur.fetchmany(chunk_size):
                    add(rows)
        else:
            rows = s.instances.get(tn, [])
            for start in range(0, len(rows), chunk_size):
                add([[r.get(p) for p in props] for r in rows[start : start + chunk_size]])
        # Keys are compressed too. Used for reference navigation without reading facts.
        index = base64.b64encode(
            gzip.compress(
                json.dumps(keys, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0
            )
        ).decode()
        result[tn] = {
            "columns": props,
            "chunks": chunks,
            "chunk_size": chunk_size,
            "index": index,
            "display": t.get("display"),
            "ids": s.id_props(tn),
            "refs": s.links_of(tn),
        }
    return result
