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

import os
from dataclasses import dataclass, field
from typing import Any

import yaml

from . import bind as bind_mod
from . import expr

OWNERS = ("source", "ontology")
#: The kinds a node can be. Not a field anyone writes: the block a thing is
#: declared in says which one it is — `raw:` a reading taken from a system,
#: `hooks:` something missing, `nodes:` something computed — and each block
#: requires different fields, so a thing put in the wrong one fails on the
#: fields rather than on a label. Asking for the kind as well meant the same
#: fact was stated twice and could disagree with itself: a node in `nodes:`
#: declaring `kind: raw` passed check() and was then silently never computed.
NODE_KINDS = ("raw", "hook", "derived")
OP_CLASSES = ("DerivedOp", "RecordableOp", "BlockedOp")
PROP_TYPES = ("string", "money", "number", "date", "enum", "ref", "bool")

TOP_LEVEL = {
    "ontology", "dimensions", "bases", "bridges", "types", "raw",
    "hooks", "instances", "nodes", "ops", "checks",
}

#: Node keys that may be written per reading, as `<key>@<basis>`.
#: Keys a node may carry beyond its expressions.
NODE_EXTRA_KEYS = ("conversion",)

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
    #: name -> {from, to}: which pairs of readings produce entries, plus what a
    #: crossing is *called* here (see BRIDGE_VOCAB) and which `slots` an entry
    #: fills. Audit says "adjusting entry", "post", debit and credit; a budget
    #: revision says "variance" and names one pool. Neither is the compiler's to
    #: assume, so the words travel with the spec like every other label, and the
    #: renderer reads them instead of spelling one domain into the UI.
    #: Required once there are more than two readings, because past two "the
    #: difference" stops being obvious and an undeclared bridge is a deliverable
    #: nobody agreed to produce.
    bridges: dict[str, dict] = field(default_factory=dict)
    #: Where the spec was read from. A backing's dsn is written relative to the
    #: spec, because a spec and the database it reads travel together — not
    #: relative to whichever directory the compiler happened to be run in.
    source_base: str = "."
    #: Backed types too large to hold, kept as a row count. Their aggregates are
    #: answered by the database; anything that needs the rows themselves refuses
    #: rather than quietly working on none of them.
    unloaded: dict[str, int] = field(default_factory=dict)

    def owner_of(self, type_name: str, prop: str) -> str | None:
        t = self.types.get(type_name)
        if not t:
            return None
        p = (t.get("props") or {}).get(prop)
        if not p:
            return None
        # A formula is a decision of ours, so a computed property is
        # ontology-owned without having to say so.
        return "ontology" if "op" in p else p.get("owner")

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

    def slots_arriving_at(self, basis: str | None) -> list[list[str]]:
        """The slot sets declared by the bridges that end at this reading."""
        return [
            list(b["slots"])
            for b in self.bridges.values()
            if isinstance(b, dict) and b.get("to") == basis and b.get("slots")
        ]

    def vocab_for(self, before: str | None, after: str | None) -> dict[str, str]:
        """What the bridge between these two readings calls what it produces."""
        for b in self.bridges.values():
            if isinstance(b, dict) and b.get("from") == before and b.get("to") == after:
                return bridge_vocab(b)
        return bridge_vocab(None)

    def backing_of(self, type_name: str) -> dict:
        """The table this type is a view over, if it is one."""
        return (self.types.get(type_name) or {}).get("backing") or {}

    def id_props(self, type_name: str) -> list[str]:
        """The properties that name one row of this type.

        A type that is a view over a table already said what identifies a row,
        in `backing.key`, so repeating it as `id` is the same fact written
        twice — and a fact written twice can disagree with itself. It did: a
        fact table's key is nearly always two columns, `id` took one, and rows
        quietly collapsed onto each other on the canvas.
        """
        t = self.types.get(type_name) or {}
        if t.get("id"):
            return [t["id"]]
        back = {self.column_of(type_name, p): p for p in (t.get("props") or {})}
        return [back[c] for c in ((t.get("backing") or {}).get("key") or []) if c in back]

    def identify(self, type_name: str, row: dict) -> str:
        """What this row is called. One property, or the key's values joined."""
        parts = [row.get(p) for p in self.id_props(type_name)]
        return parts[0] if len(parts) == 1 else "·".join(str(x) for x in parts)

    def column_of(self, type_name: str, prop: str) -> str:
        """The upstream column behind a property; its own name when unmapped.

        Defaulting to the property name is what keeps a spec readable when the
        upstream happens to agree, without making the two the same thing — a
        system that calls it FBillNo still maps cleanly.
        """
        p = ((self.types.get(type_name) or {}).get("props") or {}).get(prop) or {}
        return p.get("column") or prop

    def sources_of(self, type_name: str, prop: str) -> list[str]:
        """The raws that supply this property. More than one means corroborated."""
        p = ((self.types.get(type_name) or {}).get("props") or {}).get(prop) or {}
        f = p.get("from")
        if isinstance(f, list):
            return list(f)
        if f:
            return [f]
        # A type that is a view over a table does not repeat the source on every
        # column. Saying it once on the backing is the whole point; `from` stays
        # available for the column that genuinely comes from somewhere else,
        # which is how corroboration is expressed.
        backing = self.backing_of(type_name)
        return [backing["from"]] if backing.get("from") else []

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
        rows = self.instances.get(type_name) or []
        return {self.identify(type_name, r) for r in rows if isinstance(r, dict)}


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

    # A type that is a view over a table is unusable without the table, and a
    # compile over zero rows would answer every question with nothing rather
    # than refusing. So the binding is compared against the live schema here, at
    # the only entrance, and the rows arrive with it.
    #
    # This is what makes "a binding is not a copy" enforceable rather than
    # merely stated: a copy cannot be wrong about its source, only out of date,
    # and nothing can tell you which.
    if any(s.backing_of(t) for t in s.types):
        base = os.path.dirname(os.path.abspath(path))
        broken = bind_mod.verify(s, base)
        if broken:
            raise SpecError(
                "the spec claims things the source does not say:\n  - "
                + "\n  - ".join(broken)
            )
        s = bind_mod.bind_all(s, base)
    return s


