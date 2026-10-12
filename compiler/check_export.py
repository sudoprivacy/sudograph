"""Verify a deliverable's reader before handoff, in any customer repository."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import app, html_export


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", help="native or packed graph HTML, at any path")
    parser.add_argument(
        "--model", help="operator-supplied checked model JSON; otherwise verify the embedded reader"
    )
    args = parser.parse_args(argv)
    try:
        saved = html_export.model(args.artifact)
        checked = json.loads(Path(args.model).read_text(encoding="utf8")) if args.model else saved
        app.check_export(args.artifact, checked, language=saved["ui"]["language"])
        print(json.dumps({
            "artifact": str(Path(args.artifact).resolve()), "reader": "verified",
            "checked_model_supplied": bool(args.model), "source_authority_verified": False,
        }))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Export refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
