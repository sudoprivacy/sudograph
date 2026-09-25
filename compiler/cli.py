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
import json
import sys

from . import app as app_mod
from . import compile as compile_mod
from . import diff as diff_mod
from . import spec as spec_mod


def _where(at: dict) -> str:
    return "  [" + " ".join(f"{k}={v}" for k, v in at.items()) + "]" if at else ""


def _coords(pairs: list[str] | None) -> dict[str, str]:
    """`--at 期间=2023 --at 主体=北京` -> {"期间": "2023", "主体": "北京"}."""
    out: dict[str, str] = {}
    for p in pairs or []:
        if "=" not in p:
            raise ValueError(f"--at takes <dimension>=<value>, got {p!r}")
        dim, _, value = p.partition("=")
        out[dim] = value
    return out


def _money(v: object) -> str:
    return f"{v:,}" if isinstance(v, (int, float)) else str(v)


def _report_diff(d: diff_mod.Diff, *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(d.as_dict(), ensure_ascii=False, indent=2))
        return 0 if d.explained else 3

    before, after = d.bases
    print(f"{d.ontology}  {before} -> {after}" + _where(d.at))
    print()
    print(f"adjusting entries ({len(d.entries)})")
    for e in d.entries:
        print(f"  {e.node}: {_money(e.before)} -> {_money(e.after)}  ({_money(e.amount)})")
        if e.debit and e.credit:
            print(f"      Dr {e.debit}  Cr {e.credit}")
        else:
            print("      (memo — posts nowhere)")
        print(f"      because: {e.because}")
    print(f"  posted {_money(d.posted())}   (all differences {_money(d.total())})")

    if d.carried:
        print()
        print(f"carried ({len(d.carried)}) — moved by an entry above, not booked again")
        for c in d.carried:
            origin = ", ".join(c.origins) if c.origins else "nothing — unexplained"
            print(f"  {c.node}: {_money(c.amount)}  <- {origin}")

    if d.unexplained:
        print()
        for name in d.unexplained:
            print(f"  FAIL basis/{name}: differs between bases with no entry above it")
    return 0 if d.explained else 3


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
    ap.add_argument(
        "--at",
        action="append",
        metavar="DIM=VALUE",
        help="restrict to one slice, e.g. --at 期间=2023; repeat for several dimensions. "
        "The spec is written once and fed different leaves",
    )
    ap.add_argument("--basis", help="compute under one declared basis")
    ap.add_argument(
        "--app",
        metavar="OUT.html",
        help="write the self-contained graph app: every reading, every slice and "
        "every bridge computed here and inlined, so the renderer only picks",
    )
    ap.add_argument(
        "--diff",
        metavar="BEFORE:AFTER",
        help="compile under both bases and derive the adjusting entries between them",
    )
    args = ap.parse_args(argv)
    try:
        at = _coords(args.at)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    try:
        s = spec_mod.load(args.spec)
    except spec_mod.SpecError as e:
        print(str(e), file=sys.stderr)
        return 2

    if args.app:
        try:
            b = app_mod.bundle(s, fold_over=args.fold_over, top_n=args.top_n)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        with open(args.app, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(app_mod.render(b))
        print(f"{args.app}: {len(b['views'])} view(s), {len(b['diffs'])} bridge diff(s)")
        return 0

    if args.diff:
        if ":" not in args.diff:
            print("--diff takes BEFORE:AFTER, two bases the spec declares", file=sys.stderr)
            return 2
        before, after = args.diff.split(":", 1)
        try:
            d = diff_mod.diff(
                s, before, after, at=at, fold_over=args.fold_over, top_n=args.top_n
            )
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        return _report_diff(d, as_json=args.view)

    try:
        c = compile_mod.compile_spec(
            s, fold_over=args.fold_over, top_n=args.top_n, at=at, basis=args.basis
        )
    except ValueError as e:
        # A missing basis or a cycle among derived nodes: the spec, or the way
        # it was asked, is wrong. That is exit 2, and a caller should read the
        # message rather than a traceback.
        print(str(e), file=sys.stderr)
        return 2

    if args.view:
        print(compile_mod.to_json(c))
        return 0 if c.passed else 3

    print(
        f"{s.name}"
        + _where(at)
        + (f"  <{args.basis}>" if args.basis else "")
    )
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
