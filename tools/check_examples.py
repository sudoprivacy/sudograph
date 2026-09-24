"""Every example loads, matches the schema, and passes its own checks.

Run in CI. The compiler's own tests assert on two fixtures; this asserts on all
of them, so an example that has quietly stopped compiling fails the build rather
than misleading the next person who copies it.

Exits non-zero with the list of failures — never on silence. An empty output
here must mean "found examples and they were fine", not "found none".
"""

from __future__ import annotations

import os
import sys

import jsonschema
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler import compile as compile_mod
from compiler import diff as diff_mod
from compiler import spec as spec_mod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")
SCHEMA = os.path.join(ROOT, "schema", "spec.schema.json")


def main() -> int:
    with open(SCHEMA, encoding="utf-8") as fh:
        schema = yaml.safe_load(fh)
    validator = jsonschema.Draft202012Validator(schema)

    paths = sorted(
        os.path.join(EXAMPLES, f)
        for f in os.listdir(EXAMPLES)
        if f.endswith((".yaml", ".yml"))
    )
    if not paths:
        print(f"no examples found under {EXAMPLES} — nothing was checked", file=sys.stderr)
        return 1

    failures: list[str] = []
    for path in paths:
        name = os.path.relpath(path, ROOT)
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        for e in sorted(validator.iter_errors(doc), key=lambda e: list(e.path)):
            failures.append(f"{name}: schema: {'/'.join(str(p) for p in e.path)}: {e.message}")

        try:
            s = spec_mod.load(path)
        except spec_mod.SpecError as e:
            failures.append(f"{name}: {e}")
            continue

        bases = s.bases or [None]
        for basis in bases:
            c = compile_mod.compile_spec(s, basis=basis)
            where = f"{name}" + (f" <{basis}>" if basis else "")
            for k in c.checks:
                if not k.ok:
                    failures.append(f"{where}: check {k.name}: {k.detail}")
            print(f"  ok  {where}: {c.summary()}")

        # A declared pair of bases must also reconcile: every difference either
        # is an entry or is attributed to one. An unexplained movement between
        # the two sets of figures is the failure this whole design prevents.
        if len(s.bases) >= 2:
            d = diff_mod.diff(s, s.bases[0], s.bases[1])
            for node in d.unexplained:
                failures.append(f"{name}: {node} differs between bases with no entry above it")
            print(
                f"  ok  {name} {s.bases[0]} -> {s.bases[1]}: "
                f"{len(d.entries)} entries, {len(d.carried)} carried, posted {d.posted():,}"
            )

    print(f"\n{len(paths)} example(s) checked")
    for f in failures:
        print(f"FAIL {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
