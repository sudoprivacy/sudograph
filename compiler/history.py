"""Read the edit log back as per-object timelines.

A raw log is chronological, which is the one order nobody asks for. The question
a reviewer actually has is "what happened to this node", so the log is indexed by
target and handed to the graph app that way: click an object, see its own history.

Nothing here is a second source of truth. The log is part of the spec directory
and travels with it into git; this module only reindexes what is already there.
"""

from __future__ import annotations

import io
import os
from collections import OrderedDict
from typing import Any

import yaml


def log_path(spec_path: str) -> str:
    """The edit log sits beside its spec, so git carries the two together."""
    base, _ = os.path.splitext(spec_path)
    return base + ".edits.yaml"


def read(spec_path: str) -> list[dict]:
    p = log_path(spec_path)
    if not os.path.exists(p):
        return []
    with io.open(p, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or []


def timelines(entries: list[dict]) -> dict[str, list[dict]]:
    """Index edits by the object they touched, newest last.

    Entries keep their original order within a target: the sequence of decisions
    is the point, and sorting by timestamp alone would reorder two edits made in
    the same second.
    """
    out: "OrderedDict[str, list[dict]]" = OrderedDict()
    for e in entries:
        out.setdefault(e.get("target", "?"), []).append(e)
    return dict(out)


def pending(entries: list[dict]) -> list[dict]:
    """Proposals waiting on a person.

    A RecordableOp is proposed by an agent and landed by a human, so the queue of
    things awaiting a decision is a first-class view: without it, "a human has to
    land it" is a refusal with nowhere to go.
    """
    return [e for e in entries if e.get("status") == "proposed"]


def attach(view: dict[str, Any], spec_path: str) -> dict[str, Any]:
    """Fold history into a view model, next to the nodes it explains."""
    entries = read(spec_path)
    by_target = timelines(entries)
    view["history"] = by_target
    view["pending"] = pending(entries)

    # An instance's own timeline hangs off its group, so the graph app does not
    # have to know how targets are spelled.
    for group in view.get("groups", []):
        prefix = group["type"] + "/"
        group["history"] = {
            k.split("/", 1)[1]: v for k, v in by_target.items() if k.startswith(prefix)
        }
    return view


def summarise(entries: list[dict]) -> str:
    if not entries:
        return "no edits recorded"
    targets = len({e.get("target") for e in entries})
    waiting = len(pending(entries))
    tail = f", {waiting} awaiting a person" if waiting else ""
    return f"{len(entries)} edits across {targets} objects{tail}"
