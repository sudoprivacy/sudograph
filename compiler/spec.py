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

from dataclasses import dataclass, field
from typing import Any

import yaml

from . import expr

OWNERS = ("source", "ontology")
NODE_KINDS = ("raw", "hook", "derived")
OP_CLASSES = ("DerivedOp", "RecordableOp", "BlockedOp")
PROP_TYPES = ("string", "money", "number", "date", "enum", "ref", "bool")

TOP_LEVEL = {
    "ontology", "dimensions", "bases", "bridges", "types", "raw",
    "hooks", "instances", "nodes", "ops", "checks",
}

#: Node keys that may be written per reading, as `<key>@<basis>`.
PER_BASIS = ("op", "because", "entry")


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
    #: Named readings the same structure is computed under — the book figures,
    #: the restated ones, the tax ones. One spec, one set of nodes; only the
    #: expressions that actually differ are written per reading. Two files would
    #: drift.
    #:
    #: A flat list, not a product of dimensions. Two rule axes would give 2^n
    #: complete alternative worlds and n(n-1)/2 bridges between them, of which
    #: only a couple mean anything — and the business does not talk that way
    #: either. Nobody says "the figure under book-basis crossed with new-tax";
    #: they say "the tax figure". So readings are named and enumerated, and the
    #: bridges that are actually deliverables are declared.
    bases: list[str] = field(default_factory=list)
    #: Named axes the facts are partitioned along — reporting period, legal
    #: entity, currency. A dimension *divides* the rows: the 2023 rows and the
    #: 2025 rows are disjoint, and the periods sum to the whole. That is why
    #: there may be any number of them and they compose freely, and it is
    #: exactly what a basis does NOT do — a basis is a complete reading of all
    #: the facts, so bases list rather than multiply.
    dimensions: list[str] = field(default_factory=list)
    #: name -> {from, to}: which pairs of readings produce adjusting entries.
    #: Required once there are more than two readings, because past two "the
    #: difference" stops being obvious and an undeclared bridge is a deliverable
    #: nobody agreed to produce.
    bridges: dict[str, dict] = field(default_factory=dict)

    def owner_of(self, type_name: str, prop: str) -> str | None:
        t = self.types.get(type_name)
        if not t:
            return None
        p = (t.get("props") or {}).get(prop)
        return p.get("owner") if p else None

    def types_with(self, prop: str) -> list[str]:
        return [tn for tn, t in self.types.items() if prop in (t.get("props") or {})]

    def axis_of(self, type_name: str, dim: str) -> str | None:
        """Which property of this type carries `dim`, if it is partitioned by it.

        A type that declares none is reference data — people, suppliers — and is
        never filtered out, because dropping it would break every row that
        points at it.
        """
        return ((self.types.get(type_name) or {}).get("dimensions") or {}).get(dim)

    def reason_for(self, node_name: str, basis: str | None) -> str | None:
        """Why this node reads the way it does under `basis`.

        A reading-specific reason wins; a bare `because` is shorthand for "the
        same reason under every reading that diverges", which is what the common
        two-reading case actually means.
        """
        n = self.nodes.get(node_name) or {}
        if basis and f"because@{basis}" in n:
            return n[f"because@{basis}"]
        return n.get("because")

    def entry_for(self, node_name: str, basis: str | None) -> dict:
        """Where the difference posts when arriving at `basis`."""
        n = self.nodes.get(node_name) or {}
        if basis and f"entry@{basis}" in n:
            return n[f"entry@{basis}"] or {}
        return n.get("entry") or {}

    def sources_of(self, type_name: str, prop: str) -> list[str]:
        """The raws that supply this property. More than one means corroborated."""
        p = ((self.types.get(type_name) or {}).get("props") or {}).get(prop) or {}
        f = p.get("from")
        if isinstance(f, list):
            return list(f)
        return [f] if f else []

    def corroborated(self, type_name: str) -> dict[str, list[str]]:
        """prop -> its independent sources, for the properties that have several.

        A figure asserted by one system is a figure you have taken on trust. The
        whole of audit evidence is that two systems which do not talk to each
        other say the same thing, so the model has to be able to hold both — and
        to notice when they disagree.
        """
        props = (self.types.get(type_name) or {}).get("props") or {}
        return {p: list(d["from"]) for p, d in props.items() if isinstance(d.get("from"), list)}

    def links_of(self, type_name: str) -> dict[str, str]:
        """prop -> the type it points at. Refs to hooks are gaps, not links."""
        props = (self.types.get(type_name) or {}).get("props") or {}
        return {
            p: d["to"]
            for p, d in props.items()
            if d.get("type") == "ref" and d.get("to") not in (None, "hook")
        }

    def ids_of(self, type_name: str) -> set:
        t = self.types.get(type_name) or {}
        rows = self.instances.get(type_name) or []
        idp = t.get("id")
        return {r.get(idp) for r in rows if isinstance(r, dict)} if idp else set()


