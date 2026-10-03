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


def _not_unique(conn, table: str, columns: list[str], backing: dict) -> list[int]:
    """How many values of these columns name more than one row; empty if none.

    A list rather than a count so callers read as "for each problem", and a
    claim about rows is settled by looking at rows.
    """
    quoted = ", ".join(f'"{c}" ' for c in columns).replace(" ,", ",")
    where = f" where {backing['where']}" if backing.get("where") else ""
    n = conn.execute(
        f"select count(*) from (select {quoted} from \"{table}\"{where} "
        f"group by {quoted} having count(*) > 1)"
    ).fetchone()[0]
    return [n] if n else []


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

            # `id` is what every row-level statement is addressed to — the node
            # on the canvas, the target of a link, the thing a comment anchors
            # to. A non-unique one does not fail: rows quietly collapse onto one
            # another and the graph draws four rows as two, which is worse than
            # an error because it looks like an answer. Checked against the data
            # for the same reason the key is: it is a claim about rows.
            idp = t.get("id")
            if idp and idp in (t.get("props") or {}):
                for bad in _not_unique(conn, table, [s.column_of(tname, idp)], b):
                    out.append(
                        f"type {tname}: id {idp!r} names more than one row — "
                        f"{bad} value(s) are shared. The key declares "
                        f"{b.get('key')}, so no single property identifies a row "
                        f"here; narrow the type with backing.where, or bind one "
                        f"whose rows an id can name"
                    )
            key = b.get("key") or []
            if key and all(k in cols for k in key):
                for dupes in _not_unique(conn, table, key, b):
                    out.append(
                        f"type {tname}: key {key} is not unique in {table} — "
                        f"{dupes} value(s) name more than one row"
                    )
    finally:
        for c in conns.values():
            c.close()
    return out


def count(s: Spec, tname: str, base: str = ".") -> int:
    """How many rows this type has, without fetching any of them."""
    b = s.backing_of(tname)
    raw = s.raw[b["from"]]
    where = f" where {b['where']}" if b.get("where") else ""
    with connect(raw["dsn"], base) as conn:
        return conn.execute(f'select count(*) from "{b["table"]}"{where}').fetchone()[0]


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
        rows = conn.execute(f'select {select} from "{b["table"]}"{where}').fetchall()
    return [dict(r) for r in rows]


def bind_all(s: Spec, base: str = ".") -> Spec:
    """A spec whose backed types carry their rows — except the ones too large.

    A type bigger than memory is not an error and must not become one: the
    aggregate over it is answerable by the database, and that is what most of a
    graph asks for. So it is left unloaded with its row count, and only the
    things that genuinely need rows — showing them, computing per row — have to
    say they cannot.
    """
    from dataclasses import replace

    rows: dict[str, list[dict]] = {}
    unloaded: dict[str, int] = {}
    for t in s.types:
        if not s.backing_of(t):
            continue
        n = count(s, t, base)
        if n > MAX_ROWS:
            unloaded[t] = n
        else:
            rows[t] = load(s, t, base)
    if not rows and not unloaded:
        return s
    return replace(
        s, instances={**s.instances, **rows}, unloaded=unloaded, source_base=base
    )


def answerer(s: Spec, at: dict | None = None):
    """A way to hand an aggregate to the database, for the evaluator to try first.

    `at` travels with it because the slice must reach the query. Built without
    it, every pushable figure silently reports the whole book while the rows
    beside it are filtered — and which figures do that depends on whether their
    filter happened to be translatable, so two numbers on one graph disagree
    for no reason a reader can see.
    """
    from . import expr

    if not any(s.backing_of(t) for t in s.types):
        return None

    def answer(node: Any) -> Any:
        try:
            return aggregate(s, node, s.source_base, at)
        except NotPushable:
            # Only legitimate when the rows are here to do it the other way.
            if node.type_name in s.unloaded:
                raise BindingError(
                    f"{node.type_name} holds {s.unloaded[node.type_name]} rows, too many "
                    f"to work through here, and this aggregate cannot be handed to the "
                    f"database. Narrow the type with backing.where, or express it so the "
                    f"query can answer it"
                ) from None
            return expr.DECLINED

    return answer