#: What a bridge calls the things a crossing produces. Every one of these is a
#: word some domain uses and another does not, which is why they are declared
#: rather than written into the renderer. The defaults say only what is
#: structurally true, so an undeclared spec reads plainly instead of reading as
#: accounting.
BRIDGE_VOCAB = {
    "entry_noun": "差异",       # a difference someone decided
    "posted_noun": "合计",      # the sum of the ones that land somewhere
    "carried_noun": "连带差异",  # a difference something upstream caused
}


def bridge_vocab(b: dict | None) -> dict[str, str]:
    """A bridge's own words, filled in with the structurally-true ones."""
    b = b or {}
    return {k: (b.get(k) or d) for k, d in BRIDGE_VOCAB.items()}


#: A figure written into a formula is a decision nobody can reach: it cannot be
#: pointed at, commented on, cited, or varied by reading. Every one of those is
#: something this model exists to make possible, so a bare number is refused
#: where it hides and named where it belongs.
#:
#: The exemption is declared, never guessed. `/ 100` really is mechanical and
#: `* 0.15` really is a policy, and nothing about the two numbers tells them
#: apart — only a person knows, so a person says, once, on the constant.
def _hidden_judgement(owner: str, holder: dict, bases: list) -> list[str]:
    out: list[str] = []
    for key, src in holder.items():
        if key != "op" and not key.startswith("op@"):
            continue
        if not isinstance(src, str):
            continue
        try:
            ast = expr.parse(src)
        except expr.ExprError:
            continue
        if isinstance(ast, expr.Lit):
            continue          # a bare constant is the named case, handled above
        for lit in expr.numeric_literals(ast):
            out.append(
                f"{owner}: {key} hides the number {lit} inside a formula. A figure "
                f"written into an expression cannot be pointed at, commented on, or "
                f"varied by reading — give it a name of its own with its evidence, "
                f"then refer to it. If it is a unit conversion, name it anyway and "
                f"mark it conversion: <what it converts>"
            )
    return out


def _is_literal(n: dict) -> bool:
    """True when every expression this node carries is a bare constant."""
    srcs = [v for k, v in n.items() if k == "op" or k.startswith("op@")]
    if not srcs:
        return False
    for src in srcs:
        try:
            if not isinstance(expr.parse(src), expr.Lit):
                return False
        except expr.ExprError:
            return False
    return True


#: What a type's `backing` may say. The table is named, not described: nothing
#: here restates what the database already knows — column types, indexes, which
#: foreign keys exist. Those are read back and compared, because a fact we write
#: down that the source also holds is a fact that can drift. What is written is
#: what the database cannot answer: which table carries this business object,
#: which columns identify a row of it, and which rows belong to it at all.
BACKING_KEYS = ("from", "table", "key", "where")


