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
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from . import bind as bind_mod
from . import compile as compile_mod
from . import expr
from .query import link_resolver
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
            "generator": self.id.split('/', 1)[0],
            "node": self.id.split('/', 1)[-1],
        }


@dataclass
class Run:
    ontology: str
    results: list[Result] = field(default_factory=list)
    uncovered: list[dict] = field(default_factory=list)

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
            "uncovered": self.uncovered,
        }


def fingerprint(s: Spec) -> str:
    """What the spec says, independent of how it is laid out in the file."""
    payload = json.dumps(
        asdict(s),
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def correctness(s: Spec, basis: str | None = None, at: dict | None = None) -> Run:
    """Generate additive partition and independent execution-route questions.

    Partition checks apply only to SUM/COUNT: averages and extrema cannot be
    added across subsets. SQL UNKNOWN is deliberately visible as uncovered
    rows; WHERE c and WHERE NOT c do not cover null predicates.
    """
    run = Run(ontology=s.name)
    before = fingerprint(s)
    if not any(s.backing_of(t) for t in s.types):
        run.uncovered = [{'node': n, 'reason': 'no direct backed aggregate'} for n in s.nodes]
        return run
    compiled = compile_mod.compile_spec(s, basis=basis, at=at)
    working = replace(s, instances=compiled.rows)
    agg = bind_mod.answerer(working, at, basis)
    resolve = link_resolver(working)

    for name, node in s.nodes.items():
        src = compile_mod.op_for(node, basis)
        ast = expr.parse(src) if src else None
        if not isinstance(ast, expr.Select) or not s.backing_of(ast.type_name):
            run.uncovered.append({"node": name, "reason": "no direct backed aggregate"})
            continue
        start = len(run.results)
        if ast.where is not None and ast.func in ('sum', 'count'):
            parts = [replace(ast, where=None), ast, replace(ast, where=expr.Not(ast.where))]
            try:
                whole, kept, rest = [expr.evaluate(a, compiled.values, working.instances,
                                                  agg, resolve) for a in parts]
                run.results.append(Result(
                    id=f"partition/{name}",
                    asks=(f"{name}: selected + excluded = all rows "
                          "(null predicates can leave a gap)"),
                    trace=[f"{expr.to_sql(a)} = {v}"
                           for a, v in zip(parts, (whole, kept, rest), strict=True)],
                    expected=whole, got=(kept or 0) + (rest or 0),
                ))
            except (expr.ExprError, bind_mod.BindingError) as e:
                run.uncovered.append({"node": name, "reason": str(e)})
        if ast.type_name not in s.unloaded:
            try:
                in_sql = bind_mod.aggregate(working, ast, s.source_base, at,
                                            basis=basis, scope=compiled.values)
                in_rows = expr.evaluate(ast, compiled.values, working.instances,
                                        resolve=resolve)
                run.results.append(Result(
                    id=f"routes/{name}",
                    asks=f"{name}: database and in-memory rows give the same figure",
                    trace=[f"source: {expr.to_sql(ast)} = {in_sql}",
                           f"rows: {expr.to_sql(ast)} = {in_rows}"],
                    expected=in_sql, got=in_rows,
                ))
            except (expr.ExprError, bind_mod.BindingError, bind_mod.NotPushable) as e:
                run.uncovered.append({"node": name, "reason": str(e)})
        if len(run.results) == start and not any(x['node'] == name for x in run.uncovered):
            run.uncovered.append({"node": name, "reason": "rows not loaded; no additive partition"})
    if fingerprint(s) != before:
        raise Tampered(f"{s.name} changed while measured; the harness is not measuring it")
    return run
