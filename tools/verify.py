"""Everything CI runs, in one command, so a local green means a green build.

This exists because of a specific failure. CI was red on `main` for five
consecutive commits — a lint gate, failing from the first commit that added the
pinned linter — and every one of those commits was pushed after a local run that
said everything passed. The local run was the test suite. The gate was not.

A verification scope that differs from CI's is not a weaker check, it is a
misleading one: it returns zero and means nothing about whether the build is
green. So the scope is stated once, here, and `.github/workflows/ci.yml` runs
this rather than listing the steps a second time. Two lists of the same steps
drift, and the way they drift is that the local one gets shorter.

Each step says what it is for, because a gate whose purpose is unstated is a
gate that gets deleted the first time it is inconvenient.
"""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: (argv, why). Ordered cheapest-first so the fastest signal arrives first.
STEPS: list[tuple[list[str], str]] = [
    (
        ["ruff", "check", "compiler", "tests", "tools"],
        "the rule set is committed, so this is the same gate everywhere",
    ),
    (
        [sys.executable, "-m", "pytest", "-q"],
        "the compiler's own behaviour",
    ),
    (
        [sys.executable, "-m", "tools.check_examples"],
        "every example still loads, validates and passes its own checks",
    ),
    (
        [sys.executable, "-m", "tools.check_baselines"],
        "frozen source examples retain their file hashes and complete source manifests",
    ),
    (
        [sys.executable, "-m", "tools.check_readme"],
        "every command the front page shows still works",
    ),
]


def main() -> int:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    failed: list[str] = []
    for argv, why in STEPS:
        shown = " ".join(argv[1:] if argv[0] == sys.executable else argv)
        print(f"\n=== {shown}  —  {why}", flush=True)
        code = subprocess.run(argv, cwd=ROOT, env=env, check=False).returncode
        if code:
            failed.append(f"{shown} exited {code}")
    print()
    for f in failed:
        print(f"FAIL {f}", file=sys.stderr)
    print(f"{len(STEPS) - len(failed)}/{len(STEPS)} step(s) passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
