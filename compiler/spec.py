"""Load a spec, and turn the owner rule into a refusal rather than a convention.

Validation has two layers:
  L1 structure — required fields present, types right, enum values in range;
  L2 semantics — the owner rule, referential integrity, expressions that parse.

L2 is why this file exists. An L1 failure is a typo; an L2 failure means the
ontology itself is wrong.

Field names are English because they are our contract. Values stay in the
customer's own vocabulary, because translating business terms loses them.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

import yaml

from . import expr

OWNERS = ("source", "ontology")
NODE_KINDS = ("raw", "hook", "derived")
OP_CLASSES = ("DerivedOp", "RecordableOp", "BlockedOp")
PROP_TYPES = ("string", "money", "number", "date", "enum", "ref", "bool")

TOP_LEVEL = {"ontology", "types", "raw", "hooks", "instances", "nodes", "ops"}


class SpecError(ValueError):
    pass


@dataclass
class Spec:
    name: str
    types: dict[str, dict]
    raw: dict[str, dict] = field(default_factory=dict)
    hooks: dict[str, dict] = field(default_factory=dict)
    instances: dict[str, list[dict]] = field(default_factory=dict)
    nodes: dict[str, dict] = field(default_factory=dict)
    ops: dict[str, dict] = field(default_factory=dict)

    def owner_of(self, type_name: str, prop: str) -> str | None:
        t = self.types.get(type_name)
        if not t:
            return None
        p = (t.get("props") or {}).get(prop)
        return p.get("owner") if p else None

    def types_with(self, prop: str) -> list[str]:
        return [tn for tn, t in self.types.items() if prop in (t.get("props") or {})]


def load(path: str) -> Spec:
    with io.open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    if not isinstance(doc, dict):
        raise SpecError(f"{path}: the top level must be a mapping")
    unknown = set(doc) - TOP_LEVEL
    if unknown:
        raise SpecError(f"unknown top-level keys: {sorted(unknown)}")
    if "ontology" not in doc or "types" not in doc:
        raise SpecError("the top level needs both 'ontology' and 'types'")
    s = Spec(
        name=doc["ontology"],
        types=doc["types"],
        raw=doc.get("raw") or {},
        hooks=doc.get("hooks") or {},
        instances=doc.get("instances") or {},
        nodes=doc.get("nodes") or {},
        ops=doc.get("ops") or {},
    )
    problems = check(s)
    if problems:
        raise SpecError("spec is invalid:\n  - " + "\n  - ".join(problems))
    return s


def check(s: Spec) -> list[str]:
    """Return every problem rather than stopping at the first.

    The author is an agent: one pass that lists all of them is cheaper than a
    round trip per mistake.
    """
    out: list[str] = []

    for tname, t in s.types.items():
        for req in ("label", "id", "props"):
            if req not in t:
                out.append(f"type {tname} is missing '{req}'")
        props = t.get("props") or {}
        if t.get("id") and t["id"] not in props:
            out.append(f"type {tname}: id property {t['id']!r} is not among its props")
        for pname, p in props.items():
            where = f"{tname}.{pname}"
            if p.get("type") not in PROP_TYPES:
                out.append(f"{where}: type {p.get('type')!r} is not one of {PROP_TYPES}")
            owner = p.get("owner")
            if owner not in OWNERS:
                out.append(f"{where}: owner must be 'source' or 'ontology', got {owner!r}")
            # Hard rule: a source property must name the raw that supplies it.
            if owner == "source":
                if not p.get("from"):
                    out.append(f"{where}: source property needs 'from' naming its raw")
                elif p["from"] not in s.raw:
                    out.append(f"{where}: 'from' points at unknown raw {p['from']!r}")
            if owner == "ontology" and p.get("from"):
                out.append(f"{where}: ontology property cannot have 'from' — it is not upstream")
            if p.get("type") == "enum" and not p.get("values"):
                out.append(f"{where}: an enum needs 'values'")

    for rname, r in s.raw.items():
        if not r.get("connector"):
            out.append(f"raw {rname} needs a 'connector' (one executable command)")
        for pname in r.get("provides") or []:
            if not s.types_with(pname):
                out.append(f"raw {rname} claims to provide {pname!r}, which no type declares")

    for hname, h in s.hooks.items():
        if not h.get("resolve_when"):
            out.append(f"hook {hname} needs 'resolve_when' — otherwise it can never clear")
        for node in h.get("affects") or []:
            if node not in s.nodes:
                out.append(f"hook {hname} affects {node!r}, which is not a declared node")

    for tname, rows in s.instances.items():
        if tname not in s.types:
            out.append(f"instances declare {tname!r}, which is not a type")
            continue
        t = s.types[tname]
        idp = t.get("id")
        seen: set[Any] = set()
        for i, row in enumerate(rows):
            unknown = set(row) - set(t.get("props") or {})
            if unknown:
                out.append(f"{tname}[{i}] has undeclared properties: {sorted(unknown)}")
            if idp and idp in row:
                if row[idp] in seen:
                    out.append(f"{tname}: duplicate id {row[idp]!r} — instance ids must be unique")
                seen.add(row[idp])
            elif idp:
                out.append(f"{tname}[{i}] is missing its id property {idp!r}")
            for pname, v in row.items():
                p = (t.get("props") or {}).get(pname)
                if p and p.get("type") == "enum" and v is not None and v not in p["values"]:
                    out.append(f"{tname}[{i}].{pname} = {v!r} is not in {p['values']}")

    for nname, n in s.nodes.items():
        if n.get("kind") not in NODE_KINDS:
            out.append(f"node {nname}: kind {n.get('kind')!r} is not one of {NODE_KINDS}")
        if n.get("kind") == "derived":
            if not n.get("op"):
                out.append(f"derived node {nname} needs an 'op'")
            else:
                try:
                    expr.parse(n["op"])
                except expr.ExprError as e:
                    out.append(f"node {nname}: op does not parse: {e}")

    for oname, o in s.ops.items():
        if o.get("class") not in OP_CLASSES:
            out.append(f"op {oname}: class {o.get('class')!r} is not one of {OP_CLASSES}")
        if o.get("intent") != "required":
            out.append(f"op {oname}: intent must be 'required' — every write says why")
        writes = o.get("writes") or []
        if not writes and o.get("class") != "BlockedOp":
            out.append(f"op {oname} declares no 'writes'")
        # Hard rule: ops may only write owner=ontology properties.
        for w in writes:
            owners = {s.owner_of(tn, w) for tn in s.types_with(w)}
            owners.discard(None)
            if not owners:
                out.append(f"op {oname} writes {w!r}, which is not a property of any type")
            elif "source" in owners:
                out.append(
                    f"op {oname} writes {w!r}, whose owner is 'source' — "
                    f"upstream facts are written by connectors, never by ops"
                )

    return out
