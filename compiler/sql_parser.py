"""Parse standard SQLite expressions; admit only constructs the ontology can check.

SQLGlot owns syntax. This adapter owns the capability boundary and lowers to our
small evaluation AST. Parsing is not validation: every unhandled SQL node is
refused, including executable statements and arbitrary functions.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError
from sqlglot.tokens import TokenType

from . import expr

_BINARY = {
    exp.Add: "+", exp.Sub: "-", exp.Mul: "*", exp.Div: "/",
    exp.EQ: "=", exp.NEQ: "!=", exp.LT: "<", exp.LTE: "<=",
    exp.GT: ">", exp.GTE: ">=", exp.And: "and", exp.Or: "or",
}
_AGG = {exp.Sum: "sum", exp.Count: "count", exp.Avg: "avg", exp.Min: "min", exp.Max: "max"}
_CLAUSES = {
    "group": "GROUP BY: grouping is a view decision; put an aggregate on the related object",
    "order": "ORDER BY: a total must not depend on row order; use the view's ranking",
    "limit": "LIMIT: a subtotal is not the figure; restrict the type or filter in WHERE",
    "having": "HAVING: filter in WHERE, or define a named metric to compare",
    "joins": "JOIN: a relationship is modelled as a link; follow that ref as product.category",
    "distinct": "DISTINCT: declare the row identity instead of hiding duplicate rows",
}


def parse(src: str):
    try:
        # Legacy spellings get actionable errors without examining string values.
        tokens = sqlglot.tokenize(src, read="sqlite")
        for token in tokens:
            if token.token_type == TokenType.STRING:
                continue
            spelling = src[token.start:token.end + 1]
            if spelling == "==":
                raise expr.ExprError("use `=` for equality, as in SQL — not `==`")
            if spelling == "->":
                raise expr.ExprError(
                    "the projection arrow is gone; write `select sum(<prop>) from <Type>`"
                )
        trees = sqlglot.parse(src, read="sqlite")
    except (ParseError, TokenError) as e:
        raise expr.ExprError(f"invalid SQL or trailing input: {e}") from None
    if len(trees) != 1 or trees[0] is None:
        raise expr.ExprError("write exactly one scalar expression or SELECT")
    return _lower(trees[0])


def _lower(node, *, in_select=False):
    if isinstance(node, (exp.Paren, exp.Subquery)):
        return _lower(node.this, in_select=in_select)
    if isinstance(node, exp.Null):
        return expr.Lit(None)
    if isinstance(node, exp.Boolean):
        return expr.Lit(node.this)
    if isinstance(node, exp.Literal):
        if node.is_string:
            return expr.Lit(node.this)
        return expr.Lit(float(node.this) if any(c in node.this for c in '.eE') else int(node.this))
    if isinstance(node, exp.Column):
        names = [part.name for part in node.parts]
        if len(names) > 1:
            if not in_select:
                raise expr.ExprError("follow declared links inside a SELECT over their source type")
            return expr.Path(tuple(names))
        return expr.Ref(node.name)
    if isinstance(node, exp.Not):
        inner = _lower(node.this, in_select=in_select)
        if isinstance(inner, expr.IsNull):
            return expr.IsNull(inner.operand, not inner.negated)
        return expr.Not(inner)
    if isinstance(node, exp.Neg):
        return expr.Neg(_lower(node.this, in_select=in_select))
    if isinstance(node, exp.Is) and isinstance(node.expression, exp.Null):
        return expr.IsNull(_lower(node.this, in_select=in_select), False)
    if type(node) in _BINARY:
        left = _lower(node.this, in_select=in_select)
        right = _lower(node.expression, in_select=in_select)
        op = _BINARY[type(node)]
        if op in ("=", "!=", "<", "<=", ">", ">=") and any(
            isinstance(x, expr.Lit) and x.value is None for x in (left, right)
        ):
            raise expr.ExprError(
                "a comparison with null is unknown — use `is null` or `is not null`")
        return expr.Bin(op, left, right)
    if isinstance(node, exp.Union):
        raise expr.ExprError("UNION: add the two selects instead")
    if isinstance(node, exp.Select):
        for key, reason in _CLAUSES.items():
            if node.args.get(key):
                raise expr.ExprError(reason)
        allowed = {"expressions", "from_", "where"}
        unknown = [k for k, v in node.args.items() if v and k not in allowed]
        if unknown:
            raise expr.ExprError(f"unsupported SELECT clauses {unknown}; use a scalar aggregate")
        source = node.args.get("from_")
        table = source.this if source else None
        if not isinstance(table, exp.Table) or table.args.get("alias") or len(table.parts) != 1:
            raise expr.ExprError(
                "FROM must name one declared object type, without alias or subquery")
        if len(node.expressions) != 1 or type(node.expressions[0]) not in _AGG:
            raise expr.ExprError("SELECT needs one of SUM/COUNT/AVG/MIN/MAX over a named property")
        aggregate = node.expressions[0]
        if any(v for k, v in aggregate.args.items() if k not in ("this", "big_int")):
            raise expr.ExprError("the aggregate takes exactly one property")
        prop = aggregate.this
        func = _AGG[type(aggregate)]
        if isinstance(prop, exp.Star):
            if func != "count":
                raise expr.ExprError(f"{func}(*) is undefined — name the property to aggregate")
            name = None
        elif isinstance(prop, exp.Column):
            name = ".".join(p.name for p in prop.parts)
        else:
            raise expr.ExprError(
                "name a computed property, then aggregate it; do not hide a formula")
        where = node.args.get("where")
        return expr.Select(func, name, table.name,
                           _lower(where.this, in_select=True) if where else None)
    if type(node) in _AGG:
        raise expr.ExprError(
            "an aggregate needs a select around it: `(select sum(prop) from Type)`")
    raise expr.ExprError(
        f"unsupported SQL construct {node.key!r}; use a declared property, a scalar "
        "expression, or SUM/COUNT/AVG/MIN/MAX over a declared type"
    )
