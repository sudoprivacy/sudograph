"""Shared checked YAML entrance for ordinary edits and optional GitLab delivery."""

from __future__ import annotations

import tempfile
from pathlib import Path

from . import business, source_schema
from .spec import read_document

SOURCE_REQUEST = "sudograph-source-request/v1"
MODEL_FILE = "model.yaml"


class Refused(ValueError):
    def __init__(self, code, reason, recovery, status=400):
        super().__init__(reason)
        self.code, self.reason, self.recovery, self.status = code, reason, recovery, status


def parse_document(content):
    if not isinstance(content, str) or len(content.encode("utf8")) > 2 * 1024 * 1024:
        raise Refused(
            "MODEL_REQUIRED",
            "model must be UTF-8 YAML within 2 MiB",
            "Submit checked model inputs, never generated HTML",
        )
    with tempfile.TemporaryDirectory(prefix="sudograph-model-") as folder:
        path = Path(folder) / MODEL_FILE
        path.write_text(content, encoding="utf8")
        return read_document(str(path))


def compile_model(content, baseline, previous=None, *, namespace=None, _history=False):
    source_schema.validate(baseline["source_schema"])
    if (
        baseline.get("projection", {}).get("mode") != "source_projection"
        or not baseline["projection"].get("source_read_only")
        or baseline.get("business")
    ):
        raise ValueError("operator must register a complete read-only phase-one baseline")
    doc = parse_document(content)
    pin = {"manifest": "registered-source-baseline", "sha256": business.digest(baseline)}
    if not isinstance(doc, dict) or doc.get("baseline") != pin:
        raise Refused(
            "SOURCE_PIN",
            "model does not reference the registered source baseline",
            "Use the baseline pin returned by contract; authors cannot choose source paths",
        )
    if doc.get("format") == SOURCE_REQUEST:
        if set(doc) != {"format", "baseline"}:
            raise Refused(
                "SOURCE_FACTS_ONLY",
                "phase one accepts only the registered source request",
                "Put authored business definitions in a phase-two overlay",
            )
        model, registry = baseline, previous or {}
    else:
        if namespace is not None and doc.get("namespace") != namespace:
            raise Refused(
                "IDENTITY_NAMESPACE",
                "model changed its registered identity namespace",
                "Reuse the namespace returned by contract; views do not allocate identities",
            )
        if _history and doc.get("format") == "sudograph-business-overlay/v3":
            # Only the operator-anchored target history uses this decoder. New
            # submissions, CI, release checks and HTML rendering remain strict.
            decoded = business.compile_document(doc, baseline["source_schema"], _history=True)
            model = {"business": decoded}
        else:
            model = business.build(doc, baseline, previous=previous)
        registry = business.registry(model, previous or {})
    return model, registry
