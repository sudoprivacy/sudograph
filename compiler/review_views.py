"""Derive review selections from checked definitions, without a model or prompts.

Source identities and business meanings remain inputs. This selects declared
subjects and dependencies; it never guesses a business relationship from prose.
"""

from __future__ import annotations

ALGORITHM = "sudograph-review-selection/v1"
MAX_DEFINITIONS = 200


def defaults(definitions):
    """Return stable subject and unresolved-question seeds in canonical order."""
    ordered = sorted(definitions.items())
    subjects = {i: n for i, n in ordered
                if n["role"] == "business" and n["category"] in {"meaning", "metric"}}
    attached_by_subject = {identity: [] for identity in subjects}
    for _, node in ordered:
        if node["role"] == "business" and node["category"] in {"rule", "issue"}:
            for target in node["applies_to"]:
                attached_by_subject[target].append(node)
    views = {}
    for identity, subject in subjects.items():
        attached = attached_by_subject[identity]
        questions = [n for n in attached if n["category"] == "issue"
                     and n["review_status"] == "unreviewed"]
        suffix = identity.rsplit("/", 1)[-1]
        for kind, nodes in [("subject", [subject, *attached]), ("questions", questions)]:
            if not nodes:
                continue
            views[kind + "-" + suffix] = {
                "label": subject["label"],
                "definitions": [n["key"] for n in nodes],
                "selection_kind": kind,
                "subject": identity,
            }
    return views
