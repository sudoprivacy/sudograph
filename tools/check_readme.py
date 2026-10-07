"""Run every command the README tells a reader to run, and fail if one is dead.

The README is the entry point for the only reader that matters here: a model
handed this repo and a database, asked to produce an ontology. It does not
explore — it does what the front page shows. So a command on the front page that
no longer works is not a documentation blemish, it is the tool being broken for
its primary user, and it is invisible to a test suite that imports the modules
directly.

This exists because the README drifted exactly that way: it showed a `--period`
flag that had been renamed to `--at`, and said nothing at all about `--measure`
or about reading a database — while the compiler's own output was telling people
to run `--measure`. Everything in the repo was green.

So the fix is not to correct the prose. It is to make the prose executable, which
is the only form of documentation that cannot go stale quietly.

What counts as a failure, and why:

  exit 2   the invocation or the spec is invalid — a flag that no longer exists,
           a spec file that moved. This is drift, and it is the whole point.
  exit 1   a bug in the compiler, reached through a path the README advertises.
  exit 3   a check failed. A command shown on the front page is shown because it
           works; if one is meant to demonstrate a failure, say so in the README
           with `# fails:` and this will require it to fail.
  exit 4   the data the spec reads is not on this machine. Skipped and counted
           apart, never passed: the front page may show a command over a
           customer database or a 23 MB download, and that command is not wrong
           on a CI runner that has no copy of it. A skip reported as a pass is
           how a suite stops meaning anything.

Output paths are redirected into a temporary directory, so running the README
cannot leave files behind in the repo. Nothing else about a command is altered —
a check that ran something other than what the page shows would prove nothing.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Flags whose value is a file this writes. Redirected to a temp directory so a
#: check of the documentation does not litter the working tree.
_WRITES = ("--app",)

#: Marker in a README comment for a command that is supposed to fail, so the
#: page can show one. Without it a non-zero exit is the drift this looks for.
_EXPECT_FAIL = re.compile(r"#\s*fails:")

#: Commands that would run this one again. Both belong on the README — they are
#: things a reader should run — and running either from here recurses until
#: something gives out.
_RECURSIVE = ("tools.check_readme", "tools.verify")

#: The compiler's exit code for "the spec is fine, the data it reads is not on
#: this machine". Named once here rather than written as a bare 4 at the one
#: place it is compared, because it is the compiler's protocol and not ours.
_SOURCE_UNAVAILABLE = 4


def commands(readme: str) -> list[tuple[int, str, bool]]:
    """Every `python -m ...` line in the README, with its line number.

    Read line by line rather than by parsing fenced blocks: the thing being
    checked is "a reader copies this line and runs it", and a reader does not
    care which block it came from.
    """
    out = []
    for n, line in enumerate(readme.splitlines(), 1):
        text = line.strip()
        if not text.startswith("python -m ") or any(r in text for r in _RECURSIVE):
            continue
        fails = bool(_EXPECT_FAIL.search(text))
        out.append((n, text.split("#")[0].strip(), fails))
    return out


def _redirected(argv: list[str], outdir: str) -> list[str]:
    if len(argv) >= 5 and argv[2] == 'compiler.project':
        argv = list(argv)
        argv[4] = os.path.join(outdir, os.path.basename(argv[4]))
    done = []
    for i, a in enumerate(argv):
        if i and argv[i - 1] in _WRITES:
            done.append(os.path.join(outdir, os.path.basename(a)))
        else:
            done.append(a)
    return done


def main(argv: list[str] | None = None) -> int:
    """`argv` may name a README other than this repo's, so this is testable.

    A checker nobody has watched fail is a checker that might only ever print
    "ok" — the one failure mode that looks exactly like success.
    """
    path = (argv or [None])[0] or os.path.join(ROOT, "README.md")
    with open(path, encoding="utf-8") as fh:
        found = commands(fh.read())
    if not found:
        # Silence is not evidence: if the extraction stops matching, this must
        # say so rather than report a clean run over nothing.
        print(f"no commands found in {path} — the extraction is broken", file=sys.stderr)
        return 1

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    failures: list[str] = []
    skipped: list[str] = []
    with tempfile.TemporaryDirectory() as outdir:
        for line_no, cmd, expect_fail in found:
            argv = _redirected(shlex.split(cmd), outdir)
            argv = [sys.executable if a == "python" else a for a in argv]
            p = subprocess.run(
                argv, cwd=ROOT, env=env, capture_output=True, text=True,
                encoding="utf-8", check=False,
            )
            if p.returncode == _SOURCE_UNAVAILABLE:
                why = ((p.stderr or "").strip().splitlines() or [""])[-1]
                skipped.append(f"README:{line_no} {cmd} — {why}")
                print(f"  SKIP  README:{line_no}  {cmd}")
                print(f"        {why}")
                continue
            bad = (p.returncode == 0) if expect_fail else (p.returncode != 0)
            want = "fail" if expect_fail else "succeed"
            print(f"  {'FAIL' if bad else 'ok  '}  README:{line_no}  {cmd}")
            if bad:
                tail = (p.stderr or p.stdout or "").strip().splitlines()
                failures.append(
                    f"README:{line_no} is supposed to {want} and exited "
                    f"{p.returncode}: {cmd}\n      " + "\n      ".join(tail[-6:])
                )

    ran = len(found) - len(skipped)
    print(f"\n{ran} command(s) run" + (f", {len(skipped)} skipped" if skipped else ""))
    for f in failures:
        print(f"FAIL {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
