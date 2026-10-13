"""Checked phase-two definitions over a pinned, unchanged phase-one snapshot.

This first overlay records meanings and questions, not executable metrics. The
source reader remains the evidence; an origin is never business approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import unicodedata
from pathlib import Path
from urllib.parse import quote, urlparse

from . import source_schema
from .spec import read_document

FORMAT = "sudograph-business-overlay/v4"
REGISTRY = "sudograph-business-registry/v1"


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf8")
    ).hexdigest()


def mapping(value, allowed, required, where):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise ValueError(f"{where}: requires {sorted(required)}; allowed keys: {sorted(allowed)}")
    return value


def text(value, where):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: provide non-empty text")
    return value


def source_nodes(model):
    return {
        n["id"]: n
        for src in model["sources"]
        for obj in src["objects"]
        for n in [obj, *obj["fields"]]
    }


def compile_document(doc, model, *, _history=False):
    mapping(
        doc,
        {"format", "namespace", "baseline", "documents", "definitions", "views", "translations"},
        {"format", "namespace", "baseline", "definitions", "views"},
        "business overlay",
    )
    legacy = _history and doc["format"] == "sudograph-business-overlay/v3"
    if doc["format"] != FORMAT and not legacy:
        raise ValueError(f"business overlay: use format: {FORMAT}")
    namespace = text(doc["namespace"], "namespace")
    mapping(doc["baseline"], {"manifest", "sha256"}, {"manifest", "sha256"}, "baseline pin")
    source_schema.validate(model)
    nodes = source_nodes(model)
    documents = doc.get("documents", {})
    if not isinstance(documents, dict):
        raise ValueError("documents: use a mapping of supplied evidence")
    for key, document in documents.items():
        mapping(document, {"uri", "text", "sha256"}, {"uri", "text", "sha256"}, f"document {key}")
        if urlparse(text(document["uri"], f"document {key}.uri")).scheme != "https":
            raise ValueError(f"document {key}: cite an HTTPS source")
        raw = text(document["text"], f"document {key}.text")
        if hashlib.sha256(raw.encode("utf8")).hexdigest() != document["sha256"]:
            raise ValueError(f"document {key}: evidence text differs from its SHA-256")
    definitions, keys, seen = {}, {}, set()
    if not isinstance(doc["definitions"], dict) or not doc["definitions"]:
        raise ValueError("definitions: declare at least one canonical definition")
    for key, item in doc["definitions"].items():
        where = f"definition {key}"
        required = {
            "concept", "category", "label", "statement", "origin",
            "contributor", "targets", "version",
        }
        if not legacy:
            required.add("role")
        mapping(
            item, required | {"evidence", "applies_to", "grain", "scope"}
            | (set() if legacy else {"purpose"}),
            required, where,
        )
        role = "business" if legacy else item["role"]
        if role not in {"business", "source_evidence", "implementation_note"}:
            raise ValueError(
                f"{where}.role: use business, source_evidence or implementation_note; "
                "source SQL observations and arithmetic notes belong in evidence details"
            )
        if not isinstance(item["category"], str) or item["category"] not in {
            "meaning", "metric", "rule", "issue",
        }:
            raise ValueError(f"{where}.category: use meaning, metric, rule or issue")
        for name in ("concept", "label", "statement"):
            text(item[name], f"{where}.{name}")
        if item["origin"] not in ("provided", "inferred"):
            raise ValueError(
                f"{where}.origin: use provided with evidence, or inferred for model deduction"
            )
        contributors = ("source", "business_user") if item["origin"] == "provided" else ("model",)
        if item["contributor"] not in contributors:
            raise ValueError(
                f"{where}.contributor: {item['origin']} requires one of {contributors}; "
                "keep source material, business-user input and model deduction distinct"
            )
        if role == "source_evidence" and (
            item["origin"] != "provided" or item["contributor"] != "source"
            or item["category"] != "meaning"
        ):
            raise ValueError(f"{where}: source_evidence requires a provided source observation")
        if not legacy and role == "business" and item["category"] in {"meaning", "metric"}:
            purpose = mapping(
                item.get("purpose"), {"stakeholder", "decision"},
                {"stakeholder", "decision"}, f"{where}.purpose",
            )
            for name in ("stakeholder", "decision"):
                text(purpose[name], f"{where}.purpose.{name}")
        elif "purpose" in item:
            raise ValueError(
                f"{where}: purpose belongs to business meanings/metrics; "
                "attach rules, questions and supporting notes through applies_to"
            )
        if role != "business" and item["category"] == "metric":
            raise ValueError(f"{where}: a metric must have a business purpose")
        if type(item["version"]) is not int or item["version"] < 1:
            raise ValueError(
                f"{where}.version: use a positive integer and increment it when edited"
            )
        targets = item["targets"]
        if (
            not isinstance(targets, list)
            or not targets
            or any(not isinstance(v, str) for v in targets)
        ):
            raise ValueError(f"{where}.targets: reference source object/field IDs")
        if len(set(targets)) != len(targets) or set(targets) - nodes.keys():
            raise ValueError(
                f"{where}.targets: unknown or duplicate source ID; discover source_schema IDs"
            )
        if item["category"] == "metric":
            grain = item.get("grain")
            if (
                not isinstance(grain, list) or not grain
                or any(not isinstance(v, str) for v in grain)
                or len(set(grain)) != len(grain)
                or any(v not in targets or nodes[v].get("kind") != "schema_field" for v in grain)
            ):
                raise ValueError(
                    f"{where}.grain: metric definitions require source-field IDs in targets"
                )
            text(item.get("scope"), f"{where}.scope")
        elif "grain" in item or "scope" in item:
            raise ValueError(f"{where}: grain and scope belong to metric definitions")
        concept = unicodedata.normalize("NFKC", item["concept"]).strip().casefold()
        signature = digest([namespace, concept, sorted(targets)])
        identity = "sg-business/" + quote(namespace, safe="") + "/" + signature
        if signature in seen:
            raise ValueError(
                f"{where}: duplicate concept and targets; reuse its definition in views"
            )
        seen.add(signature)
        evidence = item.get("evidence", [])
        if not isinstance(evidence, list) or (item["origin"] == "provided" and not evidence):
            raise ValueError(
                f"{where}.evidence: provided claims need a supplied document or source SQL quote"
            )
        if item["contributor"] == "business_user" and not any(
            isinstance(e, dict) and e.get("kind") == "document" for e in evidence
        ):
            raise ValueError(f"{where}: business-user input requires a supplied document quote")
        for citation in evidence:
            mapping(
                citation, {"kind", "ref", "quote"}, {"kind", "ref", "quote"}, f"{where}.evidence"
            )
            excerpt = text(citation["quote"], f"{where}.evidence.quote")
            if citation["kind"] == "source_sql":
                obj = nodes.get(citation["ref"], {})
                original = obj.get("definition")
            elif citation["kind"] == "document":
                original = documents.get(citation["ref"], {}).get("text")
            else:
                raise ValueError(f"{where}.evidence: use source_sql or document")
            if not original or excerpt not in original:
                raise ValueError(
                    f"{where}.evidence: quote is absent from its cited source; "
                    "inspect the actual evidence"
                )
        definitions[identity] = {
            "id": identity,
            "key": key,
            "kind": "business_definition",
            **item,
            "review_status": "unreviewed",
        }
        keys[key] = identity
    for definition in definitions.values():
        refs = definition.get("applies_to", [])
        if (
            not isinstance(refs, list)
            or any(not isinstance(v, str) for v in refs)
            or len(set(refs)) != len(refs) or set(refs) - keys.keys()
            or definition["key"] in refs
        ):
            raise ValueError(
                f"definition {definition['key']}.applies_to: reference other canonical definitions"
            )
        if (definition["category"] == "rule" or (
            not legacy and definition["role"] == "business" and definition["category"] == "issue"
        )) and (
            not refs or any(
                (not legacy and definitions[keys[k]]["role"] != "business")
                or definitions[keys[k]]["category"] not in {"meaning", "metric"} for k in refs
            )
        ):
            raise ValueError(
                f"definition {definition['key']}: a rule or question must apply to a "
                "named business "
                "meaning or metric; source fields alone do not establish its business purpose"
            )
        if not legacy and definition["role"] != "business" and not refs:
            raise ValueError(
                f"definition {definition['key']}: attach supporting evidence/notes through "
                "applies_to; do not place them in the business view"
            )
        if not legacy and definition["role"] == "business" and any(
            definitions[keys[k]]["role"] != "business" for k in refs
        ):
            raise ValueError(
                f"definition {definition['key']}: business dependencies must reference business "
                "subjects; attach evidence/notes to the subject in their own applies_to"
            )
        definition["applies_to"] = [keys[k] for k in refs]
    visiting, visited = set(), set()

    def dependencies(identity):
        if identity in visiting:
            raise ValueError("business dependencies contain a cycle; make their purpose explicit")
        if identity in visited:
            return
        visiting.add(identity)
        for target in definitions[identity]["applies_to"]:
            dependencies(target)
        visiting.remove(identity)
        visited.add(identity)

    for identity in definitions:
        dependencies(identity)
    dependents = {identity: [] for identity in definitions}
    for identity, definition in definitions.items():
        for target in definition["applies_to"]:
            dependents[target].append(identity)
    views = {}
    if not isinstance(doc["views"], dict) or not doc["views"]:
        raise ValueError("views: declare at least one business view using definition references")
    used = set()
    for key, item in doc["views"].items():
        mapping(item, {"label", "definitions"}, {"label", "definitions"}, f"view {key}")
        text(item["label"], f"view {key}.label")
        refs = item["definitions"]
        if not isinstance(refs, list) or not refs or any(not isinstance(v, str) for v in refs):
            raise ValueError(f"view {key}: use a non-empty list of canonical definition keys")
        if len(set(refs)) != len(refs) or set(refs) - keys.keys():
            raise ValueError(
                f"view {key}: duplicate or unknown definition; reference an existing key"
            )
        ids = [keys[k] for k in refs]
        if not legacy and any(definitions[i]["role"] != "business" for i in ids):
            raise ValueError(
                f"view {key}: source_evidence and implementation_note belong in details; "
                "reference business definitions with a stakeholder and decision purpose"
            )
        # A view reuses dependencies by identity. A rule cannot be shown with its
        # business purpose silently omitted, and no extra definition is copied.
        for identity in ids:
            ids.extend(v for v in definitions[identity]["applies_to"] if v not in ids)
        used.update(ids)
        # Supporting evidence is attached by reference, outside the business
        # canvas. Include nested notes without copying or changing identities.
        attached, supporting_ids = list(ids), set()
        for identity in attached:
            for dependent in dependents[identity]:
                if (
                    not legacy and definitions[dependent]["role"] != "business"
                    and dependent not in supporting_ids
                ):
                    supporting_ids.add(dependent)
                    attached.append(dependent)
        supporting = [identity for identity in definitions if identity in supporting_ids]
        used.update(supporting)
        targets = sorted(
            {target for identity in ids for target in definitions[identity]["targets"]}
        )
        edges = [
            {
                "id": "sg-relation/" + digest([identity, target, "business_evidence"]),
                "from": target,
                "to": identity,
                "rel": "business_evidence",
                "origin": definitions[identity]["origin"],
                "contributor": definitions[identity]["contributor"],
                "review_status": definitions[identity]["review_status"],
            }
            for identity in ids
            for target in definitions[identity]["targets"]
        ]
        edges.extend(
            {
                "id": "sg-relation/" + digest([identity, target, "business_applies_to"]),
                "from": identity,
                "to": target,
                "rel": "business_applies_to",
                "origin": definitions[identity]["origin"],
                "contributor": definitions[identity]["contributor"],
                "review_status": definitions[identity]["review_status"],
            }
            for identity in ids for target in definitions[identity]["applies_to"]
        )
        views[key] = {
            "label": item["label"],
            "definitions": ids,
            "supporting": supporting,
            "targets": targets,
            "edges": edges,
        }
    if used != set(definitions):
        raise ValueError(
            "definitions: unreferenced definitions; use a business view or attach "
            "supporting evidence to a visible business subject"
        )
    translations = doc.get("translations", {})
    if not isinstance(translations, dict) or set(translations) - {"en", "zh"}:
        raise ValueError("translations: use the supported en/zh catalogues")
    vocabulary = {item[name] for item in definitions.values() for name in ("label", "statement")}
    vocabulary.update(item["scope"] for item in definitions.values() if "scope" in item)
    vocabulary.update(
        value for item in definitions.values() for value in item.get("purpose", {}).values()
    )
    vocabulary.update(v["label"] for v in views.values())
    for language, terms in translations.items():
        if (
            not isinstance(terms, dict)
            or set(terms) - vocabulary
            or any(not isinstance(v, str) for v in terms.values())
        ):
            raise ValueError(
                f"translations.{language}: translate overlay text only, "
                "without changing source labels"
            )
    return {
        "format": doc["format"],
        "document": doc,
        "definitions": definitions,
        "views": views,
        "source_digest": digest(model),
    }


def build(doc, baseline):
    if (
        baseline.get("projection", {}).get("mode") != "source_projection"
        or not baseline["projection"].get("source_read_only")
        or baseline.get("business")
    ):
        raise ValueError("business overlay requires a separate read-only phase-one baseline")
    business = compile_document(doc, baseline["source_schema"])
    translations = {lang: dict(terms) for lang, terms in baseline.get("translations", {}).items()}
    for language, terms in doc.get("translations", {}).items():
        existing = translations.setdefault(language, {})
        if any(k in existing and existing[k] != v for k, v in terms.items()):
            raise ValueError("overlay translations must not change existing source labels")
        existing.update(terms)
    return {
        **baseline,
        "projection": {**baseline["projection"], "mode": "business"},
        "translations": translations,
        "business": business,
    }


def validate(model):
    business = model["business"]
    if model["projection"]["mode"] != "business":
        raise ValueError("business definitions cannot be added to a phase-one export")
    expected = compile_document(business["document"], model["source_schema"])
    if business != expected:
        raise ValueError(
            "business identities, evidence or view references changed; "
            "rebuild through compiler.business"
        )


def registry(model, previous):
    definitions = model["business"]["definitions"]
    if previous and previous.get("format") != REGISTRY:
        raise ValueError("unsupported business identity registry")
    entries = dict(previous.get("definitions", {}))
    for identity, item in definitions.items():
        content = digest({k: v for k, v in item.items() if k not in {"key", "version"}})
        old = entries.get(identity)
        if old and (
            item["version"] < old["version"]
            or (item["version"] == old["version"] and content != old["content_digest"])
        ):
            raise ValueError(
                f"definition {item['key']}: content changed without a new version; "
                "keep the ID and increment version"
            )
        entries[identity] = {"version": item["version"], "content_digest": content}
    return {"format": REGISTRY, "definitions": entries}


def load(path):
    # The baseline checker is the established file/contract authority; reuse it
    # instead of introducing a second implementation of frozen snapshot checks.
    from tools.check_baselines import bundle, check  # noqa: PLC0415
    from tools.check_baselines import digest as file_digest  # noqa: PLC0415

    path = Path(path)
    doc = read_document(str(path))
    mapping(
        doc,
        {"format", "namespace", "baseline", "documents", "definitions", "views", "translations"},
        {"format", "namespace", "baseline", "definitions", "views"},
        "business overlay",
    )
    pin = mapping(doc["baseline"], {"manifest", "sha256"}, {"manifest", "sha256"}, "baseline pin")
    manifest = (path.resolve().parent / pin["manifest"]).resolve()
    if file_digest(manifest) != pin["sha256"]:
        raise ValueError(
            "baseline manifest differs from the supplied pin; review the new source baseline first"
        )
    check(manifest)
    data = json.loads(manifest.read_text(encoding="utf8"))
    return build(doc, bundle(manifest.parent / data["artifact"]))


def write(path, data):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.resolve().parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None):
    from . import app  # noqa: PLC0415 — renderer validates through this module

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--app", help="write the shared graph HTML")
    target.add_argument(
        "--check-app", help="verify a saved export against the pinned source and definitions"
    )
    parser.add_argument("--lang", choices=app.languages(), default="zh")
    parser.add_argument("--pack-html", action="store_true")
    parser.add_argument(
        "--registry",
        help="operator's canonical identity/version registry; defaults beside the overlay",
    )
    args = parser.parse_args(argv)
    if args.pack_html and not args.app:
        parser.error("--pack-html requires --app")
    try:
        model = load(args.spec)
        path = Path(args.registry or str(Path(args.spec).with_suffix(".registry.json")))
        previous = json.loads(path.read_text(encoding="utf8")) if path.exists() else {}
        checked = registry(model, previous)
        if args.check_app:
            from .html_export import model as read_model  # noqa: PLC0415

            saved = read_model(args.check_app)
            validate(saved)
            if {k: v for k, v in saved.items() if k != "ui"} != {
                k: v for k, v in model.items() if k != "ui"
            }:
                raise ValueError(
                    "saved export differs from the pinned source or definitions; regenerate"
                )
            if saved.get("ui", {}).get("language") != args.lang:
                raise ValueError("saved export language differs from --lang")
            app.check_export(args.check_app, model, language=args.lang)
        if args.app:
            rendered = app.render(model, language=args.lang, packed=args.pack_html)
            write(args.app, rendered.encode("utf8"))
            write(path, (json.dumps(checked, indent=2) + "\n").encode("utf8"))
        print(
            json.dumps(
                {
                    "format": FORMAT,
                    "definitions": len(model["business"]["definitions"]),
                    "views": list(model["business"]["views"]),
                    "review_status": "unreviewed",
                }
            )
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Business overlay refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
