"""Command line entry point.

Exit codes are a branching protocol, not decoration: a calling agent should be
able to tell "the spec is wrong" from "a check failed" from "I broke the tool",
without parsing prose.

  0  spec loaded and every check passed
  2  the spec is invalid (fix the spec)
  3  the spec is valid but a check failed (fix the ontology or the materials)
  4  the spec is fine but the data it reads is not reachable from here
     (bring the source, or run where it is — nothing is wrong with the spec)
  1  anything else (a bug here)

4 is separate from 2 because it is the one failure that is nobody's mistake: a
spec bound to a customer's warehouse is correct on a laptop that cannot see the
warehouse. Folded into 2 it reads as "your spec is broken", which sends the
reader to edit a file that is right.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

from . import app as app_mod
from . import bind as bind_mod
from . import compile as compile_mod
from . import diff as diff_mod
from . import measure as measure_mod
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
    w = d.vocab
    print(f"{d.ontology}  {before} -> {after}" + _where(d.at))
    print()
    print(f"{w['entry_noun']} ({len(d.entries)})")
    for e in d.entries:
        print(f"  {e.node}: {_money(e.before)} -> {_money(e.after)}  ({_money(e.amount)})")
        if e.posts:
            print("      " + "  ".join(f"{slot} {where}" for slot, where in e.posts.items()))
        else:
            print(f"      (memo — nothing lands, not in {w['posted_noun']})")
        print(f"      because: {e.because}")
    print(f"  {w['posted_noun']} {_money(d.posted())}"
          f"   (all differences {_money(d.total())})")

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
    ap.add_argument('--lang', choices=['auto', *app_mod.languages()], default='zh',
                    help='graph language (default zh); auto follows browser, '
                         'en uses declared translations')
    ap.add_argument(
        "--app",
        metavar="OUT.html",
        help="write the self-contained graph app: every reading, every slice and "
        "every bridge computed here and inlined, so the renderer only picks",
    )
    ap.add_argument('--records', action='store_true',
                    help='include complete, compressed record pages in a portable export')
    ap.add_argument('--questions', help='include public blind questions; private oracles refuse')
    ap.add_argument(
        "--diff",
        metavar="BEFORE:AFTER",
        help="compile under both readings and derive the entries between them",
    )
    ap.add_argument(
        "--measure",
        action="store_true",
        help=(
            "ask the ontology questions generated from itself and report how it did. "
            "The exit code says whether the run happened, never how well it went — a "
            "score that can block a change stops being a measurement"
        ),
    )
    args = ap.parse_args(argv)
    try:
        at = _coords(args.at)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    try:
        s = spec_mod.load(args.spec)
    except bind_mod.SourceUnavailable as e:
        print(f"{e} — the spec is fine, the data is not here", file=sys.stderr)
        return 4
    except spec_mod.SpecError as e:
        print(str(e), file=sys.stderr)
        return 2

    if args.app:
        try:
            b = app_mod.bundle(s, fold_over=args.fold_over, top_n=args.top_n, records=args.records)
            if args.questions:
                with open(args.questions, encoding='utf-8') as fh:
                    b['challenge'] = json.load(fh)
                app_mod.blind.public_only(b['challenge'])
            html = app_mod.render(b, language=args.lang)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        target = os.path.abspath(args.app)
        staging = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                             dir=os.path.dirname(target), delete=False) as fh:
                staging = fh.name
                fh.write(html)
            os.replace(staging, target)
        finally:
            if staging and os.path.exists(staging):
                os.unlink(staging)
        print(f"{args.app}: {len(b['views'])} view(s), {len(b['diffs'])} bridge diff(s)")
        return 0

    if args.measure:
        try:
            run = measure_mod.correctness(s, basis=args.basis, at=at)
        except measure_mod.Tampered as e:
            print(str(e), file=sys.stderr)
            return 2
        if args.view:
            print(json.dumps(run.as_dict(), ensure_ascii=False, indent=2))
            return 0
        passed, total = run.score()
        for r in run.results:
            print(f"  {'ok  ' if r.ok else 'FAIL'} {r.id}")
            print(f"       {r.asks}")
            for line in r.trace:
                print(f"       · {line}")
            if not r.ok:
                print(f"       expected {r.expected}, got {r.got}")
        print(f"\n{passed}/{total} — {s.name}")
        for item in run.uncovered:
            print(f"  UNMEASURED {item['node']}: {item['reason']}")
        if passed != total:
            # Reported, never enforced. A number that falls is something to
            # explain; a harness that blocks on it is something to route around.
            print(
                "a falling score is a thing to explain, not a thing to block on",
                file=sys.stderr,
            )
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
    # Said here because here is where the reader — person or agent — is deciding
    # what to do next. A capability named only in `--help` is one nobody reaches
    # for, and "it compiled" is exactly the moment the next question is "and is
    # it right?". The count is real: it is how many questions this spec can
    # already be asked about itself.
    askable = len(measure_mod.correctness(s, basis=args.basis, at=at).results)
    if askable:
        print(
            f"\n{askable} question(s) can be generated from this spec and checked "
            f"against the source — run it with --measure"
        )
    return 0 if c.passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
