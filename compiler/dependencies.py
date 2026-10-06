"""Resolve expression dependencies in their row scope, including ref paths."""

from . import expr


def validate_names(s, ast, row_type=None, *, allow_this=False):
    """Bind every name before reading any rows, including empty input tables."""
    def path(tname, parts):
        if tname not in s.types:
            raise expr.ExprError(f'unknown type {tname!r}; use a declared graph type')
        for i, name in enumerate(parts):
            if name not in s.types[tname].get('props', {}):
                raise expr.ExprError(
                    f'{tname} has no property {name!r}; inspect the column mapping')
            if i < len(parts) - 1:
                target = s.links_of(tname).get(name)
                if not target:
                    raise expr.ExprError(f'{tname}.{name} is not a declared ref; declare the link')
                tname = target

    if isinstance(ast, expr.Ref):
        if ast.name == 'this' and allow_this:
            return
        if row_type and ast.name in s.types[row_type].get('props', {}):
            return
        if ast.name not in (set(s.nodes) | set(s.raw) | set(s.hooks)):
            if row_type:
                raise expr.ExprError(
                    f'{ast.name!r}, which is neither a property of {row_type!r} '
                    'nor a declared scalar node; inspect the graph property names')
            raise expr.ExprError(f'unknown name {ast.name!r}; use a declared property or node')
    elif isinstance(ast, expr.Path):
        path(row_type, ast.parts)
    elif isinstance(ast, expr.Select):
        path(ast.type_name, ast.prop.split('.') if ast.prop else [])
        validate_names(s, ast.where, ast.type_name, allow_this=allow_this)
    elif isinstance(ast, (expr.Not, expr.Neg, expr.IsNull)):
        validate_names(s, ast.operand, row_type, allow_this=allow_this)
    elif isinstance(ast, expr.Bin):
        validate_names(s, ast.left, row_type, allow_this=allow_this)
        validate_names(s, ast.right, row_type, allow_this=allow_this)


def vertices(s, ast, row_type=None):
    def prop(tname, parts):
        out = set()
        for i, name in enumerate(parts):
            definition = (s.types.get(tname, {}).get('props') or {}).get(name, {})
            if 'op' in definition:
                out.add(('prop', tname, name))
            if i < len(parts) - 1:
                tname = s.links_of(tname).get(name)
                if not tname:
                    break
        return out

    if isinstance(ast, expr.Ref):
        if row_type and ast.name in s.types[row_type].get('props', {}):
            return prop(row_type, [ast.name])
        return {('node', ast.name)} if ast.name in s.nodes else set()
    if isinstance(ast, expr.Path):
        return prop(row_type, ast.parts) if row_type else set()
    if isinstance(ast, expr.Select):
        return (prop(ast.type_name, ast.prop.split('.')) if ast.prop else set()) | vertices(
            s, ast.where, ast.type_name)
    if isinstance(ast, (expr.Not, expr.Neg, expr.IsNull)):
        return vertices(s, ast.operand, row_type)
    if isinstance(ast, expr.Bin):
        return vertices(s, ast.left, row_type) | vertices(s, ast.right, row_type)
    return set()
