"""Two bases, one structure: the adjusting entries fall out of the difference.

An audit restatement is two sets of figures over the same business — what the
books say, and what they should say. The usual way to hold both is two documents
and a hand-written list of adjusting entries reconciling them. Then the entries
drift: someone changes a figure on one side, the entry still reads as it did,
and the reconciliation is fiction that balances.

Here the two sets share one set of nodes. Only the expressions that genuinely
differ are written twice, and the entries are *computed* from that difference
rather than transcribed. You cannot change one side without the entry moving.

Two kinds of difference, and telling them apart is the whole value:

  * an **entry** is a node whose expression itself differs between the bases.
    This is where the restatement is decided, so this is where it is booked, and
    `because` says on whose authority.
  * a **carried** difference is a node whose expression is identical under both
    bases but whose value differs anyway, because something upstream did. It is
    a consequence, not a decision. Booking it too would double-count it, and
    every total in the graph would look like its own separate adjustment.

`origins` on a carried difference names the entries that caused it, which is the
question a reviewer actually asks: *this total moved — which adjustment moved it?*
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import compile as compile_mod
from . import lineage as lin_mod
from .spec import Spec


@dataclass
class Entry:
    """One adjusting entry: a decided divergence, with its reason and its sides."""

    node: str
    label: str
    before: Any
    after: Any
    amount: Any
    because: str | None = None
    debit: str | None = None
    credit: str | None = None
    ops: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "node": self.node,
            "label": self.label,
            "before": self.before,
            "after": self.after,
            "amount": self.amount,
            "because": self.because,
            "debit": self.debit,
            "credit": self.credit,
            "ops": self.ops,
        }


@dataclass
class Carried:
    """A figure that moved because an entry upstream moved it."""

    node: str
    label: str
    before: Any
    after: Any
    amount: Any
    origins: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "node": self.node,
            "label": self.label,
            "before": self.before,
            "after": self.after,
            "amount": self.amount,
            "origins": self.origins,
        }


@dataclass
class Diff:
    ontology: str
    bases: tuple[str, str]
    period: str | None = None
    entries: list[Entry] = field(default_factory=list)
    carried: list[Carried] = field(default_factory=list)
    #: Differences with no entry anywhere above them. A figure that moved for no
    #: recorded reason is the one outcome this module exists to make impossible,
    #: so it is reported rather than rendered as just another number.
    unexplained: list[str] = field(default_factory=list)

    @property
    def explained(self) -> bool:
        return not self.unexplained

    def total(self) -> Any:
        """Every entry. Carried differences are excluded: they are these amounts
        again, seen further down the graph, and adding them would double-count."""
        return sum(e.amount for e in self.entries if isinstance(e.amount, (int, float)))

    def posted(self) -> Any:
        """Only the entries that name where they post.

        A divergence can be real and still not be a journal entry — a memo
        figure such as "how much is waiting on materials" exists under one basis
        and not the other, and nothing in a ledger moves for it. Totalling those
        alongside real postings would report a net effect that no account shows.
        """
        return sum(
            e.amount
            for e in self.entries
            if e.debit and e.credit and isinstance(e.amount, (int, float))
        )

    def as_dict(self) -> dict:
        return {
            "ontology": self.ontology,
            "bases": list(self.bases),
            "period": self.period,
            "entries": [e.as_dict() for e in self.entries],
            "carried": [c.as_dict() for c in self.carried],
            "unexplained": self.unexplained,
            "total": self.total(),
            "posted": self.posted(),
        }


def _differs(a: Any, b: Any) -> bool:
    if a is None and b is None:
        return False
    return a != b


def diff(
    s: Spec,
    before: str,
    after: str,
    *,
    period: str | None = None,
    fold_over: int = 20,
    top_n: int = 5,
) -> Diff:
    """Compile under both bases and derive the entries between them.

    Both compiles run over the same spec object, so there is no version of this
    where the two sides describe different structures — which is the failure two
    files would eventually have.
    """
    for b in (before, after):
        if b not in s.bases:
            raise ValueError(f"unknown basis {b!r}; the spec declares {s.bases}")

    ca = compile_mod.compile_spec(s, period=period, basis=before, fold_over=fold_over, top_n=top_n)
    cb = compile_mod.compile_spec(s, period=period, basis=after, fold_over=fold_over, top_n=top_n)

    d = Diff(ontology=s.name, bases=(before, after), period=period)

    # Where the author wrote two expressions, the restatement was decided.
    decided: set[str] = set()
    for name, node in s.nodes.items():
        op_a = compile_mod.op_for(node, before)
        op_b = compile_mod.op_for(node, after)
        if op_a == op_b:
            continue
        decided.add(name)
        va, vb = ca.values.get(name), cb.values.get(name)
        amount = vb - va if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else None
        entry = node.get("entry") or {}
        d.entries.append(
            Entry(
                node=name,
                label=node.get("label", name),
                before=va,
                after=vb,
                amount=amount,
                because=node.get("because"),
                debit=entry.get("debit"),
                credit=entry.get("credit"),
                ops={before: op_a, after: op_b},
            )
        )

    # Everything else that moved, moved because one of those did. Attribute it
    # rather than book it. Ancestry is taken under both bases and unioned: an
    # entry can feed a total under one basis and not the other, and dropping it
    # on that ground would leave the total looking unexplained.
    lin_a = lin_mod.lineage(s, before)
    lin_b = lin_mod.lineage(s, after)
    for name in s.nodes:
        if name in decided:
            continue
        va, vb = ca.values.get(name), cb.values.get(name)
        if not _differs(va, vb):
            continue
        ancestors = set(lin_a[name]["ancestors"]) | set(lin_b[name]["ancestors"])
        origins = sorted(ancestors & decided)
        amount = vb - va if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else None
        d.carried.append(
            Carried(
                node=name,
                label=s.nodes[name].get("label", name),
                before=va,
                after=vb,
                amount=amount,
                origins=origins,
            )
        )
        if not origins:
            d.unexplained.append(name)

    d.entries.sort(key=lambda e: e.node)
    d.carried.sort(key=lambda c: c.node)
    return d
