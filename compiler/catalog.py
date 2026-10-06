"""Source-first inventory and coverage. No business names or database special cases."""

from __future__ import annotations

from . import bind
from .query import quote


def scan(dsn, base="."):
    """Enumerate empty tables, views, columns, keys and foreign keys as well as rows."""
    with bind.connect(dsn, base) as conn:
        result = []
        for obj in conn.execute(
            "SELECT name,type FROM sqlite_master WHERE type IN "
            "('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ):
            name = obj["name"]
            columns = [dict(r) for r in conn.execute(f"PRAGMA table_info({quote(name)})")]
            fks = [dict(r) for r in conn.execute(f"PRAGMA foreign_key_list({quote(name)})")]
            result.append(
                {
                    "name": name,
                    "kind": obj["type"],
                    "columns": columns,
                    "foreign_keys": fks,
                    "count": conn.execute(f"SELECT count(*) FROM {quote(name)}").fetchone()[0],
                }
            )
        return result


def coverage(s):
    sources = []
    for name, raw in s.raw.items():
        if not raw.get("dsn"):
            continue
        exemptions = raw.get("exclude") or {}
        if raw.get("coverage", "partial") not in ("partial", "complete"):
            raise ValueError(f"{name}.coverage must be partial or complete")
        if not isinstance(exemptions, dict) or any(
            not isinstance(v, str) or not v.strip() for v in exemptions.values()
        ):
            raise ValueError(f"{name}.exclude must map source object/column names to reasons")
        objects = scan(raw["dsn"], s.source_base)
        valid = {o["name"] for o in objects}
        valid |= {o["name"] + "." + c["name"] for o in objects for c in o["columns"]}
        unknown = set(exemptions) - valid
        if unknown:
            raise ValueError(f"{name}.exclude names missing source objects: {sorted(unknown)}")
        missing = []
        for obj in objects:
            table = obj["name"]
            types = [
                t
                for t in s.types
                if s.backing_of(t).get("from") == name and s.backing_of(t).get("table") == table
            ]
            mapped = {
                s.column_of(t, p)
                for t in types
                for p, d in s.types[t]["props"].items()
                if "op" not in d
            }
            obj["types"] = types
            obj["excluded"] = exemptions.get(table)
            obj["missing_columns"] = [
                c["name"]
                for c in obj["columns"]
                if c["name"] not in mapped and f"{table}.{c['name']}" not in exemptions
            ]
            obj["excluded_columns"] = {
                c["name"]: exemptions[f"{table}.{c['name']}"]
                for c in obj["columns"]
                if f"{table}.{c['name']}" in exemptions
            }
            obj["missing_refs"] = []
            for fk in obj["foreign_keys"]:
                represented = any(
                    s.column_of(t, p) == fk["from"]
                    and s.backing_of(target).get("from") == name
                    and s.backing_of(target).get("table") == fk["table"]
                    and s.backing_of(target).get("key") == [fk["to"]]
                    for t in types
                    for p, target in s.links_of(t).items()
                )
                if not represented:
                    obj["missing_refs"].append(fk)
            if not obj["excluded"]:
                if not types:
                    missing.append(f"{table}: no object binding")
                missing.extend(
                    f"{table}.{c}: no property or explicit exclusion"
                    for c in obj["missing_columns"]
                )
                missing.extend(
                    f"{table}.{f['from']} -> {f['table']}.{f['to']}: no ref"
                    for f in obj["missing_refs"]
                )
                # A filtered binding is not proof that all source facts arrived.
                # Prove coverage per mapped column; disjoint projections may
                # jointly cover it, and SQL NULL in a filter must count as omitted.
                for column in mapped:
                    carriers = [
                        t
                        for t in types
                        if any(
                            "op" not in d and s.column_of(t, p) == column
                            for p, d in s.types[t]["props"].items()
                        )
                    ]
                    predicates = [s.backing_of(t).get("where") for t in carriers]
                    if any(not p for p in predicates):
                        continue
                    union = " OR ".join(f"({p})" for p in predicates)
                    with bind.connect(raw["dsn"], s.source_base) as conn:
                        uncovered = conn.execute(
                            f"SELECT count(*) FROM {quote(table)} WHERE NOT COALESCE(({union}),0)"
                        ).fetchone()[0]
                    if uncovered:
                        missing.append(
                            f"{table}.{column}: {uncovered} source rows outside bindings"
                        )
        sources.append(
            {
                "source": name,
                "objects": objects,
                "missing": missing,
                "complete": not missing,
                "required": raw.get("coverage") == "complete",
            }
        )
    return sources


def enforce(s):
    reports = coverage(s)
    errors = [f"{r['source']}: {m}" for r in reports if r["required"] for m in r["missing"]]
    if errors:
        raise ValueError(
            "Source coverage is incomplete; bind the missing data or declare an "
            "explicit exclusion with its reason:\n" + "\n".join(errors)
        )
    return reports
