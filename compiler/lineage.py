"""Derive what the graph knows but nobody wrote down.

Three things fall out of one traversal, and all three are the kind a person
cannot maintain by hand without it going stale:

  * **lineage** — which nodes feed a figure, and which leaves it ultimately
    rests on. A reviewer asks "where does this number come from" and an agent
    asks the same question; this is the answer both read.
  * **provisional** — which hooks make a figure uncertain, *transitively*. A
    total whose input is provisional is provisional too, and nobody remembers
    to propagate that by hand.
  * **completeness** — full / partial / missing, inferred from the hooks and
    the values themselves. Asking an author to mark it a second time only
    creates something to disagree with the hooks.
"""

from __future__ import annotations

from typing import Any

from . import expr
from .spec import Spec

FULL = "full"
PARTIAL = "partial"
MISSING = "missing"


def direct_inputs(s: Spec) -> dict[str, set[str]]:
    """node -> the nodes its expression reads directly."""
    out: dict[str, set[str]] = {}
    for name, d in s.nodes.items():
        if d.get("kind") != "derived" or not d.get("op"):
            out[name] = set()
            continue
        ast = expr.parse(d["op"])
        out[name] = expr.referenced_names(ast) & set(s.nodes)
    return out


def _closure(seed: set[str], step: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(seed)
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(step.get(n, ()))
    return seen


def lineage(s: Spec) -> dict[str, dict[str, Any]]:
    """Per node: direct inputs, the full ancestor set, and the leaves beneath it."""
    inputs = direct_inputs(s)
    out: dict[str, dict[str, Any]] = {}
    for name in s.nodes:
        ancestors = _closure(inputs.get(name, set()), inputs) - {name}
        leaves = sorted(a for a in ancestors if not inputs.get(a))
        out[name] = {
            "inputs": sorted(inputs.get(name, set())),
            "ancestors": sorted(ancestors),
            "leaves": leaves,
        }
    return out


def provisional(s: Spec, lin: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    """node -> the hooks that make it provisional, its own and its ancestors'.

    Declared the other way round in the spec (a hook says what it affects),
    because that is how a person discovers a gap. Read this way round at review
    time, because that is how a person questions a number.
    """
    direct: dict[str, set[str]] = {}
    for hname, h in s.hooks.items():
        for target in h.get("affects") or []:
            direct.setdefault(target, set()).add(hname)

    out: dict[str, list[str]] = {}
    for name in s.nodes:
        hooks = set(direct.get(name, set()))
        for anc in lin[name]["ancestors"]:
            hooks |= direct.get(anc, set())
        out[name] = sorted(hooks)
    return out


def completeness(
    s: Spec,
    values: dict[str, Any],
    prov: dict[str, list[str]],
) -> dict[str, str]:
    """full / partial / missing, inferred rather than declared.

    A node with no hook against it is full. One that is provisional but still
    carries a figure is partial — usable, with a caveat. One that is provisional
    and has no figure is missing, and saying so is the whole point: an absent
    number that renders as a blank is indistinguishable from a zero.
    """
    out: dict[str, str] = {}
    for name in s.nodes:
        if not prov.get(name):
            out[name] = FULL
        elif values.get(name) is None:
            out[name] = MISSING
        else:
            out[name] = PARTIAL
    return out


def instance_completeness(s: Spec, rows: list[dict], tname: str) -> dict[str, str]:
    """The same three grades per instance, from its own gap references."""
    props = s.types[tname].get("props") or {}
    idp = s.types[tname]["id"]
    gap_refs = [p for p, d in props.items() if d.get("type") == "ref" and d.get("to") == "hook"]
    money = [p for p, d in props.items() if d.get("type") in ("money", "number")]

    out: dict[str, str] = {}
    for r in rows:
        cited = [r.get(g) for g in gap_refs if r.get(g)]
        if not cited:
            out[r.get(idp)] = FULL
        elif any(r.get(m) is None for m in money):
            out[r.get(idp)] = MISSING
        else:
            out[r.get(idp)] = PARTIAL
    return out