def load(path: str) -> Spec:
    with open(path, encoding="utf-8") as fh:
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
        bases=doc.get("bases") or [],
        bridges=doc.get("bridges") or {},
        dimensions=doc.get("dimensions") or [],
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

    # Shape before anything reads a row. A mapping under 'instances' is almost
    # always a type definition pasted into the wrong section, and every later
    # check that walks the rows would otherwise raise an AttributeError that
    # points nowhere. Bail out of those checks entirely rather than half-run
    # them against a shape they cannot handle.
    malformed: set[str] = set()
    for tname, rows in s.instances.items():
        if not isinstance(rows, list):
            out.append(
                f"instances.{tname} is a {type(rows).__name__}, not a list of rows — "
                f"a type definition may have been pasted under 'instances'"
            )
            malformed.add(tname)
        elif any(not isinstance(r, dict) for r in rows):
            out.append(f"instances.{tname} has an entry that is not a mapping")
            malformed.add(tname)

    for tname, t in s.types.items():
        # A type names the property carrying each dimension it is partitioned
        # along. One spec then serves every slice: the compiler feeds it
        # different leaves rather than the author duplicating nodes per period.
        axes = t.get("dimensions") or {}
        if not isinstance(axes, dict):
            out.append(f"type {tname}: 'dimensions' must map a dimension name to a property")
            axes = {}
        for dim, col in axes.items():
            if dim not in s.dimensions:
                out.append(f"type {tname}: {dim!r} is not a declared dimension")
            if col not in (t.get("props") or {}):
                out.append(f"type {tname}: dimension {dim!r} names property {col!r}, "
                           f"which is not among its props")
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
            # `from` may be a list, which is how a figure says it is corroborated
            # rather than merely asserted.
            if owner == "source":
                srcs = s.sources_of(tname, pname)
                if not srcs:
                    out.append(f"{where}: source property needs 'from' naming its raw")
                for src in srcs:
                    if src not in s.raw:
                        out.append(f"{where}: 'from' points at unknown raw {src!r}")
                corr = p.get("corroboration") or {}
                if corr and not isinstance(p.get("from"), list):
                    out.append(
                        f"{where}: 'corroboration' needs more than one source in 'from' — "
                        f"one system agreeing with itself corroborates nothing"
                    )
                extra = set(corr) - {"at_least", "prefer"}
                if extra:
                    out.append(f"{where}: corroboration has unknown keys: {sorted(extra)}")
                at_least = corr.get("at_least", 1)
                if not isinstance(at_least, int) or at_least < 1:
                    out.append(f"{where}: corroboration.at_least must be a positive integer")
                elif at_least > len(srcs):
                    out.append(
                        f"{where}: corroboration.at_least is {at_least} but only "
                        f"{len(srcs)} source(s) are declared — it can never be met"
                    )
                if corr.get("prefer") and corr["prefer"] not in srcs:
                    out.append(
                        f"{where}: corroboration.prefer names {corr['prefer']!r}, "
                        f"which is not among its sources"
                    )
            if owner == "ontology" and p.get("from"):
                out.append(f"{where}: ontology property cannot have 'from' — it is not upstream")
            if p.get("type") == "enum" and not p.get("values"):
                out.append(f"{where}: an enum needs 'values'")
            # A ref is how one object reaches another. Until now the only thing
            # one could reach was a hook, which meant the graph had gaps as
            # first-class citizens and relationships as nothing at all — and a
            # relationship is most of what an audit is: this payment against
            # that supplier, this entity inside that consolidation.
            if p.get("type") == "ref":
                target = p.get("to")
                if not target:
                    out.append(f"{where}: a ref needs 'to' — a type name, or 'hook'")
                elif target != "hook" and target not in s.types:
                    out.append(
                        f"{where}: ref points at {target!r}, which is neither a declared "
                        f"type nor 'hook'"
                    )
                # The same ambiguity as a nullable number, one level over: "not
                # matched yet" and "determined to have no counterpart" look
                # identical in the data and mean opposite things. One is work
                # outstanding, the other is a finding.
                elif (
                    target != "hook"
                    and p.get("nullable")
                    and p.get("absent") not in ("gap", "none")
                ):
                    out.append(
                        f"{where}: a nullable ref must declare absent: 'gap' "
                        f"(not matched yet) or 'none' (determined to have no counterpart)"
                    )
            # A nullable number is ambiguous unless the spec says what absence
            # means. "not recorded yet" and "determined to be zero" look the
            # same in the data and are opposite in the business: one is a gap
            # to chase, the other is a finding. Saying which is cheap here and
            # impossible to recover later.
            numeric_and_nullable = p.get("nullable") and p.get("type") in ("money", "number")
            if numeric_and_nullable and p.get("absent") not in ("gap", "zero"):
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
            elif tname in malformed or tname not in s.types:
                pass  # already reported; do not compound one fault with another
            elif not any(r.get(s.types[tname]["id"]) == iid for r in rows):
                out.append(f"hook {hname}: no {tname} with id {iid!r}")
        if not h.get("resolve_when"):
            out.append(f"hook {hname} needs 'resolve_when' — otherwise it can never clear")
        for node in h.get("affects") or []:
            if node not in s.nodes:
                out.append(f"hook {hname} affects {node!r}, which is not a declared node")

    # Past two readings, "the difference" stops being obvious: three readings
    # offer three pairings and only some of them are anything anyone wants. An
    # undeclared bridge is a deliverable nobody agreed to produce.
    if len(s.bases) > 2 and not s.bridges:
        out.append(
            f"{len(s.bases)} readings are declared but no 'bridges' — "
            f"say which pairs produce adjusting entries; with more than two, "
            f"'the difference' is no longer a single thing"
        )
    seen_pairs: dict[tuple[str, str], str] = {}
    for bname, b in s.bridges.items():
        if not isinstance(b, dict):
            out.append(f"bridge {bname} must be a mapping with 'from' and 'to'")
            continue
        extra = set(b) - {"from", "to", "label"}
        if extra:
            out.append(f"bridge {bname} has unknown keys: {sorted(extra)}")
        a, z = b.get("from"), b.get("to")
        for end, which in ((a, "from"), (z, "to")):
            if end is None:
                out.append(f"bridge {bname} needs '{which}'")
            elif end not in s.bases:
                out.append(f"bridge {bname}: {which} {end!r} is not a declared reading")
        if a is not None and a == z:
            out.append(f"bridge {bname}: from and to are both {a!r} — that bridges nothing")
        elif a is not None and z is not None:
            if (a, z) in seen_pairs:
                out.append(
                    f"bridge {bname} spans the same pair as {seen_pairs[(a, z)]!r} — "
                    f"one pair, one bridge, or two names disagree about one deliverable"
                )
            seen_pairs[(a, z)] = bname

    for tname, rows in s.instances.items():
        if tname not in s.types:
            out.append(f"instances declare {tname!r}, which is not a type")
            continue
        if tname in malformed:
            continue
        t = s.types[tname]
        idp = t.get("id")
        seen: set[Any] = set()
        corr = s.corroborated(tname)
        for i, row in enumerate(rows):
            # A corroborated figure is written once per source — 金额@R-KINGDEE,
            # 金额@R-LEDGER — because the point is that two systems said it
            # independently. Writing it bare as well would create a third value
            # with no source, which is the thing corroboration exists to prevent.
            per_source: set[str] = set()
            for key in row:
                if "@" not in key:
                    continue
                prop, _, src = key.partition("@")
                if prop not in corr:
                    continue
                per_source.add(key)
                if src not in corr[prop]:
                    out.append(
                        f"{tname}[{i}].{key}: {src!r} is not among the sources declared "
                        f"for {prop} ({corr[prop]})"
                    )
            for prop in corr:
                if prop in row:
                    out.append(
                        f"{tname}[{i}].{prop} is written bare, but it is corroborated by "
                        f"{corr[prop]} — write {prop}@<raw> per source, so the compiler can "
                        f"tell whether they agree"
                    )
            unknown = set(row) - set(t.get("props") or {}) - per_source
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
                out.append(
                    f"node {nname}: residual_to needs plug_against — a residual against what?"
                )
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
        # A node may compute differently under each basis. Everything about a
        # divergence is refused unless it is explained, because a divergence is
        # exactly what becomes an adjusting entry: an unexplained one is an
        # unexplained restatement, and those are what an auditor is looking for.
        for k in n:
            key, _, named = k.partition("@")
            if named and key in PER_BASIS and named not in s.bases:
                out.append(f"node {nname}: {k} names a reading not listed in 'bases'")
        diverges = any(f"op@{b}" in n for b in s.bases)
        for b in s.bases:
            key = f"op@{b}"
            if key in n:
                try:
                    expr.parse(n[key])
                except expr.ExprError as e:
                    out.append(f"node {nname}: {key} does not parse: {e}")
            elif diverges and not n.get("op"):
                # Silence under one basis is ambiguous in the same way a null
                # money column is: "nil under the book figures" and "we have not
                # worked this one out" look identical and mean opposite things.
                # Writing op@<basis>: "0" says the first out loud.
                out.append(
                    f"node {nname}: diverges by basis but has no expression under {b!r} — "
                    f"give it one, or write op@{b}: \"0\" if it is genuinely nil there"
                )
        # Every reading this node computes differently under owes a reason. With
        # two readings one bare `because` says it; past that, each reading gets
        # its own, because "why is the restated figure different" and "why is the
        # tax figure different" are not the same answer.
        provenance = set(s.raw) | set(s.hooks)
        if not diverges:
            for stray in [k for k in n if k.partition("@")[0] in ("because", "entry")]:
                out.append(
                    f"node {nname}: has {stray!r} but computes the same under every reading"
                )
        for b in s.bases:
            if f"op@{b}" not in n:
                continue
            reason = s.reason_for(nname, b)
            if not reason:
                out.append(
                    f"node {nname}: reads differently under {b!r} but declares no reason — "
                    f"write because@{b} (or a bare 'because' if every reading shares one). "
                    f"The difference becomes an adjusting entry, and an entry needs a reason"
                )
            elif reason not in provenance:
                out.append(f"node {nname}: because for {b!r} is {reason!r}, not a raw or a hook")
            # Both sides or neither: a one-sided entry does not balance, and half
            # an entry posted into a ledger is worse than none.
            entry = s.entry_for(nname, b)
            if entry and not (entry.get("debit") and entry.get("credit")):
                out.append(f"node {nname}: entry for {b!r} needs both 'debit' and 'credit'")
        if n.get("kind") == "derived":
            if not n.get("op") and not diverges:
                out.append(f"derived node {nname} needs an 'op'")
            elif n.get("op"):
                try:
                    expr.parse(n["op"])
                except expr.ExprError as e:
                    out.append(f"node {nname}: op does not parse: {e}")

    for cname, spec_ in s.checks.items():
        # Either a bare expression (must hold in every slice) or a mapping
        # {expr, at}. A total that is only true for the whole ledger would
        # otherwise turn red the moment anyone compiles one period, and a check
        # that cries wolf gets switched off.
        src = spec_.get("expr") if isinstance(spec_, dict) else spec_
        if not isinstance(src, str):
            out.append(f"check {cname} needs an expression (a string, or {{expr, at}})")
            continue
        if isinstance(spec_, dict):
            extra = set(spec_) - {"expr", "at", "basis"}
            if extra:
                out.append(f"check {cname} has unknown keys: {sorted(extra)}")
            if "basis" in spec_ and spec_["basis"] not in s.bases:
                out.append(
                    f"check {cname}: basis {spec_['basis']!r} is not a declared reading"
                )
            at = spec_.get("at")
            if "at" in spec_ and not isinstance(at, dict):
                out.append(f"check {cname}: 'at' must map dimension names to values")
            elif isinstance(at, dict):
                for dim in at:
                    if dim not in s.dimensions:
                        out.append(f"check {cname}: {dim!r} is not a declared dimension")
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
