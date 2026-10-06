"""Evaluate a checked SQL subset over ontology objects.

SQLGlot parses standard syntax; sql_parser lowers only supported constructs to
this AST. Database translation and row evaluation share this representation.
Paths follow declared refs, preserving one source row per aggregate input.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from . import sql_parser

AGGREGATES = ("sum", "count", "avg", "min", "max")


def money_round(value, scale=0):
    if value is None:
        return None
    result = Decimal(str(value)).quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_UP)
    return int(result) if scale == 0 else float(result)


def divide(left, right):
    if left is None or right is None:
        return None
    if right == 0:
        raise ExprError("division by zero")
    return left / right


def decimal_binary(op, left, right):
    """Keep decimal money arithmetic exact until the property's rounding boundary."""
    if left is None or right is None:
        return None
    a, b = Decimal(str(left)), Decimal(str(right))
    if op == '+':
        return a + b
    if op == '-':
        return a - b
    if op == '*':
        return a * b
    return divide(a, b)

#: What an aggregate answerer returns when it cannot answer this one, kept
#: distinct from None because None is a legitimate answer.
_DECLINED = object()
DECLINED = _DECLINED


class ExprError(ValueError):
    """The expression is not valid.

    Messages carry the offending position because the author is an agent, and a
    failure that does not say where is a failure it cannot act on.
    """


# ── AST ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Lit:
    value: Any


@dataclass(frozen=True)
class Ref:
    """A bare identifier: resolved against instance properties, then node values."""

    name: str


@dataclass(frozen=True)
class Path:
    """A path of declared refs, never arbitrary Python attribute access."""

    parts: tuple[str, ...]


@dataclass(frozen=True)
class Bin:
    op: str
    left: Any
    right: Any


@dataclass(frozen=True)
class Not:
    operand: Any


@dataclass(frozen=True)
class Neg:
    operand: Any


@dataclass(frozen=True)
class IsNull:
    operand: Any
    negated: bool


@dataclass(frozen=True)
class Select:
    """A scalar subquery: one aggregate over one type, optionally filtered."""

    func: str
    prop: str | None  # None only for count(*)
    type_name: str
    where: Any | None


def parse(src: str) -> Any:
    return sql_parser.parse(src)


# ── Evaluation ─────────────────────────────────────────────────────────

_CMP: dict[str, Callable[[Any, Any], Any]] = {
    "=": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}


def evaluate(
    node: Any,
    scope: dict[str, Any],
    instances: dict[str, list[dict]],
    agg: Any = None,
    resolve: Any = None,
    *, decimal_math: bool = False,
) -> Any:
    """`scope` holds the names visible here: node values, or one instance's props.

    `agg` is an optional way to answer a whole aggregate without rows — the
    database doing it, when the type is a view over a table. It is tried first
    and may decline, which is how a type larger than memory stays usable while
    one that is not keeps the row-by-row path.
    """
    def run(n, local=None):
        return evaluate(n, scope if local is None else local, instances, agg, resolve,
                        decimal_math=decimal_math)

    if isinstance(node, Lit):
        return node.value
    if isinstance(node, Ref):
        if node.name in scope:
            return scope[node.name]
        raise ExprError(f"unknown name {node.name!r}: neither a property nor a computed node")
    if isinstance(node, Path):
        if resolve is None:
            raise ExprError(f"{'.'.join(node.parts)} needs declared links to follow")
        return resolve(scope.get('__type__'), node.parts, scope)
    if isinstance(node, Not):
        value = run(node.operand)
        return None if value is None else not value
    if isinstance(node, Neg):
        value = run(node.operand)
        return None if value is None else -value
    if isinstance(node, IsNull):
        return (run(node.operand) is not None) == node.negated
    if isinstance(node, Select):
        if agg is not None:
            answered = agg(node, scope)
            if answered is not _DECLINED:
                return answered
        rows = instances.get(node.type_name)
        if rows is None:
            raise ExprError(f"select refers to unknown type {node.type_name!r}")
        kept = [
            r
            for r in rows
            if node.where is None or run(node.where, {**scope, **r, '__type__': node.type_name})
        ]
        if node.func == "count" and node.prop is None:
            return len(kept)
        column = Path(tuple(node.prop.split('.'))) if '.' in node.prop else Ref(node.prop)
        values = [run(column, {**scope, **r, '__type__': node.type_name}) for r in kept]
        values = [v for v in values if v is not None]
        if node.func == "count":
            return len(values)
        if node.func == "sum":
            return sum(values)
        if not values:
            return None
        if node.func == "avg":
            return sum(values) / len(values)
        return min(values) if node.func == "min" else max(values)
    if isinstance(node, Bin):
        a = run(node.left)
        b = run(node.right)
        if node.op == "and":
            if (a is not None and not a) or (b is not None and not b):
                return False
            return None if a is None or b is None else True
        if node.op == "or":
            if a or b:
                return True
            return None if a is None or b is None else False
        # SQL semantics are kept, deliberately: a comparison involving a null is
        # unknown, which keeps the row out of a filter, and arithmetic touching
        # a null is null. Python would raise on both, so a figure computed here
        # would have crashed where the same figure computed by the database
        # quietly excluded the row — the two routes disagreeing about the one
        # case this project cares most about. Found by the measurement harness
        # the first time it ran against a column that was actually nullable.
        if a is None or b is None:
            return None
        if node.op in _CMP:
            return _CMP[node.op](a, b)
        if decimal_math and node.op in ('+', '-', '*', '/'):
            return decimal_binary(node.op, a, b)
        if node.op == "+":
            return a + b
        if node.op == "-":
            return a - b
        if node.op == "*":
            return a * b
        if node.op == "/":
            return divide(a, b)
    raise ExprError(f"cannot evaluate node: {node!r}")


