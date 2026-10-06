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

import copy
import os
import sqlite3
from dataclasses import replace
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from . import expr
from .dependencies import validate_names
from .query import Builder, NotPushable, compile_query, quote

if TYPE_CHECKING:
    # Only ever an annotation here, and `spec` imports this module to bind at
    # load time. Importing it for real would make that a cycle and force every
    # function in this file to import lazily — which is how the lazy imports got
    # here in the first place. Kept behind TYPE_CHECKING so the dependency runs
    # one way: spec reaches for bind, bind never reaches back.
    from .spec import Spec

#: Rows loaded into memory for one type before this refuses. Aggregates are
#: evaluated in Python today, so a table of half a million rows would not be
#: slow so much as untenable — and discovering that as a hang teaches nothing.
#: The number is a statement about what is built, not about what is reasonable:
#: pushing aggregates down to SQL removes it entirely.
MAX_ROWS = 50_000


class BindingError(Exception):
    """The spec says something about the source that the source does not say."""


class SourceUnavailable(BindingError):
    """The spec is fine; the data it reads is not reachable from this machine.

    Kept apart from every other binding failure because it is the one that is
    nobody's mistake. A spec bound to a customer's warehouse is correct on a
    laptop that cannot see the warehouse, and a CI runner that has no copy of a
    23 MB database is not evidence of a bug. Callers that need to skip rather
    than fail — CI, the README check — branch on this type.

    It is a type and not a phrase for a plain reason: both of those callers used
    to match the substring "no database at", so the message could not be
    reworded without silently turning their skips into failures. A condition two
    tools have to agree about is an object, not prose.
    """


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
        raise SourceUnavailable(f"no database at {path}")
    uri = "file:" + path.replace("\\", "/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.create_function('sg_round', 2, expr.money_round, deterministic=True)
    conn.create_function('sg_div', 2, expr.divide, deterministic=True)
    for op, name in [('+', 'add'), ('-', 'sub'), ('*', 'mul'), ('/', 'div')]:
        def decimal_op(a, b, operator=op):
            result = expr.decimal_binary(operator, a, b)
            return None if result is None else str(result)
        conn.create_function(f'sg_decimal_{name}', 2, decimal_op, deterministic=True)
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
            except SourceUnavailable:
                # Not a broken claim, so not collected as one: the spec may be
                # entirely right and simply be somewhere the data is not. Let it
                # out, so the caller decides between skipping and stopping.
                raise
            except BindingError as e:
                out.append(f"type {tname}: {e}")
                continue
            conn = conns[dsn]

            table = b["table"]
            cols = _columns(conn, table)
            if not cols:
                out.append(f"type {tname}: {b['from']} has no table {table!r}")
                continue
            if b.get('where'):
                physical = SimpleNamespace(types={table: {'props': {c: {} for c in cols}}},
                                           nodes={}, raw={}, hooks={}, links_of=lambda _: {})
                try:
                    validate_names(physical, expr.parse(b['where']), table)
                except expr.ExprError as error:
                    out.append(f'type {tname}: invalid source filter: {error}')
                    continue

            for pname in (t.get("props") or {}):
                definition = t["props"][pname]
                if "op" in definition:
                    continue
                if s.owner_of(tname, pname) != "source":
                    out.append(
                        f"type {tname}.{pname}: a stored ontology-owned decision has no "
                        "backing store here. Use a related ontology-owned type for decisions, "
                        "or an 'op' for a calculated property; do not add a source column"
                    )
                    continue
                col = s.column_of(tname, pname)
                if col not in cols:
                    out.append(
                        f"type {tname}.{pname}: {table!r} has no column {col!r}"
                    )
                    continue
                condition = f"({b['where']}) AND " if b.get("where") else ""
                if not definition.get("nullable"):
                    nulls = conn.execute(
                        f'SELECT count(*) FROM {quote(table)} WHERE {condition}'
                        f'{quote(col)} IS NULL'
                    ).fetchone()[0]
                    if nulls:
                        out.append(
                            f"type {tname}.{pname}: {nulls} source row(s) are null, but "
                            "the property is not nullable. Declare nullable and what "
                            "absence means, or correct the binding"
                        )
                if definition.get("type") == "enum":
                    values = definition["values"]
                    placeholders = ','.join('?' for _ in values)
                    bad = conn.execute(
                        f'SELECT DISTINCT {quote(col)} FROM {quote(table)} WHERE {condition}'
                        f'{quote(col)} IS NOT NULL AND '
                        f'{quote(col)} NOT IN ({placeholders}) LIMIT 5',
                        values,
                    ).fetchall()
                    if bad:
                        out.append(f"type {tname}.{pname}: source values "
                                   f"{[r[0] for r in bad]} are not in the declared enum")
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
            if idp and s.column_of(tname, idp) in cols:
                for bad in _not_unique(conn, table, [s.column_of(tname, idp)], b):
                    out.append(
                        f"type {tname}: id {idp!r} names more than one row — "
                        f"{bad} value(s) are shared. The key declares "
                        f"{b.get('key')}, so no single property identifies a row "
                        f"here; omit id to use the full backing.key, or narrow the "
                        f"type with backing.where"
                    )
            key = b.get("key") or []
            if key and all(k in cols for k in key):
                condition = f"({b['where']}) AND " if b.get("where") else ""
                null_key = ' OR '.join(f'{quote(k)} IS NULL' for k in key)
                if conn.execute(f'SELECT 1 FROM {quote(table)} WHERE {condition}'
                                f'({null_key}) LIMIT 1').fetchone():
                    out.append(f"type {tname}: key {key} contains null; a row needs an identity")
                for dupes in _not_unique(conn, table, key, b):
                    out.append(
                        f"type {tname}: key {key} is not unique in {table} — "
                        f"{dupes} value(s) name more than one row"
                    )
        for hname, hook in s.hooks.items():
            owner = str(hook.get('owner') or '')
            if '/' not in owner:
                continue
            tname, identity = owner.split('/', 1)
            b = s.backing_of(tname)
            if not b or b['from'] not in s.raw:
                continue
            dsn = s.raw[b['from']]['dsn']
            conn = conns.get(dsn)
            if conn is None or not _columns(conn, b['table']):
                continue
            cols = [s.column_of(tname, p) for p in s.id_props(tname)]
            key_sql = " || '·' || ".join(f'CAST({quote(c)} AS TEXT)' for c in cols)
            condition = f"({b['where']}) AND " if b.get('where') else ''
            if not conn.execute(f'SELECT 1 FROM {quote(b["table"])} WHERE {condition}'
                                f'({key_sql}) = ? LIMIT 1', [identity]).fetchone():
                out.append(f"hook {hname}: no {tname} with id {identity!r} in its source binding")
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
    props = [p for p, d in (s.types[tname].get("props") or {}).items() if "op" not in d]
    cols = {pn: s.column_of(tname, pn) for pn in props}
    select = ", ".join(f'"{c}" as "{p}"' for p, c in cols.items())
    where = f" where {b['where']}" if b.get("where") else ""
    with connect(raw["dsn"], base) as conn:
        rows = conn.execute(f'select {select} from "{b["table"]}"{where}').fetchall()
    return [dict(r) for r in rows]


def scoped(s: Spec, scope: dict) -> Spec:
    """Apply an operator-registered scope to bindings and inline reference rows.

    Called only by the data owner's loader. Caller-selected display coordinates
    do not grant access, and types without the axis remain shared reference data.
    """
    if set(scope) - set(s.dimensions):
        raise ValueError("registered view has an unknown dimension")
    s = copy.deepcopy(s)
    for tn in s.types:
        axes = [(s.axis_of(tn, dim), value) for dim, value in scope.items()]
        axes = [(prop, value) for prop, value in axes if prop]
        if tn in s.instances:
            s.instances[tn] = [r for r in s.instances[tn]
                               if all(r.get(prop) == value for prop, value in axes)]
        backing = s.backing_of(tn)
        if backing and axes:
            clauses = [expr.to_sql(expr.Bin("=", expr.Ref(s.column_of(tn, prop)), expr.Lit(value)))
                       for prop, value in axes]
            previous = [f"({backing['where']})"] if backing.get("where") else []
            backing["where"] = " AND ".join([*previous, *clauses])
    return s


def bind_all(s: Spec, base: str = ".") -> Spec:
    """A spec whose backed types carry their rows — except the ones too large.

    A type bigger than memory is not an error and must not become one: the
    aggregate over it is answerable by the database, and that is what most of a
    graph asks for. So it is left unloaded with its row count, and only the
    things that genuinely need rows — showing them, computing per row — have to
    say they cannot.
    """

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


def answerer(s: Spec, at: dict | None = None, basis: str | None = None):
    """A way to hand an aggregate to the database, for the evaluator to try first.

    `at` travels with it because the slice must reach the query. Built without
    it, every pushable figure silently reports the whole book while the rows
    beside it are filtered — and which figures do that depends on whether their
    filter happened to be translatable, so two numbers on one graph disagree
    for no reason a reader can see.
    """

    if not any(s.backing_of(t) for t in s.types):
        return None

    def answer(node: Any, scope: dict | None = None) -> Any:
        try:
            return aggregate(s, node, s.source_base, at, basis=basis, scope=scope)
        except NotPushable as error:
            # Only legitimate when the rows are here to do it the other way.
            if node.type_name in s.unloaded:
                raise expr.ExprError(
                    f"{node.type_name} holds {s.unloaded[node.type_name]} rows, too many "
                    f"to work through here, and this aggregate cannot be handed to the "
                    f"database. Narrow the type with backing.where, or express it so the "
                    f"query can answer it. Reason: {error}"
                ) from None
            return expr.DECLINED

    return answer

def aggregate(s: Spec, node: Any, base: str = ".", at: dict | None = None,
              *, basis: str | None = None, scope: dict | None = None) -> Any:
    """Execute a checked, parameterised aggregate without fetching its rows."""
    query = compile_query(s, node, at=at, basis=basis, scope=scope)
    with connect(query.dsn, base) as conn:
        try:
            return conn.execute(query.sql, query.params).fetchone()[0]
        except sqlite3.Error as e:
            raise expr.ExprError(f"source query failed: {e}; expression: {node}") from e


def link_evidence(s: Spec, tname: str, prop: str, at=None) -> dict:
    """Count and sample dangling refs in the source, including unfetched tables."""
    builder = Builder(s, dict(at or {}))
    joins = []
    row = builder.row(tname, joins)
    target = s.links_of(tname)[prop]
    ids = s.id_props(target)
    if len(ids) != 1:
        raise expr.ExprError(f"{tname}.{prop}: a scalar ref cannot name a composite identity")
    target_key = row.path((prop, ids[0]))
    source_key = row.property(prop)
    bad = f"({source_key} IS NOT NULL AND {target_key} IS NULL)"
    clauses = row.filters()
    base_sql = f"FROM {row.source()} {' '.join(joins)}"
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    with connect(builder.dsn, s.source_base) as conn:
        result = conn.execute(
            f"SELECT count(*), count({source_key}), COALESCE(sum({bad}), 0) {base_sql}{where}",
            builder.params,
        ).fetchone()
        columns = ','.join(row.property(p) for p in s.id_props(tname))
        sample_where = ' WHERE ' + ' AND '.join([*clauses, bad])
        sample = conn.execute(f"SELECT {columns} {base_sql}{sample_where} LIMIT 5",
                              builder.params).fetchall() if result[2] else []
    return {'total': result[0], 'linked': result[1], 'affected': result[2],
            'sample': [r[0] if len(r) == 1 else '·'.join(str(x) for x in r) for r in sample]}
