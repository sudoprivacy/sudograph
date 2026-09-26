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

from . import expr
from . import lineage as lin_mod
from .spec import Spec


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


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
    return Spec(
        name=s.name, types=s.types, raw=s.raw, hooks=s.hooks,
        instances=kept, nodes=s.nodes, ops=s.ops, checks=s.checks,
        bases=s.bases, bridges=s.bridges, dimensions=s.dimensions,
    )


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

    return Spec(
        name=s.name, types=s.types, raw=s.raw, hooks=s.hooks,
        instances=resolved, nodes=s.nodes, ops=s.ops, checks=s.checks,
        bases=s.bases, bridges=s.bridges, dimensions=s.dimensions,
    )


def op_for(node: dict, basis: str | None) -> str | None:
    """The expression this node uses under `basis`.

    A basis-specific expression wins; otherwise the shared one applies. Writing
    only the expressions that genuinely differ is the point: everything else
    stays single-sourced and cannot drift between the two sets of figures.
    """
    if basis and f"op@{basis}" in node:
        return node[f"op@{basis}"]
    return node.get("op")


def _order(s: Spec, basis: str | None = None) -> list[str]:
    """Topologically order derived nodes; raise on a cycle."""
    derived = {n: d for n, d in s.nodes.items() if d.get("kind") == "derived"}
    deps = {
        n: expr.referenced_names(expr.parse(op_for(d, basis) or "0")) & set(derived)
        for n, d in derived.items()
    }
    out: list[str] = []
    temp: set[str] = set()
    done: set[str] = set()

    def visit(n: str, trail: list[str]) -> None:
        if n in done:
            return
        if n in temp:
            raise ValueError("cycle among derived nodes: " + " -> ".join([*trail, n]))
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

    c = Compiled(ontology=s.name, at=at, basis=basis)
    if at:
        s = _restrict(s, at)
    s = _corroborate(s, c)

    # ── values ────────────────────────────────────────────────────────
    for name in _order(s, basis):
        node = s.nodes[name]
        src = op_for(node, basis)
        if not src:
            continue
        try:
            c.values[name] = expr.evaluate(expr.parse(src), dict(c.values), s.instances)
        except expr.ExprError as e:
            c.checks.append(Check(f"node/{name}", False, str(e)))

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
            # Every declared source must own up to supplying it. A corroborated
            # figure whose second source never claimed to provide it is not
            # corroborated; it is one source and a hopeful entry in a list.
            for src in s.sources_of(tname, pname):
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
                # The consequence of an untracked gap differs by what is missing,
                # and a message that names the wrong consequence teaches the
                # reader to skim the next one.
                cost = (
                    "nobody is chasing the counterpart, and an unmatched row reads "
                    "exactly like a matched one on the graph"
                    if props[col].get("type") == "ref"
                    else "the total silently understates by an unknown amount"
                )
                c.checks.append(
                    Check(
                        f"absent/{tname}/{row.get(idp)}/{col}",
                        covered,
                        ""
                        if covered
                        else f"{col} is absent and means 'not recorded yet', but the row "
                        f"cites no hook — {cost}",
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
            for row in rows:
                ref = row.get(prop)
                if ref is None:
                    continue
                c.checks.append(
                    Check(
                        f"link/{tname}/{row.get(idp)}/{prop}",
                        ref in known,
                        "" if ref in known else f"points at {target}/{ref!r}, which does not exist",
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
                "op": op_for(d, c.basis),
                "lineage": lin[name],
                "provisional_because": prov[name],
                "plug_against": d.get("plug_against"),
                "residual": c.values.get(f"{name}__residual"),
                "completeness": grade[name],
            }
        )
        # Lineage as edges too, so a renderer can draw the path a reviewer walks.
        for src in lin[name]["inputs"]:
            edges.append({"from": src, "to": name, "rel": "feeds"})
        # Authored on the node, emitted as edges, exactly like hook.affects.
        if d.get("plug_against"):
            edges.append({"from": name, "to": d["plug_against"], "rel": "plug_against"})
        if d.get("residual_to"):
            edges.append({"from": name, "to": d["residual_to"], "rel": "residual_to"})

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
        # A resolvable owner becomes an edge, so "who is this waiting on" is a
        # question the graph answers rather than one a person reconstructs.
        owner = str(h.get("owner") or "")
        if "/" in owner and owner in instance_ids:
            edges.append({"from": hname, "to": owner, "rel": "owned_by"})
        elif "/" in owner:
            # The person was folded away with their group; the edge still has to
            # land somewhere, so it lands on the type.
            edges.append({"from": hname, "to": owner.split("/", 1)[0], "rel": "owned_by"})

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
        if d.get("kind") != "derived" or not src:
            continue
        for tname in expr.aggregated_types(expr.parse(src)):
            aggregated_by.setdefault(tname, []).append(name)

    # Instances are grouped, not listed: a business graph has more rows than a
    # canvas has room. Folding is a view decision, which is why it is here.
    groups: list[dict] = []
    for tname, rows in s.instances.items():
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
                "count": len(members),
                "folded": folded,
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
        "checks": [{"name": k.name, "ok": k.ok, "detail": k.detail} for k in c.checks],
    }


def to_json(c: Compiled) -> str:
    return json.dumps(c.view, ensure_ascii=False, indent=2)
