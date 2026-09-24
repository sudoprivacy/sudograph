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
from dataclasses import dataclass, field
from typing import Any

from . import expr, lineage as lin_mod
from .spec import Spec


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Compiled:
    ontology: str
    period: str | None = None
    values: dict[str, Any] = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)
    view: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)

    def summary(self) -> str:
        good = sum(1 for c in self.checks if c.ok)
        return f"{good}/{len(self.checks)} checks passed"


def _restrict(s: Spec, period: str) -> Spec:
    """A copy whose instances are only those of one period.

    Types that declare no period property are left whole: reference data such
    as people or suppliers is not per-period, and dropping it would break every
    row that points at it.
    """
    kept: dict[str, list[dict]] = {}
    for tname, rows in s.instances.items():
        col = (s.types.get(tname) or {}).get("period")
        kept[tname] = [r for r in rows if r.get(col) == period] if col else list(rows)
    return Spec(
        name=s.name, types=s.types, raw=s.raw, hooks=s.hooks,
        instances=kept, nodes=s.nodes, ops=s.ops, checks=s.checks,
    )


def _order(s: Spec) -> list[str]:
    """Topologically order derived nodes; raise on a cycle."""
    derived = {n: d for n, d in s.nodes.items() if d.get("kind") == "derived"}
    deps = {
        n: expr.referenced_names(expr.parse(d["op"])) & set(derived)
        for n, d in derived.items()
    }
    out: list[str] = []
    temp: set[str] = set()
    done: set[str] = set()

    def visit(n: str, trail: list[str]) -> None:
        if n in done:
            return
        if n in temp:
            raise ValueError("cycle among derived nodes: " + " -> ".join(trail + [n]))
        temp.add(n)
        for d in sorted(deps[n]):
            visit(d, trail + [n])
        temp.discard(n)
        done.add(n)
        out.append(n)

    for n in sorted(derived):
        visit(n, [])
    return out


