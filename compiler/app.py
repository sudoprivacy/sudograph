"""Build the self-contained graph app.

The renderer holds no logic — that rule is easy to state and easy to lose the
moment the app needs a figure the compiler did not send. So the compiler sends
*everything*: every reading, every slice, and the diff across every declared
bridge, computed here and inlined into one HTML file.

The app then only picks. It cannot compute a figure, because it never has the
spec; it cannot disagree with the compiler, because it never evaluates anything.
The cost is a larger file, which is the right trade: a renderer that recomputes
is a second implementation of the ontology, and the two will disagree on the day
it matters most.

One file, no server, no network: a reviewer opens it from disk, or mails it.
"""

from __future__ import annotations

import itertools
import json
import os
from typing import Any

from . import compile as compile_mod
from . import diff as diff_mod
from .spec import Spec

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(_ROOT, "app", "index.html")

#: Every reading times every slice is compiled up front. A spec with several
#: dimensions of many values each would multiply into something nobody opens, so
#: the explosion is refused with the number rather than discovered as a hang.
MAX_VIEWS = 200


def coordinates(s: Spec) -> dict[str, list[str | None]]:
    """The values each dimension actually takes, plus None for "not sliced".

    Read from the instances rather than declared, because a declared value with
    no rows behind it is a slice that renders empty and teaches nothing.
    """
    out: dict[str, list[str | None]] = {}
    for dim in s.dimensions:
        seen: set[str] = set()
        for tname, rows in s.instances.items():
            col = s.axis_of(tname, dim)
            if not col:
                continue
            seen |= {r[col] for r in rows if r.get(col) is not None}
        out[dim] = [None, *sorted(seen)]
    return out


def _key(basis: str | None, at: dict[str, str]) -> str:
    coords = ",".join(f"{k}={v}" for k, v in sorted(at.items()))
    return f"{basis or ''}|{coords}"


def bundle(s: Spec, *, fold_over: int = 20, top_n: int = 5) -> dict[str, Any]:
    axes = coordinates(s)
    bases: list[str | None] = list(s.bases) or [None]
    combos = [
        dict(z for z in zip(axes, picked, strict=True) if z[1] is not None)
        for picked in itertools.product(*axes.values())
    ] or [{}]

    total = len(bases) * len(combos)
    if total > MAX_VIEWS:
        raise ValueError(
            f"{len(bases)} reading(s) x {len(combos)} slice(s) = {total} views, over the "
            f"{MAX_VIEWS} limit — narrow the dimensions, or render one slice at a time"
        )

    views: dict[str, Any] = {}
    for basis in bases:
        for at in combos:
            c = compile_mod.compile_spec(
                s, basis=basis, at=at, fold_over=fold_over, top_n=top_n
            )
            views[_key(basis, at)] = c.view

    # Bridges are the deliverable, so they are computed here too. With exactly
    # two readings the single pairing is implied; past that only the declared
    # ones are deliverables.
    pairs = (
        [(n, b["from"], b["to"]) for n, b in s.bridges.items()]
        if s.bridges
        else ([("", s.bases[0], s.bases[1])] if len(s.bases) == 2 else [])
    )
    diffs: dict[str, Any] = {}
    for name, before, after in pairs:
        for at in combos:
            d = diff_mod.diff(s, before, after, at=at, fold_over=fold_over, top_n=top_n)
            diffs[f"{name or f'{before}->{after}'}|{_key(None, at)[1:]}"] = d.as_dict()

    return {
        "ontology": s.name,
        "axes": axes,
        "bases": bases,
        "bridges": [
            {"name": n, "from": b["from"], "to": b["to"], "label": b.get("label", n)}
            for n, b in s.bridges.items()
        ]
        or ([{"name": "", "from": bases[0], "to": bases[1], "label": "bridge"}] if pairs else []),
        "views": views,
        "diffs": diffs,
    }


#: Inlined rather than linked. An audit deliverable is opened from disk at a
#: client site, and a CDN reference turns "open this file" into "open this file,
#: on a machine with internet, on a day the CDN is up". Both are MIT.
VENDOR = [
    os.path.join(_ROOT, "app", "vendor", "cytoscape.min.js"),
    os.path.join(_ROOT, "app", "vendor", "elk.bundled.js"),
    os.path.join(_ROOT, "app", "vendor", "cytoscape-elk.js"),
]


def render(b: dict[str, Any], template_path: str = TEMPLATE) -> str:
    with open(template_path, encoding="utf-8") as fh:
        html = fh.read()
    for placeholder in ("__BUNDLE__", "/*__VENDOR__*/"):
        if placeholder not in html:
            raise ValueError(f"{template_path} has no {placeholder} placeholder to fill")

    libs = []
    for path in VENDOR:
        if not os.path.exists(path):
            raise ValueError(f"vendored library missing: {path}")
        with open(path, encoding="utf-8") as fh:
            libs.append(fh.read())
    html = html.replace("/*__VENDOR__*/", "\n;\n".join(libs))
    # `</script>` inside the JSON would end the tag early; escaping the slash is
    # the standard way and leaves the value identical after JSON.parse.
    payload = json.dumps(b, ensure_ascii=False).replace("</", "<\\/")
    return html.replace("__BUNDLE__", payload)
