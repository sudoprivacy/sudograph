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
from .spec import Spec


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Compiled:
    ontology: str
    values: dict[str, Any] = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)
    view: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)

    def summary(self) -> str:
        good = sum(1 for c in self.checks if c.ok)
        return f"{good}/{len(self.checks)} checks passed"


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


def compile_spec(s: Spec, *, fold_over: int = 20) -> Compiled:
    c = Compiled(ontology=s.name)

    # ── values ────────────────────────────────────────────────────────
    for name in _order(s):
        node = s.nodes[name]
        try:
            c.values[name] = expr.evaluate(expr.parse(node["op"]), dict(c.values), s.instances)
        except expr.ExprError as e:
            c.checks.append(Check(f"node/{name}", False, str(e)))

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

    c.view = view_model(s, c, fold_over=fold_over)
    return c


def view_model(s: Spec, c: Compiled, *, fold_over: int = 20) -> dict[str, Any]:
    """What the graph app consumes. It renders and emits events; it holds no logic."""
    nodes: list[dict] = []
    edges: list[dict] = []

    for name, d in s.nodes.items():
        nodes.append(
            {
                "id": name,
                "kind": d.get("kind"),
                "label": d.get("label", name),
                "value": c.values.get(name),
                "op": d.get("op"),
            }
        )

    for hname, h in s.hooks.items():
        nodes.append(
            {
                "id": hname,
                "kind": "hook",
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
                "label": r.get("label", rname),
                "connector": r.get("connector"),
            }
        )

    # Instances are grouped, not listed: a business graph has more rows than a
    # canvas has room. Folding is a view decision, which is why it is here.
    groups: list[dict] = []
    for tname, rows in s.instances.items():
        t = s.types[tname]
        idp = t["id"]
        members = [{"id": r.get(idp), "props": r} for r in rows]
        groups.append(
            {
                "type": tname,
                "label": t.get("label", tname),
                "count": len(members),
                "folded": len(members) > fold_over,
                "members": [] if len(members) > fold_over else members,
                "id_prop": idp,
                "owners": {p: d.get("owner") for p, d in (t.get("props") or {}).items()},
            }
        )
        for name, d in s.nodes.items():
            if d.get("kind") == "derived" and tname in (d.get("op") or ""):
                edges.append({"from": tname, "to": name, "rel": "aggregates"})

    return {
        "ontology": s.name,
        "nodes": nodes,
        "edges": edges,
        "groups": groups,
        "checks": [{"name": k.name, "ok": k.ok, "detail": k.detail} for k in c.checks],
    }


def to_json(c: Compiled) -> str:
    return json.dumps(c.view, ensure_ascii=False, indent=2)
