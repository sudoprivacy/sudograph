"""Compile a scalar aggregate, following only the spec's declared many-to-one refs.

The join grain is fixed: every input row contributes at most once. A path cannot
invent an ON condition, cross databases or point at a non-scalar identity. A
LEFT JOIN preserves unmatched rows; absence is checked separately, never hidden
by dropping facts from an inner join.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import expr


class NotPushable(Exception):
    """The source cannot answer this expression; use rows only if they are present."""


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@dataclass
class Query:
    sql: str
    params: dict[str, Any]
    dsn: str


@dataclass
class Builder:
    spec: Any
    at: dict = field(default_factory=dict)
    basis: str | None = None
    scope: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)
    serial: int = 0
    dsn: str | None = None
    expanding: set = field(default_factory=set)

    def parameter(self, value):
        key = f"p{len(self.params)}"
        self.params[key] = value
        return f":{key}"

    def row(self, tname, joins):
        b = self.spec.backing_of(tname)
        if not b:
            raise NotPushable(f"{tname} is not backed by a table")
        dsn = self.spec.raw[b['from']]['dsn']
        if self.dsn is not None and self.dsn != dsn:
            raise NotPushable("a path crosses data sources; no federated query is available")
        self.dsn = dsn
        alias = f"t{self.serial}"
        self.serial += 1
        return Row(self, tname, alias, joins)

    def select(self, node, outer_this=None):
        joins = []
        row = self.row(node.type_name, joins)
        column = '*' if node.prop is None else row.path(tuple(node.prop.split('.')))
        if node.func not in expr.AGGREGATES:
            raise NotPushable(f"unsupported aggregate {node.func}")
        head = f"{node.func.upper()}({column})"
        if node.func == 'sum':
            head = f"COALESCE({head}, 0)"
        clauses = row.filters()
        if node.where is not None:
            clauses.append(self.emit(node.where, row, outer_this))
        tail = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        return f"SELECT {head} FROM {row.source()} {' '.join(joins)}{tail}"

    def emit(self, node, row, this=None, *, decimal_math=False):
        if isinstance(node, expr.Lit):
            return self.parameter(node.value)
        if isinstance(node, expr.Ref):
            if node.name == 'this' and this is not None:
                return this
            if node.name in row.props:
                return row.property(node.name)
            if node.name in self.scope:
                return self.parameter(self.scope[node.name])
            raise NotPushable(f"unknown name {node.name!r} in {row.tname}")
        if isinstance(node, expr.Path):
            return row.path(node.parts)
        if isinstance(node, expr.Select):
            return '(' + self.select(node, this) + ')'
        if isinstance(node, (expr.Not, expr.Neg)):
            op = 'NOT ' if isinstance(node, expr.Not) else '-'
            return f"({op}{self.emit(node.operand, row, this, decimal_math=decimal_math)})"
        if isinstance(node, expr.IsNull):
            op = 'IS NOT NULL' if node.negated else 'IS NULL'
            return f"({self.emit(node.operand, row, this)} {op})"
        if isinstance(node, expr.Bin):
            left = self.emit(node.left, row, this, decimal_math=decimal_math)
            right = self.emit(node.right, row, this, decimal_math=decimal_math)
            if decimal_math and node.op in ('+', '-', '*', '/'):
                # SQLite UDFs carry intermediate decimals as text. Only sg_round
                # converts the final value back to a database numeric value.
                names = {'+': 'add', '-': 'sub', '*': 'mul', '/': 'div'}
                return f"sg_decimal_{names[node.op]}({left}, {right})"
            if node.op == '/':
                # SQLite truncates integer division; the ontology uses ratios.
                return f"sg_div({left}, {right})"
            if node.op not in ('=', '!=', '<', '<=', '>', '>=', '+', '-', '*', 'and', 'or'):
                raise NotPushable(f"unsupported operator {node.op}")
            return f"({left} {node.op.upper()} {right})"
        raise NotPushable(f"unsupported expression {type(node).__name__}")


@dataclass
class Row:
    builder: Builder
    tname: str
    alias: str
    joins: list
    targets: dict = field(default_factory=dict)

    @property
    def props(self):
        return self.builder.spec.types[self.tname].get('props') or {}

    def source(self):
        b = self.builder.spec.backing_of(self.tname)
        # Existing backing.where is a source-side selection, scoped before joins.
        table = quote(b['table'])
        if b.get('where'):
            table = f"(SELECT * FROM {table} WHERE {b['where']})"
        return f"{table} AS {self.alias}"

    def filters(self):
        s = self.builder.spec
        return [f"{self.property(axis)} = {self.builder.parameter(value)}"
                for dim, value in self.builder.at.items()
                if (axis := s.axis_of(self.tname, dim))]

    def property(self, name):
        s = self.builder.spec
        definition = self.props.get(name)
        if definition is None:
            raise NotPushable(f"{self.tname} has no property {name!r}")
        if 'op' not in definition:
            if s.owner_of(self.tname, name) != 'source' or isinstance(definition.get('from'), list):
                raise NotPushable(f"{self.tname}.{name} is not a single source column")
            return f"{self.alias}.{quote(s.column_of(self.tname, name))}"
        key = (self.tname, name)
        if key in self.builder.expanding:
            raise NotPushable(f"cycle through computed property {self.tname}.{name}")
        self.builder.expanding.add(key)
        try:
            source = definition.get(f'op@{self.builder.basis}', definition['op'])
            ids = s.id_props(self.tname)
            identity = self.property(ids[0]) if len(ids) == 1 else None
            result = self.builder.emit(expr.parse(source), self, identity,
                                       decimal_math=definition.get('type') == 'money')
            if definition.get('type') == 'money':
                result = f"sg_round({result}, {int(definition.get('scale', 0))})"
            return result
        finally:
            self.builder.expanding.remove(key)

    def path(self, parts):
        if len(parts) == 1:
            return self.property(parts[0])
        prop = parts[0]
        s = self.builder.spec
        target = s.links_of(self.tname).get(prop)
        if not target:
            raise expr.ExprError(
                f"{self.tname}.{prop} is not a declared ref; declare the relationship "
                "before following it. A path cannot invent a join condition"
            )
        ids = s.id_props(target)
        if len(ids) != 1:
            raise expr.ExprError(
                f"{self.tname}.{prop} points to {target} with a composite identity; "
                "a scalar ref cannot name it. Bind a unique scalar key first"
            )
        if prop not in self.targets:
            related = self.builder.row(target, self.joins)
            on = [f"{self.property(prop)} = {related.property(ids[0])}", *related.filters()]
            self.joins.append(f"LEFT JOIN {related.source()} ON " + ' AND '.join(on))
            self.targets[prop] = related
        return self.targets[prop].path(parts[1:])


def compile_query(s, node, *, at=None, basis=None, scope=None):
    builder = Builder(s, dict(at or {}), basis, dict(scope or {}))
    sql = builder.select(node)
    return Query(sql, builder.params, builder.dsn)


def link_resolver(s):
    """The row evaluator follows the same declared refs, without SQL joins."""
    indexes = {}

    def resolve(tname, parts, row):
        prop = parts[0]
        if prop not in s.types[tname]['props']:
            raise expr.ExprError(f"{tname} has no property {prop!r}")
        if len(parts) == 1:
            return row.get(prop)
        target = s.links_of(tname).get(prop)
        if not target or len(s.id_props(target)) != 1:
            raise expr.ExprError(f"{tname}.{prop} must be a declared ref to a scalar identity")
        if row.get(prop) is None:
            return None
        if target in s.unloaded:
            raise expr.ExprError(f"{target} is not loaded; use the source query path")
        if target not in indexes:
            indexes[target] = {s.identify(target, r): r for r in s.instances.get(target, [])}
        related = indexes[target].get(row[prop])
        return None if related is None else resolve(target, parts[1:], related)

    return resolve