def _backing_problems(s: Spec, tname: str, t: dict) -> list[str]:
    b = t.get("backing")
    if b is None:
        return []
    out: list[str] = []
    if not isinstance(b, dict):
        return [f"type {tname}: backing must be a mapping with 'from', 'table' and 'key'"]
    extra = set(b) - set(BACKING_KEYS)
    if extra:
        out.append(f"type {tname}: backing has unknown keys: {sorted(extra)}")
    if s.instances.get(tname):
        out.append(
            f"type {tname} is backed by a table and also carries rows inline — one of "
            f"them is a copy, and the copy is the one that goes stale"
        )
    src = b.get("from")
    if not src:
        out.append(f"type {tname}: backing needs 'from' naming the raw it reads through")
    elif src not in s.raw:
        out.append(f"type {tname}: backing reads through unknown raw {src!r}")
    elif not s.raw[src].get("dsn"):
        out.append(
            f"type {tname}: backing reads through {src!r}, which declares no 'dsn' — "
            f"a raw that backs a table is a database, not a command"
        )
    if not b.get("table"):
        out.append(f"type {tname}: backing needs 'table'")
    key = b.get("key")
    props = t.get("props") or {}
    if not isinstance(key, list) or not key:
        out.append(
            f"type {tname}: backing needs 'key' — the columns that identify one row. "
            f"Without it two rows of the source are indistinguishable here"
        )
    else:
        mapped = {s.column_of(tname, pn) for pn in props}
        for col in key:
            if col not in mapped:
                out.append(
                    f"type {tname}: key column {col!r} is not behind any property — "
                    f"a row cannot be identified by something the ontology cannot see"
                )
    # Two objects may share one table, which is the point of binding rather than
    # mirroring: Orders carries an order and a shipment, and they are not the
    # same thing to anyone in the business.
    return out


def _computed_prop_problems(s: Spec, tname: str, pname: str, p: dict) -> list[str]:
    """A property whose value is generated rather than stored.

    Two shapes, one mechanism. Over the row's own columns it is arithmetic —
    `金额_含税 / (1 + 进项税率)`. Over related rows it is the aggregate this
    language already has, with `this` standing for the row being computed —
    `select sum(金额) from 委外合同 where 供应商 = this`. The second is what
    other ontologies model as a separate "derived property" declaration of
    fixed shape; reusing the expression language covers it without a second
    thing to learn, validate, and answer the same question differently.

    The rule that matters is the one the whole file exists for: a relationship
    must be **generated**, never **synchronised**. A figure written out by hand
    beside a prose note saying how it was obtained is a synchronisation — change
    one side and nothing tells you the other is now wrong.
    """
    if "op" not in p:
        return []
    out: list[str] = []
    where = f"{tname}.{pname}"
    if not isinstance(p["op"], str) or not p["op"].strip():
        return [f"{where}: op must be an expression"]
    try:
        ast = expr.parse(p["op"])
    except expr.ExprError as e:
        return [f"{where}: op does not parse: {e}"]

    if p.get("from"):
        out.append(f"{where}: a computed property cannot have 'from' — it is not upstream")
    if "column" in p:
        out.append(f"{where}: a computed property cannot also bind a source column; drop 'column'")

    # Written out per row *and* computed is the contradiction this exists to
    # remove: one of them is stale the moment the other changes.
    written = [r for r in s.instances.get(tname, []) if pname in r]
    if written:
        out.append(
            f"{where}: {len(written)} row(s) also write this by hand — a computed "
            f"property is generated, and a value beside the formula is the copy "
            f"that goes stale"
        )

    # Names must resolve to something: a sibling column, a node, or `this`.
    props = set((s.types.get(tname) or {}).get("props") or {})
    known = props | set(s.nodes) | {"this"}
    for name in expr.referenced_names(ast):
        if name not in known:
            out.append(
                f"{where}: op names {name!r}, which is neither a property of "
                f"{tname} nor a computed node"
            )
    out += _hidden_judgement(where, p, s.bases)
    if "this" in expr.referenced_names(ast) and not s.id_props(tname):
        out.append(f"{where}: op uses 'this' but {tname} declares no 'id' for it to mean")
    return out


