"""Apply an op: the only way anything in the spec changes.

Three refusals, in this order, because each one answers a different question:

  1. is this field writable at all      -> owner must be 'ontology'
  2. may this actor land it             -> the op's class decides
  3. why is it being changed            -> intent is required, and must cite
                                            a raw or a hook, not free text

A write that passes all three appends an edit record next to the spec. That
record is the history: it travels with the spec into git, so there is no second
place where "what changed and why" could disagree with the graph.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import yaml

from .spec import Spec


class Refused(Exception):
    """The write did not happen, and the message says which gate stopped it."""


@dataclass
class Edit:
    at: str
    by: str
    op: str
    target: str
    changes: list[dict]
    intent: str
    refs: list[str]

    def as_dict(self) -> dict:
        return {
            "at": self.at,
            "by": self.by,
            "op": self.op,
            "target": self.target,
            "changes": self.changes,
            "intent": self.intent,
            "refs": self.refs,
        }


#: Who may land a write, per reversibility tier.
LANDS = {
    "DerivedOp": "agent",       # reversible: recomputing restores it
    "RecordableOp": "human",    # irreversible, but the figures are infra-derived
    "BlockedOp": "nobody",      # not a legal write given today's materials
}


def apply_op(
    s: Spec,
    op_name: str,
    target_type: str,
    target_id: str,
    values: dict[str, Any],
    *,
    intent: str,
    refs: list[str],
    by: str,
    actor: str = "agent",
) -> Edit:
    op = s.ops.get(op_name)
    if op is None:
        raise Refused(f"no such op: {op_name!r}")

    # Gate 3 first, because it costs nothing and its absence is the most common
    # mistake: an agent that changes something without saying why.
    if not intent or not intent.strip():
        raise Refused(f"op {op_name}: intent is required — every write says why")
    known = set(s.raw) | set(s.hooks)
    unknown = [r for r in refs if r not in known]
    if not refs or unknown:
        raise Refused(
            f"op {op_name}: intent must cite an existing raw or hook, "
            f"got {refs!r}" + (f" (unknown: {unknown})" if unknown else " (none)")
        )

    # Gate 2: reversibility tier decides who may land it.
    tier = LANDS.get(op.get("class"), "nobody")
    if tier == "nobody":
        raise Refused(
            f"op {op_name} is a {op.get('class')}: it does not constitute a legal write "
            f"with today's materials — resolve the gap first"
        )
    if tier == "human" and actor != "human":
        raise Refused(
            f"op {op_name} is a {op.get('class')}: an agent may propose it, "
            f"but a human has to land it"
        )

    rows = s.instances.get(target_type) or []
    idp = s.types[target_type]["id"]
    row = next((r for r in rows if r.get(idp) == target_id), None)
    if row is None:
        raise Refused(f"no {target_type} with {idp} = {target_id!r}")

    declared = set(op.get("writes") or [])
    changes: list[dict] = []
    for prop, new in values.items():
        # Gate 1: the owner rule, enforced at write time and not only at load.
        if s.owner_of(target_type, prop) != "ontology":
            raise Refused(
                f"op {op_name} cannot write {prop!r}: its owner is 'source' — "
                f"upstream facts are written by connectors"
            )
        if prop not in declared:
            raise Refused(f"op {op_name} does not declare {prop!r} in its 'writes'")
        p = s.types[target_type]["props"][prop]
        if p.get("type") == "enum" and new not in p["values"]:
            raise Refused(f"{prop} = {new!r} is not in {p['values']}")
        old = row.get(prop)
        if old != new:
            changes.append({"prop": prop, "from": old, "to": new})
            row[prop] = new

    if not changes:
        raise Refused(f"op {op_name} would change nothing — not recording an empty edit")

    return Edit(
        at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        by=by,
        op=op_name,
        target=f"{target_type}/{target_id}",
        changes=changes,
        intent=intent.strip(),
        refs=refs,
    )


def append_edit(path: str, edit: Edit) -> None:
    """Append to the edit log beside the spec, so git carries both together."""
    existing: list[dict] = []
    if os.path.exists(path):
        with io.open(path, encoding="utf-8") as fh:
            existing = yaml.safe_load(fh) or []
    existing.append(edit.as_dict())
    with io.open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(existing, fh, allow_unicode=True, sort_keys=False, width=100)
