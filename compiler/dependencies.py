"""Resolve expression dependencies in their row scope, including ref paths."""

from . import expr


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