def aggregated_types(node: Any) -> set[str]:
    """Which instance types this expression aggregates over.

    Read from the AST rather than by substring-matching the source: a type whose
    name is a substring of another would otherwise produce a phantom edge, and a
    graph that draws relationships nobody declared is worse than one that draws
    too few.
    """
    if isinstance(node, Select):
        inner = aggregated_types(node.where) if node.where is not None else set()
        return {node.type_name} | inner
    if isinstance(node, (Not, Neg)):
        return aggregated_types(node.operand)
    if isinstance(node, IsNull):
        return aggregated_types(node.operand)
    if isinstance(node, Bin):
        return aggregated_types(node.left) | aggregated_types(node.right)
    return set()


#: Numbers that carry no judgement wherever they appear: the additive and
#: multiplicative identities. Everything else written into an expression is a
#: figure somebody chose, which is why they are reported rather than ignored.
IDENTITY_LITERALS = (0, 1, -1)


def numeric_literals(node: Any) -> list[Any]:
    """Every number written into the expression, identities excluded.

    A number inside a formula is a decision wearing a disguise: `/ 1.06` is a
    tax rate somebody can disagree with, hidden where nothing can point at it,
    comment on it, or vary it by reading. Finding them is what lets the compiler
    say so instead of a reviewer having to notice.
    """
    if isinstance(node, Lit):
        v = node.value
        ok = isinstance(v, (int, float)) and not isinstance(v, bool)
        return [v] if ok and v not in IDENTITY_LITERALS else []
    if isinstance(node, (Not, Neg)):
        return numeric_literals(node.operand)
    if isinstance(node, IsNull):
        return numeric_literals(node.operand)
    if isinstance(node, Bin):
        return numeric_literals(node.left) + numeric_literals(node.right)
    if isinstance(node, Select):
        # A literal in a filter is a value being matched, not a figure the
        # result is scaled by: `where 认定 = '资本化'` and `where 数量 > 0`
        # name rows, they do not decide an amount.
        return []
    return []


def referenced_names(node: Any) -> set[str]:
    """Bare identifiers the expression reads, to order derived nodes by dependency.

    Names inside a select's where clause are instance properties, not nodes, so
    they do not count as dependencies between nodes.
    """
    if isinstance(node, Ref):
        return {node.name}
    if isinstance(node, (Not, Neg)):
        return referenced_names(node.operand)
    if isinstance(node, IsNull):
        return referenced_names(node.operand)
    if isinstance(node, Bin):
        return referenced_names(node.left) | referenced_names(node.right)
    if isinstance(node, Select):
        return set()
    return set()


def to_sql(node: Any) -> str:
    """Render the admitted AST, so generated questions do not split source text."""
    def ident(name):
        return '"' + name.replace('"', '""') + '"'

    if isinstance(node, Lit):
        if node.value is None:
            return 'NULL'
        if isinstance(node.value, str):
            return "'" + node.value.replace("'", "''") + "'"
        return str(node.value)
    if isinstance(node, Ref):
        return ident(node.name)
    if isinstance(node, Path):
        return '.'.join(ident(p) for p in node.parts)
    if isinstance(node, (Not, Neg)):
        return f"({'NOT ' if isinstance(node, Not) else '-'}{to_sql(node.operand)})"
    if isinstance(node, IsNull):
        return f"({to_sql(node.operand)} IS {'NOT ' if node.negated else ''}NULL)"
    if isinstance(node, Bin):
        return f"({to_sql(node.left)} {node.op.upper()} {to_sql(node.right)})"
    if isinstance(node, Select):
        prop = '*' if node.prop is None else '.'.join(ident(p) for p in node.prop.split('.'))
        tail = ' WHERE ' + to_sql(node.where) if node.where is not None else ''
        return f"SELECT {node.func.upper()}({prop}) FROM {ident(node.type_name)}{tail}"
    raise ExprError(f"cannot render {node!r}")
