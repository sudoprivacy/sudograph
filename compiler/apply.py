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

import os
from dataclasses import dataclass
from datetime import UTC, datetime
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
    #: "landed" once the change is in the rows; "proposed" while it waits on a
    #: person. A proposal is validated exactly as strictly as a landing, so
    #: proposing can never record something that could not be applied.
    status: str = "landed"
    decided_by: str | None = None
    decided_at: str | None = None

    def as_dict(self) -> dict:
        d = {
            "at": self.at,
            "by": self.by,
            "op": self.op,
            "target": self.target,
            "changes": self.changes,
            "intent": self.intent,
            "refs": self.refs,
            "status": self.status,
        }
        if self.decided_by:
            d["decided_by"] = self.decided_by
            d["decided_at"] = self.decided_at
        return d


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
    proposal = tier == "human" and actor != "human"

    rows = s.instances.get(target_type) or []
    idp = s.types[target_type]["id"]
    row = next((r for r in rows if r.get(idp) == target_id), None)
    if row is None:
        raise Refused(f"no {target_type} with {idp} = {target_id!r}")

    declared = set(op.get("writes") or [])
    changes: list[dict] = []
    for prop, new in values.items():
        # Validate against the row without touching it yet: a proposal must be
        # checked as strictly as a landing, or "propose" becomes a way to record
        # something that could never be applied.
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

    if not changes:
        raise Refused(f"op {op_name} would change nothing — not recording an empty edit")

    if not proposal:
        for ch in changes:
            row[ch["prop"]] = ch["to"]

    return Edit(
        status="proposed" if proposal else "landed",
        at=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        by=by,
        op=op_name,
        target=f"{target_type}/{target_id}",
        changes=changes,
        intent=intent.strip(),
        refs=refs,
    )


def append_edit(path: str, edit: Edit) -> None:
    """Write the edit to the log beside the spec, so git carries both together.

    A proposal that later lands replaces its own entry rather than adding a
    second one. Two records of one decision would read, to an auditor, as two
    decisions — and the approval already carries who decided and when, so
    nothing is lost by collapsing them.
    """
    existing: list[dict] = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            existing = yaml.safe_load(fh) or []
    d = edit.as_dict()
    for i, prior in enumerate(existing):
        same_proposal = (
            prior.get("status") == "proposed"
            and prior.get("target") == d["target"]
            and prior.get("op") == d["op"]
            and prior.get("at") == d["at"]
        )
        if same_proposal:
            existing[i] = d
            break
    else:
        existing.append(d)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(existing, fh, allow_unicode=True, sort_keys=False, width=100)


def approve(
    s: Spec,
    edit: Edit,
    *,
    by: str,
    note: str = "",
) -> Edit:
    """A person lands a proposal.

    The other half of "an agent may propose it, but a human has to land it". A
    refusal with nowhere to go is not a gate, it is a dead end — this is where
    the proposal becomes a change.

    Re-resolves the row and re-applies the recorded changes, so a proposal that
    has gone stale (someone else moved the value meanwhile) is caught rather
    than silently overwriting.
    """
    if edit.status != "proposed":
        raise Refused(f"edit for {edit.target} is {edit.status}, not awaiting a decision")

    target_type, target_id = edit.target.split("/", 1)
    rows = s.instances.get(target_type) or []
    idp = s.types[target_type]["id"]
    row = next((r for r in rows if r.get(idp) == target_id), None)
    if row is None:
        raise Refused(f"{edit.target} no longer exists")

    for ch in edit.changes:
        current = row.get(ch["prop"])
        if current != ch["from"]:
            raise Refused(
                f"{edit.target}.{ch['prop']} is now {current!r}, not {ch['from']!r} — "
                f"the proposal is stale; re-propose against the current value"
            )
    for ch in edit.changes:
        row[ch["prop"]] = ch["to"]

    edit.status = "landed"
    edit.decided_by = by
    edit.decided_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    if note:
        edit.intent = f"{edit.intent} | approved: {note}"
    return edit
