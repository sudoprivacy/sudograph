"""A restricted expression language: parsed into an AST, then evaluated. Never eval'd.

Everything outside the whitelist is a syntax error — attribute chains, function
definitions, imports, arbitrary calls. Adding a capability means adding a rule
here, deliberately, because specs are written by agents: a spec that can eval is
a spec that hands execution to the model.

Grammar (lowest precedence first):

    or_expr   := and_expr ('or' and_expr)*
    and_expr  := not_expr ('and' not_expr)*
    not_expr  := 'not' not_expr | cmp
    cmp       := sum (('=='|'!='|'<='|'>='|'<'|'>') sum)?
    sum       := product (('+'|'-') product)*
    product   := unary (('*'|'/') unary)*
    unary     := '-' unary | atom
    atom      := NUMBER | STRING | 'null' | agg | NAME | '(' or_expr ')'
    agg       := ('sum'|'count') '(' NAME ['where' or_expr] ['->' NAME] ')'

NAME is deliberately permissive (any run of non-delimiter characters) so that
business vocabulary stays in the customer's own language while the grammar
itself remains English.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

AGGREGATES = ("sum", "count")
KEYWORDS = {"and", "or", "not", "where", "null"} | set(AGGREGATES)

_TOKEN = re.compile(
    r"""
    (?P<space>\s+)
  | (?P<number>\d+(?:\.\d+)?)
  | (?P<string>'[^']*')
  | (?P<arrow>->)
  | (?P<op><=|>=|==|!=|[<>+\-*/()])
  | (?P<name>[^\s'()<>=!+\-*/]+)
    """,
    re.VERBOSE,
)


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
        if kind == "name" and text in KEYWORDS:
            kind = text
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
class Agg:
    func: str
    type_name: str
    where: Any | None
    prop: str | None


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
        node = self.or_expr()
        if self.peek() is not None:
            t = self.peek()
            raise ExprError(f"trailing input {t.text!r} at position {t.pos}: {self.src!r}")
        return node

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
        t = self.peek()
        if t is not None and t.text in ("==", "!=", "<", "<=", ">", ">="):
            self.i += 1
            return Bin(t.text, node, self.sum())
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
            node = self.or_expr()
            self.take(")")
            return node
        if t.text in AGGREGATES:
            return self.agg(t.text)
        if t.kind == "name":
            return Ref(t.text)
        raise ExprError(f"{t.text!r} at position {t.pos} cannot be a value")

    def agg(self, func: str) -> Agg:
        self.take("(")
        type_name = self.take("name").text
        where = self.or_expr() if self.accept("where") else None
        prop = self.take("name").text if self.accept("arrow") else None
        self.take(")")
        if func == "sum" and prop is None:
            raise ExprError(f"sum needs -> to say which property to add: {self.src!r}")
        return Agg(func, type_name, where, prop)


def parse(src: str) -> Any:
    return _Parser(tokenize(src), src).parse()


# ── Evaluation ─────────────────────────────────────────────────────────

_CMP: dict[str, Callable[[Any, Any], Any]] = {
    "==": lambda a, b: a == b,
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
    if isinstance(node, Agg):
        rows = instances.get(node.type_name)
        if rows is None:
            raise ExprError(f"aggregate refers to unknown type {node.type_name!r}")
        kept = [
            r
            for r in rows
            if node.where is None or evaluate(node.where, {**scope, **r}, instances)
        ]
        if node.func == "count":
            return len(kept)
        total = 0
        for r in kept:
            if node.prop not in r:
                raise ExprError(
                    f"an instance of {node.type_name} has no property {node.prop!r} to sum"
                )
            v = r[node.prop]
            if v is None:
                continue
            total += v
        return total
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


def referenced_names(node: Any) -> set[str]:
    """Bare identifiers the expression reads, to order derived nodes by dependency.

    Names inside an aggregate are instance properties, not nodes, so they do not
    count as dependencies between nodes.
    """
    if isinstance(node, Ref):
        return {node.name}
    if isinstance(node, (Not, Neg)):
        return referenced_names(node.operand)
    if isinstance(node, Bin):
        return referenced_names(node.left) | referenced_names(node.right)
    if isinstance(node, Agg):
        return set()
    return set()