#: Operators that mean the same thing in our expressions and in SQL. Translated
#: rather than passed through: the subset is small enough to enumerate, and
#: enumerating it is what keeps a spec from reaching the database with anything
#: the compiler has not understood first.
_SQL_OPS = {
    "=": "=", "<>": "<>", "!=": "<>", "<": "<", ">": ">", "<=": "<=", ">=": ">=",
    "+": "+", "-": "-", "*": "*", "/": "/",
    "and": "AND", "or": "OR",
}


class NotPushable(Exception):
    """This expression cannot be answered by the database alone."""


def _sql(node: Any, col: Any, params: list) -> str:
    """One expression, translated. Raises when any part of it has no translation.

    Never interpolated: every literal becomes a bound parameter, so a value in a
    spec cannot become syntax in a query. The spec is written by an agent, and
    the one thing that must not be possible is for what it writes to be executed
    as something other than a value.
    """
    from . import expr

    if isinstance(node, expr.Lit):
        params.append(node.value)
        return "?"
    if isinstance(node, expr.Ref):
        return f'"{col(node.name)}"'
    if isinstance(node, expr.Not):
        return f"(NOT {_sql(node.operand, col, params)})"
    if isinstance(node, expr.Neg):
        return f"(-{_sql(node.operand, col, params)})"
    if isinstance(node, expr.IsNull):
        tail = "IS NOT NULL" if node.negated else "IS NULL"
        return f"({_sql(node.operand, col, params)} {tail})"
    if isinstance(node, expr.Bin):
        op = _SQL_OPS.get(node.op)
        if not op:
            raise NotPushable(f"no translation for {node.op!r}")
        return f"({_sql(node.left, col, params)} {op} {_sql(node.right, col, params)})"
    raise NotPushable(f"no translation for {type(node).__name__}")


def aggregate(s: Spec, node: Any, base: str = ".", at: dict | None = None) -> Any:
    """Answer one aggregate from the database, or raise NotPushable.

    This is what lets a type be larger than memory. The expression language
    already says exactly one aggregate over exactly one type with an optional
    filter — which is a SELECT — so the translation is a rename of columns and
    nothing more. Anything the subset does not cover raises rather than being
    approximated.

    `at` is the slice in force, and it is not optional for correctness: the
    rows in memory are filtered by it elsewhere, so a query that ignored it
    would put a whole-book figure on a graph whose rows are one market's. The
    headline would read 330 above two rows adding to 30, under a heading saying
    which market — one number meaning two things, which is the single thing
    this project is built to prevent.
    """
    tname = node.type_name
    b = s.backing_of(tname)
    if not b:
        raise NotPushable(f"{tname} is not backed by a table")

    props = (s.types[tname].get("props") or {})

    def col(name: str) -> str:
        p = props.get(name)
        if p is None:
            raise NotPushable(f"{name!r} is not a property of {tname}")
        if "op" in p:
            # Computed here, so the database has never heard of it.
            raise NotPushable(f"{tname}.{name} is computed, not stored")
        return s.column_of(tname, name)

    params: list = []
    where = b.get("where")
    clauses = [f"({where})"] if where else []
    if node.where is not None:
        clauses.append(_sql(node.where, col, params))
    # The slice, in the same WHERE the rows would have been filtered by. A type
    # that declares none of the dimensions is reference data and stays whole,
    # exactly as _restrict leaves it.
    for dim, value in (at or {}).items():
        axis = s.axis_of(tname, dim)
        if not axis:
            continue
        clauses.append(f'"{col(axis)}" = ?')
        params.append(value)
    tail = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    if node.func == "count":
        head = "count(*)" if node.prop in (None, "*") else f'count("{col(node.prop)}")'
    elif node.func == "sum":
        head = f'sum("{col(node.prop)}")'
    else:
        raise NotPushable(f"no translation for {node.func}()")

    raw = s.raw[b["from"]]
    with connect(raw["dsn"], base) as conn:
        row = conn.execute(
            f'select {head} from "{b["table"]}"{tail}', params
        ).fetchone()
    value = row[0]
    # `sum` over no rows is NULL in SQL and 0 in the row-by-row evaluator; the
    # two must not disagree about an empty set or a figure would change meaning
    # with the size of its input.
    return 0 if value is None and node.func == "sum" else value
