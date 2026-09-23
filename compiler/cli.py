"""Command line entry point.

Exit codes are a branching protocol, not decoration: a calling agent should be
able to tell "the spec is wrong" from "a check failed" from "I broke the tool",
without parsing prose.

  0  spec loaded and every check passed
  2  the spec is invalid (fix the spec)
  3  the spec is valid but a check failed (fix the ontology or the materials)
  1  anything else (a bug here)
"""

from __future__ import annotations

import argparse
import sys

from . import compile as compile_mod
from . import spec as spec_mod


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="compiler", description="Compile a sudograph spec.")
    ap.add_argument("spec", help="path to a spec YAML file")
    ap.add_argument("--view", action="store_true", help="print the view model as JSON")
    ap.add_argument(
        "--fold-over",
        type=int,
        default=20,
        help="fold an instance group larger than this in the view model (default 20)",
    )
    ap.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="how many rows a folded group surfaces per money column (default 5)",
    )
    args = ap.parse_args(argv)

    try:
        s = spec_mod.load(args.spec)
    except spec_mod.SpecError as e:
        print(str(e), file=sys.stderr)
        return 2

    c = compile_mod.compile_spec(s, fold_over=args.fold_over, top_n=args.top_n)

    if args.view:
        print(compile_mod.to_json(c))
        return 0 if c.passed else 3

    print(f"{s.name}")
    for name, value in c.values.items():
        shown = f"{value:,}" if isinstance(value, (int, float)) else value
        print(f"  {name} = {shown}")
    print()
    print(c.summary())
    for check in c.checks:
        if not check.ok:
            print(f"  FAIL {check.name}: {check.detail}")
    return 0 if c.passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
