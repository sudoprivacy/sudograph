"""A restricted SQL subset: parsed into an AST, then evaluated. Never eval'd.

Everything outside the whitelist is a syntax error — attribute chains, function
definitions, imports, arbitrary calls. Adding a capability means adding a rule
here, deliberately, because specs are written by agents: a spec that can eval is
a spec that hands execution to the model.

**Why SQL and not a language of our own.** An earlier version of this file used
an invented syntax (`sum(T where c -> p)`). It parsed fine and nobody could read
it. The expressions are the part of a spec a business reviewer actually has to
check, so the syntax has to be one that both a person and a model already know,
and SQL is the only data language with that property. What is written here is
real SQL as far as it goes; the restrictions are subtractions, not dialect.

Grammar (lowest precedence first):

    stmt      := select | or_expr
    or_expr   := and_expr ('or' and_expr)*
    and_expr  := not_expr ('and' not_expr)*
    not_expr  := 'not' not_expr | cmp
    cmp       := sum (('='|'<>'|'!='|'<='|'>='|'<'|'>') sum)?
               | sum 'is' ['not'] 'null'
    sum       := product (('+'|'-') product)*
    product   := unary (('*'|'/') unary)*
    unary     := '-' unary | atom
    atom      := NUMBER | STRING | 'null' | NAME | '(' (select | or_expr) ')'
    select    := 'select' agg 'from' NAME ['where' or_expr]
    agg       := 'sum' '(' NAME ')' | 'count' '(' (NAME | '*') ')'

A node's whole expression may be a bare `select`; anywhere else an aggregate is
a **scalar subquery** and must be parenthesised, exactly as in SQL. That is not
ceremony: without the parentheses, `select sum(x) from T where c + 1` has two
readings, and a figure whose meaning depends on how the reader groups it is the
opposite of what this project is for.

Keywords are case-insensitive. NAME is deliberately permissive (any run of
non-delimiter characters) so business vocabulary stays in the customer's own
language while the grammar itself stays SQL.

**Deliberate subtractions from SQL**, each because it would let a figure mean two
things: no joins or subqueries in FROM (one type per aggregate — a relationship
between types is modelled as a link, not smuggled into an expression), no
GROUP BY (grouping is a view decision and lives in the compiler), no ORDER BY or
LIMIT (a total does not depend on row order), no DISTINCT, no CASE, no functions
beyond SUM and COUNT.

**Where SQL's own semantics are kept**: SUM skips nulls and COUNT(<prop>) counts
the non-null, as everywhere else in SQL. The risk that creates — a total silently
understated by a missing figure — is not fixed by changing the arithmetic, which
would surprise every reader. It is caught one level up, by `absent: gap`.

**Where they are refused instead**: `x = null` is never true in SQL, which reads
as "no such row" and means "the question was malformed". Rather than evaluate it
to false, this rejects it and names `is null`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

AGGREGATES = ("sum", "count")
KEYWORDS = {"and", "or", "not", "where", "null", "select", "from", "is"} | set(AGGREGATES)

_TOKEN = re.compile(
    r"""
    (?P<space>\s+)
  | (?P<number>\d+(?:\.\d+)?)
  | (?P<string>'[^']*')
  | (?P<gone>->|==)
  | (?P<op><=|>=|<>|!=|=|[<>+\-*/()])
  | (?P<name>[^\s'()<>=!+\-*/.,;:]+)
    """,
    re.VERBOSE,
)

#: Spellings from the invented syntax this replaced. They are recognised only so
#: the error can name the SQL that takes their place — a bare "unexpected token"
#: would leave the author guessing at a language they are still learning.
_GONE = {
    "->": "the projection arrow is gone; write `select sum(<prop>) from <Type> where <cond>`",
    "==": "use `=` for equality, as in SQL — not `==`",
}

#: SQL this subset does not have. Each entry says where the capability lives
#: instead, because every one of them exists somewhere in the system — refusing
#: without saying where is how a restriction reads as an omission.
_SUBTRACTED = {
    "group": "GROUP BY is not in this subset — grouping is a view decision, so the "
    "compiler buckets instances for the graph app instead",
    "order": "ORDER BY is not in this subset — a total must not depend on row order; "
    "ranking for display is the view model's `top`",
    "limit": "LIMIT is not in this subset — a figure computed from some of the rows is "
    "not the figure; the view model's `top_n` does the truncating for display",
    "having": "HAVING is not in this subset — filter in WHERE",
    "join": "JOIN is not in this subset — a relationship between two types is modelled "
    "as a link on the graph, not smuggled into one node's expression",
    "union": "UNION is not in this subset — add the two selects instead",
}


class ExprError(ValueError):
    """The expression is not valid.

    Messages carry the offending position because the author is an agent, and a
    failure that does not say where is a failure it cannot act on.
    """


@dataclass(frozen=True)
class Tok:
    kind: str
    text: str
    pos: int


def tokenize(src: str) -> list[Tok]:
    out: list[Tok] = []
    i = 0
    while i < len(src):
        m = _TOKEN.match(src, i)
        if not m:
            raise ExprError(f"unrecognised character {src[i]!r} at position {i}")
        i = m.end()
        kind = m.lastgroup
        if kind == "space":
            continue
        text = m.group()
        if kind == "gone":
            raise ExprError(f"{_GONE[text]} (at position {m.start()}): {src!r}")
        if kind == "name" and text.lower() in KEYWORDS:
            kind = text.lower()
        out.append(Tok(kind, text, m.start()))
    return out


# ── AST ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Lit:
    value: Any


@dataclass(frozen=True)
class Ref:
    """A bare identifier: resolved against instance properties, then node values."""

    name: str


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


class _Parser:
    def __init__(self, toks: list[Tok], src: str) -> None:
        self.toks = toks
        self.src = src
        self.i = 0

    def peek(self) -> Tok | None:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self, *kinds: str) -> Tok:
        t = self.peek()
        if t is None:
            raise ExprError(f"expression ends early, expected {'/'.join(kinds)}: {self.src!r}")
        if kinds and t.kind not in kinds and t.text not in kinds:
            raise ExprError(
                f"got {t.text!r} at position {t.pos}, expected {'/'.join(kinds)}: {self.src!r}"
            )
        self.i += 1
        return t

    def accept(self, *texts: str) -> Tok | None:
        t = self.peek()
        if t is not None and (t.text in texts or t.kind in texts):
            self.i += 1
            return t
        return None

    # Grammar ────────────────────────────────────────────────────────

    def parse(self) -> Any:
        node = self.statement()
        if self.peek() is not None:
            t = self.peek()
            raise ExprError(f"trailing input {t.text!r} at position {t.pos}: {self.src!r}")
        return node

    def statement(self) -> Any:
        t = self.peek()
        if t is not None and t.kind == "select":
            return self.select_stmt()
        return self.or_expr()

    def or_expr(self) -> Any:
        node = self.and_expr()
        while self.accept("or"):
            node = Bin("or", node, self.and_expr())
        return node

    def and_expr(self) -> Any:
        node = self.not_expr()
        while self.accept("and"):
            node = Bin("and", node, self.not_expr())
        return node

    def not_expr(self) -> Any:
        if self.accept("not"):
            return Not(self.not_expr())
        return self.cmp()

    def cmp(self) -> Any:
        node = self.sum()
        if self.accept("is"):
            negated = bool(self.accept("not"))
            self.take("null")
            return IsNull(node, negated)
        t = self.peek()
        if t is not None and t.text in ("=", "<>", "!=", "<", "<=", ">", ">="):
            self.i += 1
            right = self.sum()
            null_side = (isinstance(node, Lit) and node.value is None) or (
                isinstance(right, Lit) and right.value is None
            )
            if null_side:
                raise ExprError(
                    f"comparing with null using {t.text!r} is never true in SQL — "
                    f"write `is null` or `is not null`: {self.src!r}"
                )
            return Bin("!=" if t.text == "<>" else t.text, node, right)
        return node

    def sum(self) -> Any:
        node = self.product()
        while True:
            t = self.accept("+", "-")
            if not t:
                return node
            node = Bin(t.text, node, self.product())

    def product(self) -> Any:
        node = self.unary()
        while True:
            t = self.accept("*", "/")
            if not t:
                return node
            node = Bin(t.text, node, self.unary())

    def unary(self) -> Any:
        if self.accept("-"):
            return Neg(self.unary())
        return self.atom()

    def atom(self) -> Any:
        t = self.take()
        if t.kind == "number":
            return Lit(float(t.text) if "." in t.text else int(t.text))
        if t.kind == "string":
            return Lit(t.text[1:-1])
        if t.kind == "null":
            return Lit(None)
        if t.text == "(":
            inner = self.peek()
            nested = inner is not None and inner.kind == "select"
            node = self.select_stmt() if nested else self.or_expr()
            self.take(")")
            return node
        if t.kind in AGGREGATES:
            raise ExprError(
                f"{t.text.lower()}(...) needs a select around it: write "
                f"`(select {t.text.lower()}(<prop>) from <Type> where <cond>)` "
                f"(at position {t.pos}): {self.src!r}"
            )
        if t.kind == "name":
            return Ref(t.text)
        raise ExprError(f"{t.text!r} at position {t.pos} cannot be a value")

    def select_stmt(self) -> Select:
        self.take("select")
        func = self.take(*AGGREGATES).text.lower()
        self.take("(")
        if self.accept("*"):
            if func != "count":
                raise ExprError(f"sum(*) is not a thing — name the property to add: {self.src!r}")
            prop = None
        else:
            prop = self.take("name").text
        self.take(")")
        self.take("from")
        type_name = self.take("name").text
        where = self.or_expr() if self.accept("where") else None
        self.refuse_subtracted()
        return Select(func, prop, type_name, where)

    def refuse_subtracted(self) -> None:
        """Name the SQL we deliberately do not have, and say where it went.

        Without this the author gets "trailing input 'group'", which reads as a
        typo. Each of these has a real home elsewhere in the system, and saying
        so is the difference between a dead end and a redirection.
        """
        t = self.peek()
        if t is not None and t.text.lower() in _SUBTRACTED:
            raise ExprError(f"{_SUBTRACTED[t.text.lower()]} (at position {t.pos}): {self.src!r}")


def parse(src: str) -> Any:
    return _Parser(tokenize(src), src).parse()


# ── Evaluation ─────────────────────────────────────────────────────────

_CMP: dict[str, Callable[[Any, Any], Any]] = {
    "=": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}


def evaluate(node: Any, scope: dict[str, Any], instances: dict[str, list[dict]]) -> Any:
    """`scope` holds the names visible here: node values, or one instance's props."""
    if isinstance(node, Lit):
        return node.value
    if isinstance(node, Ref):
        if node.name in scope:
            return scope[node.name]
        raise ExprError(f"unknown name {node.name!r}: neither a property nor a computed node")
    if isinstance(node, Not):
        return not evaluate(node.operand, scope, instances)
    if isinstance(node, Neg):
        return -evaluate(node.operand, scope, instances)
    if isinstance(node, IsNull):
        return (evaluate(node.operand, scope, instances) is not None) == node.negated
    if isinstance(node, Select):
        rows = instances.get(node.type_name)
        if rows is None:
            raise ExprError(f"select refers to unknown type {node.type_name!r}")
        kept = [
            r
            for r in rows
            if node.where is None or evaluate(node.where, {**scope, **r}, instances)
        ]
        if node.func == "count" and node.prop is None:
            return len(kept)
        for r in kept:
            if node.prop not in r:
                raise ExprError(
                    f"an instance of {node.type_name} has no property {node.prop!r}"
                )
        values = [r[node.prop] for r in kept if r[node.prop] is not None]
        return len(values) if node.func == "count" else sum(values)
    if isinstance(node, Bin):
        if node.op == "and":
            return bool(evaluate(node.left, scope, instances)) and bool(
                evaluate(node.right, scope, instances)
            )
        if node.op == "or":
            return bool(evaluate(node.left, scope, instances)) or bool(
                evaluate(node.right, scope, instances)
            )
        a = evaluate(node.left, scope, instances)
        b = evaluate(node.right, scope, instances)
        if node.op in _CMP:
            return _CMP[node.op](a, b)
        if node.op == "+":
            return a + b
        if node.op == "-":
            return a - b
        if node.op == "*":
            return a * b
        if node.op == "/":
            if b == 0:
                raise ExprError("division by zero")
            return a / b
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