def compile_spec(
    s: Spec, *, fold_over: int = 20, top_n: int = 5, period: str | None = None
) -> Compiled:
    """Compile, optionally restricted to one reporting period.

    Filtering happens before anything is computed, so every figure, check and
    bucket describes that period alone. The alternative — carrying a column per
    period on each node — makes the spec grow with time and makes "which period
    is this total" a question the reader has to keep answering.
    """
    c = Compiled(ontology=s.name, period=period)
    if period is not None:
        s = _restrict(s, period)

    # ── values ────────────────────────────────────────────────────────
    for name in _order(s):
        node = s.nodes[name]
        try:
            c.values[name] = expr.evaluate(expr.parse(node["op"]), dict(c.values), s.instances)
        except expr.ExprError as e:
            c.checks.append(Check(f"node/{name}", False, str(e)))

    # ── articulation checks: the unit tier ────────────────────────────
    # Assertions the author wrote, evaluated over the node values this same
    # pass produced. There is no separate reconciliation script by design: if
    # the check ran against anything else, the two could disagree.
    for cname, spec_ in s.checks.items():
        src = spec_.get("expr") if isinstance(spec_, dict) else spec_
        # Presence of the key is what scopes a check, not its value: `period:
        # null` means "only when no period is selected", which is a real scope
        # and not the absence of one. Testing the value would have let a
        # whole-ledger assertion run against a single period and fail there.
        scoped = isinstance(spec_, dict) and "period" in spec_
        if scoped and spec_["period"] != period:
            # A check scoped elsewhere is not asked here. Not asked is neither
            # pass nor fail: it is not counted, because a check that did not run
            # must never read as evidence.
            continue
        try:
            ok = bool(expr.evaluate(expr.parse(src), dict(c.values), s.instances))
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
            r = s.raw.get(p.get("from", ""))
            declared = pname in (r.get("provides") or []) if r else False
            c.checks.append(
                Check(
                    f"provenance/{tname}.{pname}",
                    declared,
                    "" if declared else f"raw {p.get('from')!r} does not list it in 'provides'",
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
    for tname, rows in s.instances.items():
        props = s.types[tname].get("props") or {}
        gap_cols = [p for p, d in props.items() if d.get("absent") == "gap"]
        gap_refs = [p for p, d in props.items() if d.get("type") == "ref" and d.get("to") == "hook"]
        idp = s.types[tname]["id"]
        for row in rows:
            for col in gap_cols:
                if row.get(col) is not None:
                    continue
                covered = any(row.get(g) for g in gap_refs)
                c.checks.append(
                    Check(
                        f"absent/{tname}/{row.get(idp)}/{col}",
                        covered,
                        ""
                        if covered
                        else f"{col} is absent and means 'not recorded yet', but the row cites no hook — "
                        f"the total silently understates by an unknown amount",
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
                "" if affects else "declares no affected node, so the graph cannot show it is provisional",
            )
        )

    c.view = view_model(s, c, fold_over=fold_over, top_n=top_n)
    return c


def view_model(s: Spec, c: Compiled, *, fold_over: int = 20, top_n: int = 5) -> dict[str, Any]:
    """What the graph app consumes. It renders and emits events; it holds no logic."""
    nodes: list[dict] = []
    edges: list[dict] = []

    # Derived once, read three ways: where a figure comes from, which hooks make
    # it provisional, and how complete it is. None of the three is authored.
    lin = lin_mod.lineage(s)
    prov = lin_mod.provisional(s, lin)
    grade = lin_mod.completeness(s, c.values, prov)

    #: Rank for layout: sources at the top, conclusions at the bottom. A hint
    #: for the renderer, not a fact about the ontology.
    LAYER = {"raw": 0, "hook": 1, "derived": 2}

    for name, d in s.nodes.items():
        nodes.append(
            {
                "id": name,
                "kind": d.get("kind"),
                "layer": LAYER.get(d.get("kind"), 2),
                "label": d.get("label", name),
                "value": c.values.get(name),
                "op": d.get("op"),
                "lineage": lin[name],
                "provisional_because": prov[name],
                "completeness": grade[name],
            }
        )
        # Lineage as edges too, so a renderer can draw the path a reviewer walks.
        for src in lin[name]["inputs"]:
            edges.append({"from": src, "to": name, "rel": "feeds"})

    for hname, h in s.hooks.items():
        nodes.append(
            {
                "id": hname,
                "kind": "hook",
                "layer": 1,
                "label": h.get("label", hname),
                "resolve_when": h.get("resolve_when"),
                "owner": h.get("owner"),
                "blocked_on": h.get("blocked_on"),
            }
        )
        for target in h.get("affects") or []:
            edges.append({"from": hname, "to": target, "rel": "affects"})

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
        if d.get("kind") != "derived" or not d.get("op"):
            continue
        for tname in expr.aggregated_types(expr.parse(d["op"])):
            aggregated_by.setdefault(tname, []).append(name)

    # Instances are grouped, not listed: a business graph has more rows than a
    # canvas has room. Folding is a view decision, which is why it is here.
    groups: list[dict] = []
    for tname, rows in s.instances.items():
        t = s.types[tname]
        props = t.get("props") or {}
        idp = t["id"]
        members = [{"id": r.get(idp), "props": r} for r in rows]
        folded = len(members) > fold_over

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
                "completeness": lin_mod.instance_completeness(s, rows, tname),
                "label": t.get("label", tname),
                "count": len(members),
                "folded": folded,
                "members": [] if folded else members,
                "buckets": buckets,
                "top": top,
                "id_prop": idp,
                "owners": {p: d.get("owner") for p, d in props.items()},
            }
        )
        for name in aggregated_by.get(tname, ()):
            edges.append({"from": tname, "to": name, "rel": "aggregates"})

    return {
        "ontology": s.name,
        "period": c.period,
        "nodes": nodes,
        "edges": edges,
        "groups": groups,
        "checks": [{"name": k.name, "ok": k.ok, "detail": k.detail} for k in c.checks],
    }


def to_json(c: Compiled) -> str:
    return json.dumps(c.view, ensure_ascii=False, indent=2)
