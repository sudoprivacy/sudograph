"""Source-only entry point. Schema facts are discovered; business rules are refused."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from . import bind, catalog


def draft(dsn: str, *, base=".", name="Source projection") -> dict:
    objects = catalog.scan(dsn, base)
    tables = {o["name"]: o for o in objects if o["kind"] == "table"}
    exclude = {}
    types = {}
    for obj in objects:
        key = [c["name"] for c in sorted(obj["columns"], key=lambda c: c["pk"]) if c["pk"]]
        if obj["kind"] == "view" or not key:
            exclude[obj["name"]] = (
                "No declared primary key; source schema and snapshot preserved "
                "without guessed row identity."
            )
            continue
        props = {}
        for col in obj["columns"]:
            if "BLOB" in col["type"].upper():
                exclude[obj["name"] + "." + col["name"]] = (
                    "Binary payload preserved losslessly in the source snapshot, "
                    "outside scalar business properties."
                )
                continue
            affinity = col["type"].upper()
            numeric = any(
                token in affinity for token in ("INT", "REAL", "NUM", "DEC", "DOUB", "FLOA")
            )
            p = {
                "type": "number" if numeric else "string",
                "owner": "source",
                "column": col["name"],
            }
            if not col["notnull"] and not col["pk"]:
                p.update(nullable=True, absent="none")
            props[col["name"]] = p
        types[obj["name"]] = {
            "label": obj["name"],
            "backing": {"from": "SOURCE", "table": obj["name"], "key": key},
            "props": props,
        }
        # Display is presentation, never identity. Select only an unambiguous
        # named source field; multiple candidates keep the declared key label.
        display = [p for p, d in props.items() if d["type"] == "string" and
                   (p.lower() in ("name", "label", "title") or p.lower().endswith("name"))]
        if len(display) == 1:
            types[obj["name"]]["display"] = display[0]
    for name_, t in types.items():
        for fk in tables[name_]["foreign_keys"]:
            if sum(f["id"] == fk["id"] for f in tables[name_]["foreign_keys"]) > 1:
                raise ValueError(
                    f"{name_}: composite foreign keys require an unsupported ref contract"
                )
            target = types.get(fk["table"])
            if target and target["backing"]["key"] == [fk["to"]]:
                t["props"][fk["from"]].update(type="ref", to=fk["table"])
            else:
                # Never silently drop or misrepresent a composite relationship.
                raise ValueError(
                    f"{name_}.{fk['from']}: foreign key requires a composite/ref contract "
                    "not supported here"
                )
    return {
        "ontology": name,
        "mode": "source_projection",
        "raw": {
            "SOURCE": {
                "label": "Read-only source",
                "dsn": dsn,
                "coverage": "complete",
                "exclude": exclude,
            }
        },
        "types": types,
    }


def verify_projection(s):
    errors = []
    for name in ("instances", "hooks", "nodes", "ops", "checks", "bases", "bridges", "dimensions"):
        if getattr(s, name):
            errors.append(
                f"{name}: source_projection cannot introduce business rules, decisions "
                "or copied facts; use mode: business for phase two"
            )
    inventories = {}
    for raw, definition in s.raw.items():
        if (
            not definition.get("dsn")
            or definition.get("coverage") != "complete"
            or definition.get("value") is not None
        ):
            errors.append(
                f"{raw}: source_projection requires a read-only DSN and complete coverage inventory"
            )
        else:
            inventories[raw] = {
                o["name"]: o for o in catalog.scan(definition["dsn"], s.source_base)
            }
            exclusions = definition.get("exclude") or {}
            for obj in inventories[raw].values():
                if obj["name"] in exclusions and obj["kind"] == "table" and any(
                    c["pk"] for c in obj["columns"]
                ):
                    errors.append(f"{obj['name']}: cannot exclude a keyed source table "
                                  "from source_projection")
                for col in obj["columns"]:
                    if (obj["name"] + "." + col["name"] in exclusions and
                            "BLOB" not in col["type"].upper()):
                        errors.append(f"{obj['name']}.{col['name']}: cannot exclude a "
                                      "source scalar column from source_projection")
    for tn, t in s.types.items():
        b = s.backing_of(tn)
        obj = inventories.get(b.get("from"), {}).get(b.get("table"))
        if not obj or obj["kind"] != "table":
            errors.append(
                f"{tn}: source_projection needs a source table with a declared primary key"
            )
            continue
        key = [c["name"] for c in sorted(obj["columns"], key=lambda c: c["pk"]) if c["pk"]]
        if not key or b.get("key") != key:
            errors.append(
                f"{tn}: key must match declared source primary key {key}; do not infer identity"
            )
        if t.get("id") and [s.column_of(tn, t["id"])] != key:
            errors.append(f"{tn}: id must preserve the full declared primary key {key}")
        for pn, p in t["props"].items():
            if (
                "op" in p
                or p.get("owner") != "source"
                or p.get("gap")
                or p.get("additive")
                or p.get("absent") in ("gap", "zero")
            ):
                errors.append(
                    f"{tn}.{pn}: source_projection permits source fields only; NULL stays NULL, "
                    "business formulas/meaning belong to phase two"
                )
            if p.get("from") and p["from"] != b["from"]:
                errors.append(f"{tn}.{pn}: field must come from its declared table")
            if p.get("type") != "ref":
                continue
            target = s.backing_of(p.get("to"))
            column = s.column_of(tn, pn)
            declared = target.get("from") == b.get("from") and any(
                fk["from"] == column
                and fk["table"] == target.get("table")
                and [fk["to"]] == target.get("key")
                for fk in obj["foreign_keys"]
            )
            same_key = (
                target.get("from") == b.get("from")
                and target.get("table") == b.get("table")
                and target.get("key") == [column] == key
            )
            if not declared and not same_key:
                errors.append(
                    f"{tn}.{pn}: ref has no declared source foreign key "
                    "or same-table primary-key evidence"
                )
    if errors:
        raise ValueError("source_projection contract refused:\n  - " + "\n  - ".join(errors))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dsn")
    ap.add_argument("output")
    ap.add_argument("--name", default="Source projection")
    ap.add_argument("--app", help="also compile the validated projection to a graph HTML")
    ap.add_argument("--records", action="store_true", help="include complete record pages")
    args = ap.parse_args(argv)
    output = Path(args.output).resolve()
    from . import cli, spec  # noqa: PLC0415 — spec validates through this module

    try:
        # A source argument is relative to the command's working directory;
        # persist its absolute identity so an output directory cannot rebase it.
        dsn = "sqlite:///" + Path(bind._path_of(args.dsn, ".")).resolve().as_posix()
        doc = draft(dsn, name=args.name)
        output.write_text(
            yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        spec.load(str(output), expected_mode="source_projection")
    except bind.SourceUnavailable as e:
        print(str(e), file=sys.stderr)
        return 4
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(f"Validated source projection: {output}")
    if args.app:
        return cli.main([str(output), "--mode", "source_projection", "--app", args.app,
                         *(["--records"] if args.records else [])])
    return 0


if __name__ == "__main__":
    sys.exit(main())
