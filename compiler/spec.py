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

TOP_LEVEL = {"ontology", "types", "raw", "hooks", "instances", "nodes", "ops", "checks"}


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
    #: name -> a boolean expression that must hold. These are the unit tier:
    #: pure computation over node values, run on every compile. The integration
    #: tier (can an agent actually use this ontology) is a separate harness.
    checks: dict[str, str] = field(default_factory=dict)

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
        checks=doc.get("checks") or {},
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
        # A type may name the property that carries its reporting period. One
        # spec then serves every period: the compiler feeds it different leaves
        # rather than the author duplicating nodes per period.
        per = t.get("period")
        if per and per not in (t.get("props") or {}):
            out.append(f"type {tname}: period property {per!r} is not among its props")
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
            # A nullable number is ambiguous unless the spec says what absence
            # means. "not recorded yet" and "determined to be zero" look the
            # same in the data and are opposite in the business: one is a gap
            # to chase, the other is a finding. Saying which is cheap here and
            # impossible to recover later.
            if p.get("nullable") and p.get("type") in ("money", "number"):
                if p.get("absent") not in ("gap", "zero"):
                    out.append(
                        f"{where}: a nullable {p['type']} must declare absent: "
                        f"'gap' (not recorded yet) or 'zero' (determined to be none)"
                    )

    for rname, r in s.raw.items():
        if not r.get("connector"):
            out.append(f"raw {rname} needs a 'connector' (one executable command)")
        for pname in r.get("provides") or []:
            if not s.types_with(pname):
                out.append(f"raw {rname} claims to provide {pname!r}, which no type declares")

    for hname, h in s.hooks.items():
        # An owner may name an instance rather than be free text. Then the graph
        # can show who is being waited on, and an agent can message them without
        # a human first working out who "供应商对接人" is.
        ref = h.get("owner")
        if ref and "/" in str(ref):
            tname, iid = str(ref).split("/", 1)
            rows = s.instances.get(tname)
            if rows is None:
                out.append(f"hook {hname}: owner names unknown type {tname!r}")
            elif not any(r.get(s.types[tname]["id"]) == iid for r in rows):
                out.append(f"hook {hname}: no {tname} with id {iid!r}")
        if not h.get("resolve_when"):
            out.append(f"hook {hname} needs 'resolve_when' — otherwise it can never clear")
        for node in h.get("affects") or []:
            if node not in s.nodes:
                out.append(f"hook {hname} affects {node!r}, which is not a declared node")

    for tname, rows in s.instances.items():
        if tname not in s.types:
            out.append(f"instances declare {tname!r}, which is not a type")
            continue
        # Shape first. A mapping here is almost always a type definition pasted
        # into the wrong section, and without this the first row access raises
        # an AttributeError that says nothing about where to look.
        if not isinstance(rows, list):
            out.append(
                f"instances.{tname} is a {type(rows).__name__}, not a list of rows — "
                f"a type definition may have been pasted under 'instances'"
            )
            continue
        if any(not isinstance(r, dict) for r in rows):
            out.append(f"instances.{tname} has an entry that is not a mapping")
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
                # YAML types bare tokens for you: 2025 becomes an int, 26H1
                # stays a string, and a period filter then matches one and not
                # the other. Refusing here beats coercing, because coercion
                # would hide that the spec and the data disagree.
                if p and p.get("type") == "string" and v is not None and not isinstance(v, str):
                    out.append(
                        f"{tname}[{i}].{pname} = {v!r} is a {type(v).__name__}, not a string — "
                        f"quote it in the YAML, or the value will not match anything"
                    )

    for nname, n in s.nodes.items():
        # A plug absorbs whatever is left over, which makes it the one place a
        # discrepancy can hide without anyone noticing. Declaring what it is
        # measured against, and where its divergence is registered, is what
        # turns "do not silently absorb" from a discipline into a refusal.
        against, residual = n.get("plug_against"), n.get("residual_to")
        if against or residual:
            if not against:
                out.append(f"node {nname}: residual_to needs plug_against — a residual against what?")
            elif against not in s.nodes:
                out.append(f"node {nname}: plug_against {against!r} is not a node")
            if not residual:
                out.append(
                    f"node {nname} is a plug against {against!r} but declares no residual_to — "
                    f"a plug with nowhere to put its difference absorbs it silently"
                )
            elif residual not in s.hooks:
                out.append(f"node {nname}: residual_to {residual!r} is not a hook")
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

    for cname, spec_ in s.checks.items():
        # Either a bare expression (must hold in every period) or a mapping
        # {expr, period}. A total that is only true for the whole ledger would
        # otherwise turn red the moment anyone compiles one period, and a check
        # that cries wolf gets switched off.
        src = spec_.get("expr") if isinstance(spec_, dict) else spec_
        if not isinstance(src, str):
            out.append(f"check {cname} needs an expression (a string, or {{expr, period}})")
            continue
        if isinstance(spec_, dict):
            extra = set(spec_) - {"expr", "period"}
            if extra:
                out.append(f"check {cname} has unknown keys: {sorted(extra)}")
        try:
            expr.parse(src)
        except expr.ExprError as e:
            out.append(f"check {cname} does not parse: {e}")

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
