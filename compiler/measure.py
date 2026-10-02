"""Measure the ontology against the data it claims to describe.

Two axes, from the design page: whether the graph agrees with the source, and
whether an agent reading only the graph can answer business questions. This
module owns the first and leaves a place for the second.

**The questions are generated, not written.** A hand-written question set drifts
the moment the ontology changes — someone edits a metric and the question still
asks the old thing, passing for a reason nobody notices. Generated ones follow
the spec by construction: add a metric and it is measured, change its filter and
the question changes with it. There is also no upper bound on how many there
are, which a hand-written hundred has by definition.

Three refusals are built in rather than written down, because the ways this kind
of harness goes wrong are known in advance:

  * **A score never gates anything.** The exit code reports whether the harness
    ran, never how well the ontology did. Measurement that can block a change
    stops being measurement and becomes a thing people route around — and a
    falling score is something to explain, not something to suppress.
  * **A result without a trace is refused.** Not warned about: refused. A score
    you cannot retrace tells you a number and nothing about where to look, and
    the whole value of a failure is knowing which edge to go and fix.
  * **Measuring cannot change what is measured.** The spec is fingerprinted
    before and after; a run that altered it is discarded rather than reported.
    A harness that edits the ontology to make its own numbers go up is not
    measuring anything.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from . import bind as bind_mod
from . import compile as compile_mod
from . import expr
from .spec import Spec


class Tampered(Exception):
    """The spec changed while being measured, so the numbers describe nothing."""


@dataclass(frozen=True)
class Result:
    """One generated question, its answer, and how the answer was reached.

    `trace` is required and checked. A result that cannot say what it ran is
    worth less than no result: it reports a number while hiding the one thing a
    failure is for, which is knowing where to look.
    """

    id: str
    asks: str
    trace: list[str]
    expected: Any
    got: Any

    def __post_init__(self) -> None:
        if not self.trace:
            raise ValueError(
                f"result {self.id!r} carries no trace. A score that cannot be "
                f"retraced says a number and nothing about where to look, which is "
                f"the only part of a failure that is any use"
            )

    @property
    def ok(self) -> bool:
        if isinstance(self.expected, float) or isinstance(self.got, float):
            try:
                return abs(float(self.expected) - float(self.got)) < 1e-6
            except (TypeError, ValueError):
                return False
        return self.expected == self.got

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "asks": self.asks,
            "trace": self.trace,
            "expected": self.expected,
            "got": self.got,
            "ok": self.ok,
        }


@dataclass
class Run:
    ontology: str
    results: list[Result] = field(default_factory=list)

    def score(self) -> tuple[int, int]:
        return sum(1 for r in self.results if r.ok), len(self.results)

    def as_dict(self) -> dict:
        passed, total = self.score()
        return {
            "ontology": self.ontology,
            "passed": passed,
            "total": total,
            # Said out loud in the report itself, so nobody downstream has to
            # infer it from an exit code that will not carry it.
            "gates": False,
            "results": [r.as_dict() for r in self.results],
        }


def fingerprint(s: Spec) -> str:
    """What the spec says, independent of how it is laid out in the file."""
    payload = json.dumps(
        {
            "types": s.types,
            "raw": s.raw,
            "hooks": s.hooks,
            "nodes": s.nodes,
            "checks": s.checks,
            "ops": s.ops,
            "bases": s.bases,
            "bridges": s.bridges,
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _negate(src: str) -> str:
    """The same aggregate over the rows the original leaves out."""
    head, _, where = src.partition(" where ")
    return f"{head} where not ({where})" if where else src


def _whole(src: str) -> str:
    """The same aggregate over every row."""
    head, _, _ = src.partition(" where ")
    return head


def correctness(s: Spec, basis: str | None = None) -> Run:
    """Does the graph agree with the data underneath it.

    Two generators, both deriving their questions from what the spec already
    says, so neither can go stale while the spec moves:

      * **A filter partitions.** Any aggregate with a condition must, added to
        the same aggregate over the rows it excludes, come to the aggregate over
        all of them. This catches a mistranslated filter, a null handled one way
        here and another way there, and a condition that silently drops rows —
        faults that each look like a plausible number on their own.
      * **Two routes, one answer.** Where rows are in memory *and* the type is a
        view over a table, the figure is computed both ways. They are different
        code: one walks dicts in Python, one is SQL. Two routes to a number is
        two chances to disagree, and the point of having both is to notice.
    """
    run = Run(ontology=s.name)
    before = fingerprint(s)
    agg = bind_mod.answerer(s)

    for name, node in s.nodes.items():
        src = compile_mod.op_for(node, basis)
        if not src:
            continue
        try:
            ast = expr.parse(src)
        except expr.ExprError:
            continue
        if not isinstance(ast, expr.Select) or ast.where is None:
            continue
        if not s.backing_of(ast.type_name):
            continue

        parts = [_whole(src), src, _negate(src)]
        try:
            whole, kept, rest = (
                expr.evaluate(expr.parse(p), {}, s.instances, agg) for p in parts
            )
        except (expr.ExprError, bind_mod.BindingError):
            continue
        run.results.append(
            Result(
                id=f"partition/{name}",
                asks=f"{name}: the rows it keeps and the rows it leaves out are all of them",
                trace=[f"{p} = {v}" for p, v in zip(parts, (whole, kept, rest), strict=True)],
                expected=whole,
                got=(kept or 0) + (rest or 0),
            )
        )

    for tname in s.types:
        if not s.backing_of(tname) or tname in s.unloaded:
            continue
        for name, node in s.nodes.items():
            src = compile_mod.op_for(node, basis)
            if not src:
                continue
            try:
                ast = expr.parse(src)
            except expr.ExprError:
                continue
            if not isinstance(ast, expr.Select) or ast.type_name != tname:
                continue
            try:
                in_sql = bind_mod.aggregate(s, ast, s.source_base)
            except bind_mod.NotPushable:
                continue
            in_rows = expr.evaluate(ast, {}, s.instances)
            run.results.append(
                Result(
                    id=f"routes/{name}",
                    asks=f"{name}: the source and the rows in hand give the same figure",
                    trace=[f"source: {src} = {in_sql}", f"rows:   {src} = {in_rows}"],
                    expected=in_sql,
                    got=in_rows,
                )
            )

    if fingerprint(s) != before:
        raise Tampered(
            f"{s.name} changed while being measured, so these numbers describe "
            f"something that no longer exists. A harness that can edit the thing "
            f"it scores is not measuring it"
        )
    return run