def _entry_problems(s: Spec, nname: str, basis: str) -> list[str]:
    """Where a decided difference lands, checked against the bridge's own slots.

    An entry that names nowhere is legitimate — a memo figure exists under one
    reading and nothing moves for it — so `posts` is optional. What is not
    optional is filling the slots the bridge declared: accounting needs both
    halves or the entry does not balance, and a spec that declares three slots
    needs three. Declaring them is what makes the check possible without the
    compiler knowing any one domain's arity.
    """
    entry = s.entry_for(nname, basis)
    if not entry:
        return []
    out: list[str] = []
    for gone, now in (("debit", "posts"), ("credit", "posts")):
        if gone in entry:
            return [
                f"node {nname}: entry for {basis!r} uses {gone!r} — write "
                f"{now}: {{<slot>: <where>}} instead, naming the slots this "
                f"ontology's bridge declares"
            ]
    extra = set(entry) - {"posts"}
    if extra:
        out.append(f"node {nname}: entry for {basis!r} has unknown keys: {sorted(extra)}")
    posts = entry.get("posts")
    if posts is None:
        return out
    if not isinstance(posts, dict) or not posts:
        out.append(
            f"node {nname}: entry for {basis!r} has an empty 'posts' — drop it to mean "
            f"the difference lands nowhere, which is a different statement from "
            f"landing in no named place"
        )
        return out
    if not all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in posts.items()):
        out.append(f"node {nname}: entry for {basis!r}: every slot must name where it lands")
        return out
    wanted = s.slots_arriving_at(basis)
    if wanted and not any(set(posts) == set(w) for w in wanted):
        out.append(
            f"node {nname}: entry for {basis!r} fills {sorted(posts)} but the bridge "
            f"declares {sorted(wanted[0])} — a partly filled entry is worse than none"
        )
    return out


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
        for req in ("label", "props"):
            if req not in t:
                out.append(f"type {tname} is missing '{req}'")
        if not s.id_props(tname):
            out.append(
                f"type {tname} is missing 'id' — say which property names one row. "
                f"A type that is a view over a table may leave it out and take its "
                f"backing's key instead, which is usually the honest answer for a "
                f"table whose rows need two columns to tell apart"
            )
        props = t.get("props") or {}
        if t.get("id") and t["id"] not in props:
            out.append(f"type {tname}: id property {t['id']!r} is not among its props")
        out += _backing_problems(s, tname, t)
        for pname, p in props.items():
            where = f"{tname}.{pname}"
            if p.get("type") not in PROP_TYPES:
                out.append(f"{where}: type {p.get('type')!r} is not one of {PROP_TYPES}")
            # A computed property is ontology-owned by construction: a formula
            # is a decision of ours, and nothing upstream can supply it. So the
            # owner is read off the shape rather than asked for again — the same
            # fact stated twice is a fact that can disagree with itself.
            owner = s.owner_of(tname, pname)
            if "op" in p and "owner" in p:
                out.append(
                    f"{where}: drop 'owner' — a property with an 'op' is computed here, "
                    f"so it is owned here. Declaring it again is the one place the two "
                    f"could disagree"
                )
            elif "op" not in p and owner not in OWNERS:
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
            # A column may account for all of its own absences. Rows read from
            # someone else's table carry no gap reference of ours, so without
            # this a backed type could never satisfy the absence rule — and the
            # rule is right, so the declaration moves rather than the rule.
            if "gap" in p:
                if p["gap"] not in s.hooks:
                    out.append(f"{where}: gap {p['gap']!r} is not a declared hook")
                elif not p.get("nullable"):
                    out.append(
                        f"{where}: declares a gap for its absences but is not nullable — "
                        f"it has none"
                    )
                elif p.get("absent") != "gap":
                    out.append(
                        f"{where}: names a gap but absent is {p.get('absent')!r}; a gap "
                        f"accounts for 'not recorded yet', not for a determined nil"
                    )
            if "scale" in p:
                if p.get("type") != "money":
                    out.append(f"{where}: 'scale' is how a money column is rounded")
                elif not isinstance(p["scale"], int) or p["scale"] < 0:
                    out.append(f"{where}: scale must be a non-negative whole number")
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
            out += _computed_prop_problems(s, tname, pname, p)
            numeric_and_nullable = p.get("nullable") and p.get("type") in ("money", "number")
            if numeric_and_nullable and p.get("absent") not in ("gap", "zero"):
                out.append(
                    f"{where}: a nullable {p['type']} must declare absent: "
                    f"'gap' (not recorded yet) or 'zero' (determined to be none)"
                )

    for rname, r in s.raw.items():
        if not r.get("connector") and not r.get("dsn"):
            out.append(
                f"raw {rname} needs a 'connector' (one executable command) or a 'dsn' "
                f"(a database the types read through)"
            )
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
            if tname not in s.types:
                out.append(f"hook {hname}: owner names unknown type {tname!r}")
            elif s.backing_of(tname):
                pass  # Resolved against the source after structural validation.
            elif tname in malformed or tname not in s.types:
                pass  # already reported; do not compound one fault with another
            elif not any(str(s.identify(tname, r)) == iid for r in (rows or [])):
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
            f"say which pairs are deliverables; with more than two, "
            f"'the difference' is no longer a single thing"
        )
    seen_pairs: dict[tuple[str, str], str] = {}
    for bname, b in s.bridges.items():
        if not isinstance(b, dict):
            out.append(f"bridge {bname} must be a mapping with 'from' and 'to'")
            continue
        extra = set(b) - {"from", "to", "label", "slots", *BRIDGE_VOCAB}
        if extra:
            out.append(f"bridge {bname} has unknown keys: {sorted(extra)}")
        for word in BRIDGE_VOCAB:
            if word in b and not (isinstance(b[word], str) and b[word].strip()):
                out.append(f"bridge {bname}: {word} must be a non-empty name")
        slots = b.get("slots")
        if slots is not None:
            if not isinstance(slots, list) or not slots:
                out.append(
                    f"bridge {bname}: slots must be a non-empty list of the places an "
                    f"entry fills, e.g. [debit, credit]"
                )
            elif not all(isinstance(x, str) and x.strip() for x in slots):
                out.append(f"bridge {bname}: every slot must be a non-empty name")
            elif len(set(slots)) != len(slots):
                out.append(f"bridge {bname}: slots repeat: {slots}")
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
            elif nname not in (s.hooks[residual].get("affects") or []):
                # The remainder lands in that gap, so that gap is exactly what
                # keeps this figure provisional. Requiring it to say so means
                # the relation is drawn once, in one direction, instead of the
                # graph carrying an arrow each way between the same pair.
                out.append(
                    f"hook {residual} takes {nname}'s residual but does not list it in "
                    f"'affects' — a figure carrying an unexplained remainder is "
                    f"provisional on that gap by definition"
                )
        if "kind" in n:
            out.append(
                f"node {nname}: drop 'kind' — everything under 'nodes' is computed. "
                f"A reading taken from a system goes in 'raw', something missing goes "
                f"in 'hooks'; the block says which it is"
            )
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
        seen_rest: set[str] = set()
        # A node whose expression is a bare literal has no inputs, so nothing
        # upstream can account for it. A figure decided rather than computed —
        # a rate, a threshold, a materiality level — is exactly where a magic
        # number hides, so the citation is not optional there and the divergence
        # rule below does not apply to it.
        literal = _is_literal(n)
        if literal and not n.get("conversion") and not s.reason_for(nname, None) and not any(
            s.reason_for(nname, b) for b in (s.bases or [None])
        ):
            out.append(
                f"node {nname} is a decided figure, not a computed one — cite the raw "
                f"or hook it rests on with 'because'. A number with no inputs and no "
                f"evidence is the thing this model exists to refuse. If it is a unit "
                f"conversion rather than a judgement, say so with "
                f"conversion: <what it converts>"
            )
        if n.get("conversion") and not literal:
            out.append(
                f"node {nname}: 'conversion' says a bare constant is mechanical, but "
                f"this one computes something — drop it"
            )
        out += _hidden_judgement(nname, n, s.bases)
        if not diverges and not literal:
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
            elif (
                reason in s.hooks
                and nname not in (s.hooks[reason].get("affects") or [])
                and f"{nname}|{reason}" not in seen_rest
            ):
                seen_rest.add(f"{nname}|{reason}")
                # One relation, declared once. The hook says what it holds up;
                # the node says what it rests on. Where they are the same pair
                # they must agree, or the canvas gets an arrow each way.
                out.append(
                    f"node {nname} rests on {reason}, but that hook does not list it in "
                    f"'affects' — the same relation has to be declared from one side"
                )
            out += _entry_problems(s, nname, b)
        if not n.get("op") and not diverges:
            out.append(f"node {nname} needs an 'op' — everything under 'nodes' is computed")
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
