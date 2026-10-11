"""Refuse hand-edited or unregistered HTML deliverables under examples."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from compiler import business
from compiler.spec import read_document
from tools import check_baselines

ROOT = Path(__file__).resolve().parents[1]


def check_tree(root: Path) -> dict:
    paths = set(root.rglob("*.html"))
    if not paths:
        raise ValueError("no HTML deliverables found; empty checks are refused")
    checked = set()
    for path in root.rglob("baseline.json"):
        manifest = json.loads(path.read_text(encoding="utf8"))
        if manifest.get("format") != check_baselines.FORMAT:
            continue
        # Archives use their pinned historical renderer. Their exact locked bytes,
        # including HTML outside the model, must remain unchanged.
        check_baselines.check(path)
        checked.update(
            path.parent / item["path"]
            for item in manifest["files"] if item["path"].endswith(".html")
        )
    for path in [*root.rglob("*.yaml"), *root.rglob("*.yml")]:
        doc = read_document(str(path))
        if not isinstance(doc, dict) or not str(doc.get("format", "")).startswith(
            "sudograph-business-overlay/"
        ):
            continue
        for name, language in [("index.html", "en"), ("review.html", "zh")]:
            artifact = path.with_name(name)
            if artifact not in paths:
                continue
            if artifact in checked:
                raise ValueError(f"{artifact}: multiple generation owners")
            if business.main([str(path), "--check-app", str(artifact), "--lang", language]):
                raise ValueError(f"{artifact}: full regeneration check failed")
            checked.add(artifact)
    unknown = paths - checked
    if unknown:
        raise ValueError(
            "unregistered HTML deliverables; declare their checked generation input "
            f"or frozen baseline: {sorted(str(p) for p in unknown)}"
        )
    return {"artifacts": len(paths), "checked": len(checked)}


def main() -> int:
    try:
        print(json.dumps(check_tree(ROOT / "examples")))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Generated export refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
