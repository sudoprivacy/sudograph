"""Compile a spec into values, checks, and a view model.

Three outputs, one pass, from the same source — that is the whole point. There is
no second reconciliation script: checking IS running the compiler.

Derived nodes are ordered by dependency, so a node may read another node's value.
A cycle is an error rather than a stack overflow, because a business graph with a
cycle is a modelling mistake someone has to see.

Folding, grouping and top-N live here, not in the spec: a layout need must never
reshape the truth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from . import expr
from . import lineage as lin_mod
from .spec import NODE_KINDS, Spec


@dataclass
class Check:
    """One statement about the ontology, with the evidence for it reachable.

    A check is per *column*, not per row. The row-by-row form printed the same
    sentence 32,587 times for one real table, which is not more information —
    it is one fact repeated until nobody reads any of it. But aggregating the
    report must not aggregate the evidence: a reviewer who cannot get to the
    rows cannot check anything, and "21 rows are missing" on its own is as
    useless as the 32,587 lines were.

    So three layers, cheapest first:

      * the statement — one line, the thing a person reasons about
      * `sample` — the first few offending rows, enough to look at one
      * everything else — a query, never stored. For a type of 609,283 rows it
        could not have been stored anyway, which is why this is the shape
        rather than a compromise.
    """

    name: str
    ok: bool
    detail: str = ""
    #: How many rows this statement is about, when it is about rows at all.
    affected: int = 0
    #: Identifiers of the first few, so the claim can be looked at rather than
    #: believed. Bounded on purpose — the rest is a query away.
    sample: list = field(default_factory=list)


@dataclass
class Compiled:
    ontology: str
    #: Where on the filter axes this compile sits: {"期间": "2023"}. A dimension
    #: divides the facts, so any number of them compose.
    at: dict[str, str] = field(default_factory=dict)
    #: Which complete reading of those facts. Never a dict: a basis does not
    #: divide anything, so there is only ever one in force. That asymmetry is
    #: the whole distinction between the two.
    basis: str | None = None
    values: dict[str, Any] = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)
    view: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)

    def summary(self) -> str:
        good = sum(1 for c in self.checks if c.ok)
        return f"{good}/{len(self.checks)} checks passed"


def _restrict(s: Spec, at: dict[str, str]) -> Spec:
    """A copy whose instances are only those at the given coordinates.

    A type is filtered only along the dimensions it declares. One that declares
    none is reference data — people, suppliers — and is left whole, because
    dropping it would break every row that points at it.
    """
    kept: dict[str, list[dict]] = {}
    for tname, rows in s.instances.items():
        # Only the dimensions this type is actually partitioned along apply.
        axes = [(s.axis_of(tname, d), want) for d, want in at.items()]
        axes = [(col, want) for col, want in axes if col is not None]
        kept[tname] = [r for r in rows if all(r.get(col) == want for col, want in axes)]
    # `replace`, never a field-by-field rebuild: a listed-out constructor drops
    # whatever was added to Spec since it was written, silently and with no way
    # to notice. It had already lost where the spec was read from, so a sliced
    # compile looked for the database in the wrong directory.
    return replace(s, instances=kept)


def _corroborate(s: Spec, c: Compiled) -> Spec:
    """Resolve each corroborated figure from its independent sources.

    A figure asserted by one system is a figure taken on trust. Audit evidence is
    two systems that do not talk to each other saying the same thing, so a
    corroborated property is written once per source and the compiler decides
    what it is worth:

      * they agree            -> that value, and the check passes
      * they disagree         -> the check fails unless the row cites a hook AND
                                 the spec says which source governs
      * too few of them spoke -> the check fails against `at_least`

    Declaring `prefer` is deliberately not enough on its own. A preference
    written once would otherwise bury every future disagreement behind it, which
    is the same silent absorption a plug without a `residual_to` commits.
    """
    if not any(s.corroborated(t) for t in s.instances):
        return s

    resolved: dict[str, list[dict]] = {}
    for tname, rows in s.instances.items():
        corr = s.corroborated(tname)
        if not corr:
            resolved[tname] = rows
            continue
        props = s.types[tname]["props"]
        idp = s.types[tname]["id"]
        gap_refs = [
            p for p, d in props.items() if d.get("type") == "ref" and d.get("to") == "hook"
        ]
        out_rows: list[dict] = []
        for row in rows:
            new = dict(row)
            for prop, sources in corr.items():
                rules = props[prop].get("corroboration") or {}
                spoke = {
                    src: row[f"{prop}@{src}"]
                    for src in sources
                    if row.get(f"{prop}@{src}") is not None
                }
                distinct = set(spoke.values())
                agree = len(distinct) <= 1
                enough = len(spoke) >= rules.get("at_least", 1)
                hooked = any(row.get(g) for g in gap_refs)
                prefer = rules.get("prefer")

                if agree:
                    new[prop] = next(iter(distinct)) if distinct else None
                elif hooked and prefer in spoke:
                    new[prop] = spoke[prefer]
                else:
                    new[prop] = None

                said = ", ".join(f"{k}={v}" for k, v in sorted(spoke.items()))
                if not agree and not hooked:
                    detail = f"{said} — they disagree and the row cites no hook"
                elif not agree and prefer not in spoke:
                    detail = (
                        f"{said} — they disagree; declare corroboration.prefer to say "
                        f"which source governs"
                    )
                elif not enough:
                    detail = (
                        f"corroborated by {len(spoke)} of {len(sources)} sources, "
                        f"needs {rules.get('at_least', 1)}"
                    )
                else:
                    detail = ""
                c.checks.append(
                    Check(f"corroboration/{tname}/{row.get(idp)}/{prop}", not detail, detail)
                )
            out_rows.append(new)
        resolved[tname] = out_rows

    return replace(s, instances=resolved)


#: How many offending rows a check carries with it. Enough to look at one and
#: see the shape of the problem; not so many that the report becomes the data.
SAMPLE = 5


def _absent_in_source(s: Spec, tname: str, col: str, idp: str) -> tuple[int, list]:
    """How many rows of an unfetched type lack this column, and a few of them.

    The same statement as for a fetched type, obtained the only way available
    when the rows are not here. That it is the same statement is the point: one
    rule, one shape of answer, two ways of arriving at it.
    """
    from . import bind as bind_mod

    b = s.backing_of(tname)
    raw = s.raw[b["from"]]
    column = s.column_of(tname, col)
    ident = s.column_of(tname, idp)
    where = f"({b['where']}) and " if b.get("where") else ""
    with bind_mod.connect(raw["dsn"], s.source_base) as conn:
        n = conn.execute(
            f'select count(*) from "{b["table"]}" where {where}"{column}" is null'
        ).fetchone()[0]
        rows = conn.execute(
            f'select "{ident}" from "{b["table"]}" where {where}"{column}" is null '
            f"limit {SAMPLE}"
        ).fetchall()
    return n, [r[0] for r in rows]


def _money_scale(value: Any, prop: dict) -> Any:
    """Round a computed money figure to the precision its type is kept in.

    A division produces fifteen decimals, and a money column that carries them
    is wrong in two ways at once: nobody writes an amount like that, and the sum
    of the displayed figures stops equalling the displayed sum. So the rounding
    is a property of the column, decided once, rather than something each
    expression remembers to do.

    Half-up, because that is what money conventions use and what the figures
    being replaced here were rounded by; Python's own round() is half-even and
    would disagree on exact halves. `scale` defaults to 0 — whole units — and a
    currency kept in cents declares `scale: 2`.
    """
    if prop.get("type") != "money" or not isinstance(value, (int, float)):
        return value
    scale = prop.get("scale", 0)
    q = Decimal(1).scaleb(-scale)
    rounded = Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP)
    return int(rounded) if scale == 0 else float(rounded)


def op_for(node: dict, basis: str | None) -> str | None:
    """The expression this node uses under `basis`.

    A basis-specific expression wins; otherwise the shared one applies. Writing
    only the expressions that genuinely differ is the point: everything else
    stays single-sourced and cannot drift between the two sets of figures.
    """
    if basis and f"op@{basis}" in node:
        return node[f"op@{basis}"]
    return node.get("op")


#: A vertex is either a scalar node — ("node", name) — or a computed column of
#: a type — ("prop", type, prop). They share one graph because they genuinely
#: depend on each other in both directions: a column may read a node (a rate
#: decided once and applied per row), and a node aggregates over columns that
#: may themselves be computed. Ordering them separately means guessing which
#: kind goes first, and the guess is wrong for any spec that does both.
def _order(s: Spec, basis: str | None = None) -> list[tuple]:
    """Topologically order everything with a value; raise on a cycle."""
    computed = {
        (t, pn)
        for t, tdef in s.types.items()
        for pn, pdef in (tdef.get("props") or {}).items()
        if "op" in pdef
    }
    by_type: dict[str, set[str]] = {}
    for t, pn in computed:
        by_type.setdefault(t, set()).add(pn)

    def of(src: str) -> tuple[set, set]:
        """(node deps, prop deps) of one expression."""
        ast = expr.parse(src or "0")
        names = expr.referenced_names(ast)
        nodes = {("node", n) for n in names & set(s.nodes)}
        props = set()
        # Whatever this aggregates over, it reads that type's computed columns.
        for t in expr.aggregated_types(ast):
            props |= {("prop", t, pn) for pn in by_type.get(t, ())}
        return nodes, props

    deps: dict[tuple, set] = {}
    for n, d in s.nodes.items():
        a, b = of(op_for(d, basis))
        deps[("node", n)] = a | b
    for t, pn in computed:
        pdef = s.types[t]["props"][pn]
        a, b = of(op_for(pdef, basis))
        # A sibling column of the same row is a dependency too.
        siblings = {
            ("prop", t, x)
            for x in expr.referenced_names(expr.parse(op_for(pdef, basis) or "0"))
            & by_type.get(t, set())
        }
        deps[("prop", t, pn)] = a | b | siblings
    derived = deps
    out: list[tuple] = []
    temp: set[tuple] = set()
    done: set[tuple] = set()

    def show(v: tuple) -> str:
        return v[1] if v[0] == "node" else f"{v[1]}.{v[2]}"

    def visit(n: tuple, trail: list[tuple]) -> None:
        if n in done:
            return
        if n in temp:
            raise ValueError(
                "cycle among computed values: "
                + " -> ".join(show(x) for x in [*trail, n])
            )
        temp.add(n)
        for d in sorted(deps[n]):
            visit(d, [*trail, n])
        temp.discard(n)
        done.add(n)
        out.append(n)

    for n in sorted(derived):
        visit(n, [])
    return out


def compile_spec(
    s: Spec,
    *,
    fold_over: int = 20,
    top_n: int = 5,
    at: dict[str, str] | None = None,
    basis: str | None = None,
) -> Compiled:
    """Compile, optionally restricted to one reporting period.

    Filtering happens before anything is computed, so every figure, check and
    bucket describes that period alone. The alternative — carrying a column per
    period on each node — makes the spec grow with time and makes "which period
    is this total" a question the reader has to keep answering.
    """
    # No implicit basis. A spec that holds the book figures and the restated
    # ones answers "how much was capitalised" twice, and a caller who did not
    # say which one they meant would get whichever the author happened to write
    # first. That is the one ambiguity a restatement cannot survive.
    if s.bases and basis is None:
        raise ValueError(
            f"{s.name} computes under a basis; pass one of {s.bases} — "
            f"the figures differ, so the answer is not defined without it"
        )
    if basis is not None and s.bases and basis not in s.bases:
        raise ValueError(f"unknown basis {basis!r}; the spec declares {s.bases}")

    at = dict(at or {})
    unknown = sorted(set(at) - set(s.dimensions))
    if unknown:
        raise ValueError(f"not declared dimensions: {unknown}; the spec declares {s.dimensions}")

    from . import bind as bind_mod

    c = Compiled(ontology=s.name, at=at, basis=basis)
    if at:
        s = _restrict(s, at)
    # Built after the slice is known and carrying it, because the database must
    # be asked the same question the rows are. Built before, every pushable
    # figure answered for the whole book while the rows beside it were filtered.
    agg = bind_mod.answerer(s, at)
    s = _corroborate(s, c)

    # Rows are copied before anything computes into them, so a compile never
    # writes back into the spec it was handed.
    work = {t: [dict(r) for r in rows] for t, rows in s.instances.items()}
    s = replace(s, instances=work)

    # ── values ────────────────────────────────────────────────────────
    for vertex in _order(s, basis):
        if vertex[0] == "node":
            name = vertex[1]
            src = op_for(s.nodes[name], basis)
            if not src:
                continue
            try:
                c.values[name] = expr.evaluate(
                    expr.parse(src), dict(c.values), s.instances, agg
                )
            except expr.ExprError as e:
                c.checks.append(Check(f"node/{name}", False, str(e)))
            continue

        # A computed column: one evaluation per row, with the row's own columns
        # in scope and `this` bound to its id, so an aggregate can say which
        # rows belong to it.
        _, tname, pname = vertex
        src = op_for(s.types[tname]["props"][pname], basis)
        idp = s.types[tname].get("id")
        for row in work.get(tname, []):
            scope = {**c.values, **row}
            if idp:
                scope["this"] = row.get(idp)
            try:
                row[pname] = _money_scale(
                    expr.evaluate(expr.parse(src), scope, s.instances, agg),
                    s.types[tname]["props"][pname],
                )
            except expr.ExprError as e:
                row[pname] = None
                c.checks.append(
                    Check(f"computed/{tname}/{row.get(idp)}/{pname}", False, str(e))
                )
            except TypeError:
                # An input this row does not have. The result is missing rather
                # than wrong, and the row's own gap is what says why — the same
                # rule a nullable column already lives under.
                row[pname] = None

    # ── articulation checks: the unit tier ────────────────────────────
    # Assertions the author wrote, evaluated over the node values this same
    # pass produced. There is no separate reconciliation script by design: if
    # the check ran against anything else, the two could disagree.
    for cname, spec_ in s.checks.items():
        src = spec_.get("expr") if isinstance(spec_, dict) else spec_
        # Presence of the key is what scopes a check, not its value: `期间:
        # null` means "only when no period is selected", which is a real scope
        # and not the absence of one. Testing the value would have let a
        # whole-ledger assertion run against a single period and fail there.
        want = spec_.get("at") if isinstance(spec_, dict) else None
        scoped = isinstance(want, dict) and any(at.get(d) != v for d, v in want.items())
        # A reading scopes a check too: "the books recognise no holdback" is true
        # under 账面 and false under 重述, and it is an assertion worth making
        # rather than one to leave out because it cannot be said everywhere.
        if isinstance(spec_, dict) and "basis" in spec_ and spec_["basis"] != basis:
            scoped = True
        if scoped:
            # A check scoped elsewhere is not asked here. Not asked is neither
            # pass nor fail: it is not counted, because a check that did not run
            # must never read as evidence.
            continue
        try:
            ok = bool(expr.evaluate(expr.parse(src), dict(c.values), s.instances, agg))
            detail = "" if ok else f"{src} is false"
        except expr.ExprError as e:
            ok, detail = False, str(e)
        c.checks.append(Check(f"articulation/{cname}", ok, detail))

    # ── checks ────────────────────────────────────────────────────────
    # Every source property must be reachable from some raw connector, or the
    # number on the graph has no provenance.
    for tname, t in s.types.items():
        for pname, p in (t.get("props") or {}).items():
            if p.get("owner") != "source":
                continue
            # Every declared source must own up to supplying it. A corroborated
            # figure whose second source never claimed to provide it is not
            # corroborated; it is one source and a hopeful entry in a list.
            #
            # A column reached through a backing is exempt, and not as a
            # convenience: `provides` is a hand-written list, and the binding is
            # compared against the live schema. Requiring both would mean
            # restating every column of every bound table by hand — the list
            # that goes stale, standing in front of the check that cannot.
            backed = bool(s.backing_of(tname))
            for src in s.sources_of(tname, pname):
                if backed and src == s.backing_of(tname).get("from"):
                    continue
                r = s.raw.get(src)
                declared = pname in (r.get("provides") or []) if r else False
                c.checks.append(
                    Check(
                        f"provenance/{tname}.{pname}@{src}",
                        declared,
                        "" if declared else f"raw {src!r} does not list it in 'provides'",
                    )
                )

    # An instance carrying a gap must point at a hook that exists, and that hook
    # must say what clears it. A gap with no exit is how a number goes stale.
    for tname, rows in s.instances.items():
        gap_props = [
            p
            for p, d in (s.types[tname].get("props") or {}).items()
            if d.get("type") == "ref" and d.get("to") == "hook"
        ]
        for row in rows:
            for gp in gap_props:
                ref = row.get(gp)
                if ref is None:
                    continue
                h = s.hooks.get(ref)
                c.checks.append(
                    Check(
                        f"gap/{tname}/{row.get(s.types[tname]['id'])}",
                        bool(h and h.get("resolve_when")),
                        "" if h else f"points at unknown hook {ref!r}",
                    )
                )

    # A null in a column declared absent:'gap' is a missing figure, not a zero.
    # Summing over it silently understates the total, and an understated total
    # that passes every other check is exactly the failure this whole design
    # exists to prevent. So each one is reported, and it must be attached to a
    # hook that says how it gets filled.
    for tname in {**{t: None for t in s.unloaded}, **s.instances}:
        rows = s.instances.get(tname) or []
        props = s.types[tname].get("props") or {}
        gap_cols = [p for p, d in props.items() if d.get("absent") == "gap"]
        gap_refs = [p for p, d in props.items() if d.get("type") == "ref" and d.get("to") == "hook"]
        idp = s.types[tname]["id"]
        total = s.unloaded.get(tname, len(rows))
        for col in gap_cols:
            # Either the column says that all of its absences are the same gap,
            # or each row names the one it is waiting on. The first is not a
            # shortcut: rows that come from somewhere else cannot be annotated,
            # because we do not own that table.
            declared = props[col].get("gap")
            if tname in s.unloaded:
                missing, offenders = _absent_in_source(s, tname, col, idp)
            else:
                blank = [r for r in rows if r.get(col) is None]
                missing = len(blank)
                offenders = [
                    r.get(idp) for r in blank if not any(r.get(g) for g in gap_refs)
                ]
            uncovered = 0 if declared else len(offenders)
            # The consequence of an untracked gap differs by what is missing,
            # and a message that names the wrong consequence teaches the reader
            # to skim the next one.
            cost = (
                "nobody is chasing the counterpart, and an unmatched row reads "
                "exactly like a matched one on the graph"
                if props[col].get("type") == "ref"
                else "the total silently understates by an unknown amount"
            )
            if declared:
                detail = (
                    f"{missing} of {total} rows have no {col}; all of them are "
                    f"accounted for by {declared}"
                    if missing
                    else ""
                )
            elif uncovered:
                detail = (
                    f"{uncovered} of {total} rows have no {col}, and it means 'not "
                    f"recorded yet' — neither the column nor those rows name a gap "
                    f"for it, so {cost}"
                )
            else:
                detail = ""
            c.checks.append(
                Check(
                    f"absent/{tname}/{col}",
                    uncovered == 0,
                    detail,
                    affected=missing,
                    sample=offenders[:SAMPLE],
                )
            )

    # The plug's divergence is computed and reported every time, so it cannot
    # drift quietly between runs. Zero is fine; unregistered is not.
    for nname, n in s.nodes.items():
        against = n.get("plug_against")
        if not against:
            continue
        mine, theirs = c.values.get(nname), c.values.get(against)
        if mine is None or theirs is None:
            c.checks.append(
                Check(f"plug/{nname}", False, "one side has no value to compare")
            )
            continue
        diff = mine - theirs
        c.values[f"{nname}__residual"] = diff
        hook = s.hooks.get(n.get("residual_to", ""))
        c.checks.append(
            Check(
                f"plug/{nname}",
                diff == 0 or bool(hook),
                ""
                if diff == 0 or hook
                else f"differs from {against} by {diff:,} with nowhere to register it",
            )
        )

    # A link that points at nothing draws an edge to nowhere, and a reviewer
    # following it learns only that the graph lied. Resolving every one of them
    # on every compile is the difference between a relationship and a string
    # that happens to look like an id.
    for tname, rows in s.instances.items():
        links = s.links_of(tname)
        if not links:
            continue
        idp = s.types[tname]["id"]
        for prop, target in links.items():
            known = s.ids_of(target)
            dangling = [
                row.get(idp)
                for row in rows
                if row.get(prop) is not None and row.get(prop) not in known
            ]
            linked = sum(1 for row in rows if row.get(prop) is not None)
            c.checks.append(
                Check(
                    f"link/{tname}/{prop}",
                    not dangling,
                    ""
                    if not dangling
                    else f"{len(dangling)} of {linked} rows point at a {target} that "
                    f"does not exist",
                    affected=len(dangling),
                    sample=dangling[:SAMPLE],
                )
            )

    # A hook must name at least one node it affects, otherwise nothing on the
    # graph tells a reader that this number is provisional.
    for hname, h in s.hooks.items():
        affects = h.get("affects") or []
        c.checks.append(
            Check(
                f"hook/{hname}/affects",
                bool(affects),
                ""
                if affects
                else "declares no affected node, so the graph cannot show it is provisional",
            )
        )

    c.view = view_model(s, c, fold_over=fold_over, top_n=top_n)
    return c


def view_model(s: Spec, c: Compiled, *, fold_over: int = 20, top_n: int = 5) -> dict[str, Any]:
    """What the graph app consumes. It renders and emits events; it holds no logic.

    One invariant holds the whole thing together: **every edge endpoint is a node
    in this same document**. A renderer given a dangling edge either invents a
    phantom node or throws, and both are worse than the edge being absent — so
    the folding decision is taken before any edge is emitted, and an edge whose
    other end got folded away is replaced by the type-level edge that survives.
    """
    nodes: list[dict] = []
    edges: list[dict] = []

    # Folding first: it decides which instances exist as nodes at all.
    folded_types = {
        tname: len(rows) > fold_over for tname, rows in s.instances.items()
    }
    # A type that was never fetched is folded by a stronger reason than size.
    folded_types.update({t: True for t in s.unloaded})
    instance_ids: set[str] = set()
    for tname, rows in s.instances.items():
        if folded_types[tname]:
            continue
        idp = s.types[tname]["id"]
        instance_ids |= {f"{tname}/{r.get(idp)}" for r in rows}

    # Derived once, read three ways: where a figure comes from, which hooks make
    # it provisional, and how complete it is. None of the three is authored.
    lin = lin_mod.lineage(s, c.basis)
    prov = lin_mod.provisional(s, lin)
    grade = lin_mod.completeness(s, c.values, prov)

    #: Rank for layout: sources at the top, conclusions at the bottom. A hint
    #: for the renderer, not a fact about the ontology. Read from the kinds
    #: themselves, in the order they are declared, so a new kind cannot appear
    #: without a row to sit on.
    LAYER = {k: i for i, k in enumerate(NODE_KINDS)}

    for name, d in s.nodes.items():
        nodes.append(
            {
                "id": name,
                "kind": "derived",
                "layer": LAYER["derived"],
                "label": d.get("label", name),
                "value": c.values.get(name),
                "op": op_for(d, c.basis),
                "lineage": lin[name],
                "provisional_because": prov[name],
                "plug_against": d.get("plug_against"),
                "residual_to": d.get("residual_to"),
                "residual": c.values.get(f"{name}__residual"),
                "completeness": grade[name],
            }
        )
        # Lineage as edges too, so a renderer can draw the path a reviewer walks.
        for src in lin[name]["inputs"]:
            edges.append({"from": src, "to": name, "rel": "feeds"})
        # What a figure rests on, drawn. `because` names the raw or hook it is
        # justified by, and until now that was a string in the spec that nothing
        # put on the canvas — so a decided figure sat there with its evidence
        # invisible, which is the same fault as a gap pointing at nothing. For a
        # hook the relation usually arrives from the other side as `affects`;
        # deduplication below keeps it to one arrow either way.
        for b in {s.reason_for(name, c.basis), s.reason_for(name, None)}:
            if b and b in s.raw:
                edges.append({"from": b, "to": name, "rel": "rests_on"})
        # The measure a plug is checked against is an *input* to it — the plug
        # is our total minus that measure — so it points in, like everything
        # else a node is computed from. Pointing out read as the plug feeding
        # the measure, which is the opposite of what a plug is for.
        if d.get("plug_against"):
            edges.append({"from": d["plug_against"], "to": name, "rel": "plug_against"})
        # `residual_to` is deliberately not an edge. The gap it names already
        # points at this node — that is what check() requires of it — and drawing
        # the reverse as well put two arrows between the same pair in opposite
        # directions, which reads as a loop and lays out as one. Where the
        # remainder lands is on the node, and the panel says it.

    # How many rows each gap is holding up, so the number survives folding: the
    # rows themselves may be collapsed, but "waiting on 2 contracts" is the part
    # a reviewer needs either way.
    #
    # Counted from the spec rather than from the edges already emitted — the
    # edge that carries this is produced further down, and reading it here gave
    # every gap a confident zero.
    cited_by: dict[str, int] = {}
    for tname, rows in s.instances.items():
        props = s.types[tname].get("props") or {}
        for prop, d in props.items():
            if d.get("type") != "ref" or d.get("to") != "hook":
                continue
            for row in rows:
                ref = row.get(prop)
                if ref in s.hooks:
                    cited_by[ref] = cited_by.get(ref, 0) + 1

    for hname, h in s.hooks.items():
        nodes.append(
            {
                "id": hname,
                "kind": "hook",
                "layer": 1,
                "waiting_on": cited_by.get(hname, 0),
                "label": h.get("label", hname),
                "resolve_when": h.get("resolve_when"),
                "owner": h.get("owner"),
                "blocked_on": h.get("blocked_on"),
            }
        )
        for target in h.get("affects") or []:
            edges.append({"from": hname, "to": target, "rel": "affects"})
        # A resolvable owner becomes an edge, so "who is this waiting on" is a
        # question the graph answers rather than one a person reconstructs.
        owner = str(h.get("owner") or "")
        if "/" in owner and owner in instance_ids:
            edges.append({"from": hname, "to": owner, "rel": "owned_by"})
        elif "/" in owner:
            # The person was folded away with their group; the edge still has to
            # land somewhere, so it lands on the type.
            edges.append({"from": hname, "to": owner.split("/", 1)[0], "rel": "owned_by"})

    # A gap is cited by the rows that are waiting on it, and that is the first
    # thing anyone asks of one: "合同原件未到" — which contracts? The rows name
    # the hook in a ref property, the compiler already checks every one of them
    # resolves, and the graph drew the hook's *effects* and its *owner* while
    # leaving out the rows themselves. A gap with no visible subjects reads as a
    # note pinned to nothing.
    for tname, rows in s.instances.items():
        props = s.types[tname].get("props") or {}
        hook_refs = [
            p for p, d in props.items() if d.get("type") == "ref" and d.get("to") == "hook"
        ]
        if not hook_refs:
            continue
        idp = s.types[tname]["id"]
        if folded_types[tname]:
            # The rows are not on the canvas, so the edge lands on the type —
            # the same rule the ownership edges follow. Dropping it instead left
            # the gap with nothing to point at in the default view, so there was
            # no way to learn that opening that type is where the answer is.
            # One edge per gap, not one per row: the count on the gap says how
            # many, and a fan of identical arrows says nothing extra.
            for ref in sorted({
                row.get(prop) for row in rows for prop in hook_refs
                if row.get(prop) in s.hooks
            }):
                edges.append({"from": ref, "to": tname, "rel": "cites", "folded": True})
            continue
        for row in rows:
            for prop in hook_refs:
                ref = row.get(prop)
                if ref and ref in s.hooks:
                    edges.append(
                        {
                            "from": ref,
                            "to": f"{tname}/{row.get(idp)}",
                            "rel": "cites",
                            "via": prop,
                        }
                    )

    # A raw supplies the properties that name it in `from`. The relationship is
    # already in the spec and already checked on every compile
    # (provenance/<Type>.<prop>@<raw>) — it just was not being drawn, which left
    # every connector floating unattached at the top of the canvas looking like
    # noise. Provenance is the first question anyone asks of a figure, so the
    # edge that answers it cannot be the one that is missing.
    for tname in s.instances:
        supplied: dict[str, list[str]] = {}
        for pname in (s.types.get(tname) or {}).get("props") or {}:
            for src in s.sources_of(tname, pname):
                supplied.setdefault(src, []).append(pname)
        for src, props in supplied.items():
            if src in s.raw:
                edges.append(
                    {"from": src, "to": tname, "rel": "supplies", "props": sorted(props)}
                )

    for rname, r in s.raw.items():
        nodes.append(
            {
                "id": rname,
                "kind": "raw",
                "layer": 0,
                "label": r.get("label", rname),
                "connector": r.get("connector"),
            }
        )

    # Which derived nodes aggregate over which type, read from the AST rather
    # than by matching substrings of the op source.
    aggregated_by: dict[str, list[str]] = {}
    for name, d in s.nodes.items():
        src = op_for(d, c.basis)
        if not src:
            continue
        for tname in expr.aggregated_types(expr.parse(src)):
            aggregated_by.setdefault(tname, []).append(name)

    # Instances are grouped, not listed: a business graph has more rows than a
    # canvas has room. Folding is a view decision, which is why it is here.
    groups: list[dict] = []
    # A type too large to fetch is still a type: it belongs on the canvas with
    # its size, because "this object exists and there are 609,283 of them" is
    # most of what a reader wants from it. What it cannot do is open.
    for tname, rows in {**{t: [] for t in s.unloaded}, **s.instances}.items():
        t = s.types[tname]
        props = t.get("props") or {}
        idp = t["id"]
        members = [{"id": r.get(idp), "props": r} for r in rows]
        folded = folded_types[tname]
        grades = lin_mod.instance_completeness(s, rows, tname)

        # The type is a node, always — it is the end of every `aggregates` and
        # type-level `links` edge, and it is what a folded group collapses to.
        nodes.append(
            {
                "id": tname,
                "kind": "type",
                "layer": 0,
                "label": t.get("label", tname),
                "count": s.unloaded.get(tname, len(members)),
                # Not "folded away to keep the canvas readable" but "never
                # fetched", and the two are different promises to the reader:
                # one opens on a click, the other cannot.
                "folded": folded or tname in s.unloaded,
                "unfetched": s.unloaded.get(tname),
                # What this object is a view over. Two types backed by the same
                # table is the whole claim that an object is not a table — and
                # it was provable in a test while being invisible on the canvas,
                # which is the same as not having it.
                "backing": s.backing_of(tname) or None,
            }
        )
        # Instances are nodes only when the group is not folded, which is the
        # same condition that governs their edges. The two decisions are one.
        if not folded:
            for r in rows:
                iid = r.get(idp)
                nodes.append(
                    {
                        "id": f"{tname}/{iid}",
                        "kind": "instance",
                        "layer": 0,
                        "label": str(iid),
                        "type": tname,
                        "props": r,
                        "completeness": grades.get(iid),
                    }
                )
                edges.append({"from": tname, "to": f"{tname}/{iid}", "rel": "member"})

        # A folded group that shows nothing is useless: the reader learns only
        # that there are too many. So folding produces buckets instead — one per
        # value of each enum, with a count and a total, which is what a person
        # actually asks of a long list. Enums are the natural axes because the
        # spec already says their values are closed.
        buckets: dict[str, list[dict]] = {}
        money_cols = [p for p, d in props.items() if d.get("type") == "money"]
        for axis, d in props.items():
            if d.get("type") != "enum":
                continue
            by: dict[Any, dict] = {}
            for r in rows:
                key = r.get(axis)
                slot = by.setdefault(key, {"value": key, "count": 0, "totals": {}})
                slot["count"] += 1
                for mc in money_cols:
                    v = r.get(mc)
                    if v is not None:
                        slot["totals"][mc] = slot["totals"].get(mc, 0) + v
            buckets[axis] = sorted(by.values(), key=lambda b: (-b["count"], str(b["value"])))

        # Top-N by each money column, so a folded group still surfaces the rows
        # that carry the weight — the ones a reviewer would look at first.
        top: dict[str, list[dict]] = {}
        for mc in money_cols:
            ranked = sorted(
                (r for r in rows if r.get(mc) is not None),
                key=lambda r: r[mc],
                reverse=True,
            )
            top[mc] = [{"id": r.get(idp), "value": r[mc]} for r in ranked[:top_n]]

        groups.append(
            {
                "type": tname,
                "completeness": grades,
                "label": t.get("label", tname),
                "count": s.unloaded.get(tname, len(members)),
                # Not "folded away to keep the canvas readable" but "never
                # fetched", and the two are different promises to the reader:
                # one opens on a click, the other cannot.
                "folded": folded or tname in s.unloaded,
                "unfetched": s.unloaded.get(tname),
                # What this object is a view over. Two types backed by the same
                # table is the whole claim that an object is not a table — and
                # it was provable in a test while being invisible on the canvas,
                # which is the same as not having it.
                "backing": s.backing_of(tname) or None,
                "members": [] if folded else members,
                "buckets": buckets,
                "top": top,
                "id_prop": idp,
                "owners": {p: s.owner_of(tname, p) for p in props},
                # How a computed column got its value, so the panel can show the
                # formula the way a derived node shows its expression. A figure
                # whose derivation is only in the author's head is the thing
                # this replaced.
                "ops": {p: d["op"] for p, d in props.items() if "op" in d},
            }
        )
        for name in aggregated_by.get(tname, ()):
            edges.append({"from": tname, "to": name, "rel": "aggregates"})

        # Links, at two zoom levels. The type-level edge always exists, because
        # "these two types are related, and here is how much of it is unmatched"
        # is the shape of the question a reviewer opens with. Instance-level
        # edges are emitted only for an unfolded group: a 556-row ledger would
        # otherwise put 556 edges on a canvas that already folded the rows away,
        # which is the long list again wearing a different hat.
        for prop, target in s.links_of(tname).items():
            linked = [r for r in rows if r.get(prop) is not None]
            edges.append(
                {
                    "from": tname,
                    "to": target,
                    "rel": "links",
                    "via": prop,
                    # Where the link comes from. A foreign key the source system
                    # maintains and a relationship this ontology worked out are
                    # not the same claim, and until now they were the same
                    # arrow: one is a fact someone else is responsible for, the
                    # other is ours to defend. The owner rule already says
                    # which, so the edge carries it.
                    "owner": s.owner_of(tname, prop),
                    "linked": len(linked),
                    "unlinked": len(rows) - len(linked),
                }
            )
            if folded:
                continue
            for r in linked:
                edges.append(
                    {
                        "from": f"{tname}/{r.get(idp)}",
                        "to": f"{target}/{r[prop]}",
                        "rel": "link",
                        "via": prop,
                    }
                )

    return {
        "ontology": s.name,
        "dimensions": c.at,
        "basis": c.basis,
        "nodes": nodes,
        "edges": edges,
        "groups": groups,
        # The evidence travels with the statement. A check whose rows stayed in
        # the compiler is a check the reader can only believe.
        "checks": [
            {
                "name": k.name,
                "ok": k.ok,
                "detail": k.detail,
                "affected": k.affected,
                "sample": k.sample,
            }
            for k in c.checks
        ],
    }


def to_json(c: Compiled) -> str:
    return json.dumps(c.view, ensure_ascii=False, indent=2)
