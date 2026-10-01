"""Read a type's rows from the table it is a view over, and prove the view holds.

A binding is a claim about someone else's database: this table carries that
business object, these columns identify one of its rows, that column is behind
this property. Every one of those can stop being true without anyone touching
the spec — a column gets renamed, a table is replaced by a view, a key stops
being unique.

So the binding is **compared against the live schema** rather than trusted. That
comparison is the whole difference between a binding and a copy: a copy drifts
silently, a binding fails loud. Nothing here writes down what the database
already answers — column types, indexes, which foreign keys exist — because a
fact held in two places is a fact that can disagree with itself. What the spec
holds is what the database cannot say: which table is this object, which columns
name a row of it, which rows belong to it at all.

Read-only by construction: the connection is opened in SQLite's read-only mode,
so a spec cannot write to a source system even by accident.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any

from .spec import Spec

#: Rows loaded into memory for one type before this refuses. Aggregates are
#: evaluated in Python today, so a table of half a million rows would not be
#: slow so much as untenable — and discovering that as a hang teaches nothing.
#: The number is a statement about what is built, not about what is reasonable:
#: pushing aggregates down to SQL removes it entirely.
MAX_ROWS = 50_000


class BindingError(Exception):
    """The spec says something about the source that the source does not say."""


def _path_of(dsn: str, base: str) -> str:
    """`sqlite:///<path>`, where the path may be relative to the spec.

    Relative is the useful case and the one easy to get wrong: a spec and the
    database it reads travel together, so the spec says where the database is
    *from itself*, not from whichever directory the compiler was run in.
    """
    if not dsn.startswith("sqlite:"):
        raise BindingError(f"only sqlite dsns are supported yet, got {dsn!r}")
    raw = dsn.split("sqlite://", 1)[1].lstrip("/")
    return raw if os.path.isabs(raw) else os.path.normpath(os.path.join(base, raw))


def connect(dsn: str, base: str = ".") -> sqlite3.Connection:
    """Open the source read-only, so a mistake cannot become a write."""
    path = _path_of(dsn, base)
    if not os.path.exists(path):
        raise BindingError(f"no database at {path}")
    uri = "file:" + path.replace("\\", "/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> dict[str, str]:
    rows = conn.execute(f'pragma table_info("{table}")').fetchall()
    return {r["name"]: (r["type"] or "").upper() for r in rows}


#: What a declared property type will accept from a column. Deliberately loose:
#: the check is for a binding pointed at the wrong column, not for a type system
#: SQLite does not have — it stores what it is given regardless of the declared
#: affinity, so a strict rule here would reject working specs.
_COMPATIBLE = {
    "money": ("INT", "REAL", "NUM", "DEC", "DOUB", "FLOA"),
    "number": ("INT", "REAL", "NUM", "DEC", "DOUB", "FLOA"),
}


def verify(s: Spec, base: str = ".") -> list[str]:
    """Compare every binding against the schema it claims. Empty means it holds."""
    out: list[str] = []
    conns: dict[str, sqlite3.Connection] = {}
    try:
        for tname, t in s.types.items():
            b = s.backing_of(tname)
            if not b:
                continue
            raw = s.raw.get(b["from"]) or {}
            dsn = raw.get("dsn")
            try:
                if dsn not in conns:
                    conns[dsn] = connect(dsn, base)
            except BindingError as e:
                out.append(f"type {tname}: {e}")
                continue
            conn = conns[dsn]

            table = b["table"]
            cols = _columns(conn, table)
            if not cols:
                out.append(f"type {tname}: {b['from']} has no table {table!r}")
                continue

            for pname in (t.get("props") or {}):
                col = s.column_of(tname, pname)
                if col not in cols:
                    out.append(
                        f"type {tname}.{pname}: {table!r} has no column {col!r}"
                    )
                    continue
                want = _COMPATIBLE.get((t["props"][pname] or {}).get("type"))
                if want and cols[col] and not any(k in cols[col] for k in want):
                    out.append(
                        f"type {tname}.{pname} is declared as a number but "
                        f"{table}.{col} is {cols[col]} — one of the two is wrong "
                        f"about what this column holds"
                    )

            # A key that does not identify a row makes every row-level statement
            # about this type ambiguous, so it is checked against the data rather
            # than assumed from the declaration.
            key = b.get("key") or []
            if key and all(k in cols for k in key):
                quoted = ", ".join(f'"{k}"' for k in key)
                where = f" where {b['where']}" if b.get("where") else ""
                dupes = conn.execute(
                    f'select count(*) from (select {quoted} from "{table}"{where} '
                    f"group by {quoted} having count(*) > 1)"
                ).fetchone()[0]
                if dupes:
                    out.append(
                        f"type {tname}: key {key} is not unique in {table} — "
                        f"{dupes} value(s) name more than one row"
                    )
    finally:
        for c in conns.values():
            c.close()
    return out


def load(s: Spec, tname: str, base: str = ".") -> list[dict]:
    """The rows of one backed type, under the ontology's own property names."""
    b = s.backing_of(tname)
    if not b:
        return list(s.instances.get(tname) or [])
    raw = s.raw[b["from"]]
    props = list((s.types[tname].get("props") or {}))
    cols = {pn: s.column_of(tname, pn) for pn in props}
    select = ", ".join(f'"{c}" as "{p}"' for p, c in cols.items())
    where = f" where {b['where']}" if b.get("where") else ""
    with connect(raw["dsn"], base) as conn:
        n = conn.execute(f'select count(*) from "{b["table"]}"{where}').fetchone()[0]
        if n > MAX_ROWS:
            raise BindingError(
                f"type {tname} backs {n} rows of {b['table']}, over the {MAX_ROWS} "
                f"this can hold in memory. Aggregates are evaluated in Python today, "
                f"so narrow the type with backing.where — or push the aggregate into "
                f"the query, which removes this limit rather than raising it"
            )
        rows = conn.execute(f'select {select} from "{b["table"]}"{where}').fetchall()
    return [dict(r) for r in rows]


def bind_all(s: Spec, base: str = ".") -> Spec:
    """A spec whose backed types carry their rows, loaded from the source."""
    from dataclasses import replace

    backed = {t: load(s, t, base) for t in s.types if s.backing_of(t)}
    if not backed:
        return s
    return replace(s, instances={**s.instances, **backed})
