"""Machine-readable authoring format, sharing compiler field names and enums.

Structural guidance does not replace semantic compilation, provenance checks,
identity reservations, version checks or source authorization.
"""

from . import business


def object_schema(properties, required):
    return {
        "type": "object",
        "properties": properties,
        "required": sorted(required),
        "additionalProperties": False,
    }


def document_schema(namespace, baseline):
    text = {"type": "string", "minLength": 1, "pattern": r"\S"}
    refs = {"type": "array", "items": text, "uniqueItems": True}
    citation = object_schema(
        {
            "kind": {"enum": ["document", "source_sql"]},
            "ref": text,
            "quote": text,
        },
        {"kind", "ref", "quote"},
    )
    fields = {
        "concept": {**text, "description": "Stable concept key; reuse it on later edits."},
        "role": {"enum": sorted(business.ROLES)},
        "category": {"enum": sorted(business.CATEGORIES)},
        "label": text,
        "statement": text,
        "origin": {"enum": sorted(business.ORIGINS)},
        "contributor": {"enum": sorted({v for vs in business.CONTRIBUTORS.values() for v in vs})},
        "targets": {
            **refs,
            "description": (
                "Exact source object/field IDs from the context catalogue. "
                "[] is permitted for unbound business concepts."
            ),
        },
        "version": {"type": "integer", "minimum": 1},
        "purpose": object_schema(
            {"stakeholder": text, "decision": text}, {"stakeholder", "decision"}
        ),
        "verification": text,
        "evidence": {"type": "array", "items": citation},
        "applies_to": {
            **refs,
            "description": (
                "Other author keys in this document's definitions mapping, never source IDs."
            ),
        },
        "grain": {
            **refs,
            "description": ("Source-field IDs also present in targets; required for metrics."),
        },
        "scope": text,
    }
    assert set(fields) == business.DEFINITION_REQUIRED | business.DEFINITION_OPTIONAL | {"role"}
    definition = object_schema(fields, business.DEFINITION_REQUIRED | {"role"})
    conditions = []

    def when(condition, then, otherwise=None):
        conditions.append(
            {
                "if": condition,
                "then": then,
                **({"else": otherwise} if otherwise is not None else {}),
            }
        )

    def match(**values):
        return {
            "properties": {key: {"const": value} for key, value in values.items()},
            "required": sorted(values),
        }

    when(
        {
            "allOf": [
                match(role="business"),
                {
                    "properties": {"category": {"enum": ["meaning", "metric"]}},
                    "required": ["category"],
                },
            ]
        },
        {"required": ["purpose"]},
        {"not": {"required": ["purpose"]}},
    )
    when(
        match(role="source_review"),
        {
            "properties": {"category": {"const": "issue"}, "applies_to": {"maxItems": 0}},
            "required": ["verification"],
        },
        {"not": {"required": ["verification"]}},
    )
    when(
        match(category="metric"),
        {"properties": {"role": {"const": "business"}}, "required": ["grain", "scope"]},
        {"not": {"anyOf": [{"required": ["grain"]}, {"required": ["scope"]}]}},
    )
    when({"not": match(role="business")}, {"properties": {"targets": {"minItems": 1}}})
    when(
        match(origin="provided"),
        {
            "properties": {
                "contributor": {"enum": list(business.CONTRIBUTORS["provided"])},
                "evidence": {"minItems": 1},
            },
            "required": ["evidence"],
        },
        {"properties": {"contributor": {"enum": list(business.CONTRIBUTORS["inferred"])}}},
    )
    when(
        match(contributor="business_user"),
        {
            "properties": {
                "evidence": {
                    "contains": {
                        "properties": {"kind": {"const": "document"}},
                        "required": ["kind"],
                    }
                }
            },
            "required": ["evidence"],
        },
    )
    when(
        match(role="source_evidence"),
        {
            "properties": {
                "origin": {"const": "provided"},
                "contributor": {"const": "source"},
                "category": {"const": "meaning"},
            }
        },
    )
    when(
        {
            "anyOf": [
                match(category="rule"),
                match(role="business", category="issue"),
                match(role="source_evidence"),
                match(role="implementation_note"),
            ]
        },
        {"properties": {"applies_to": {"minItems": 1}}, "required": ["applies_to"]},
    )
    when(
        {
            "allOf": [
                match(category="metric"),
                {"properties": {"targets": {"minItems": 1}}, "required": ["targets"]},
            ]
        },
        {"properties": {"grain": {"minItems": 1}}},
    )
    definition["allOf"] = conditions
    properties = {
        "format": {"const": business.FORMAT},
        "namespace": {"const": namespace},
        "baseline": {"const": baseline},
        "definitions": {"type": "object", "minProperties": 1, "additionalProperties": definition},
        "documents": {
            "type": "object",
            "additionalProperties": object_schema(
                {
                    "uri": {"type": "string", "pattern": "^https://"},
                    "text": text,
                    "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                },
                {"uri", "text", "sha256"},
            ),
        },
        "views": {
            "type": "object",
            "additionalProperties": object_schema(
                {
                    "label": text,
                    "definitions": {**refs, "minItems": 1},
                },
                {"label", "definitions"},
            ),
        },
        "translations": {"type": "object"},
    }
    assert set(properties) == business.OVERLAY_REQUIRED | business.OVERLAY_OPTIONAL
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **object_schema(properties, business.OVERLAY_REQUIRED),
        "description": (
            "YAML document structure. Compiler-owned IDs and review_status are not author fields. "
            "New definitions compile as unreviewed; source attribution is not approval. "
            "Evidence hashes/quotes, references, semantic roles, identity and version rules "
            "are checked by the compiler. "
            "Optional views default to algorithmic business selections."
        ),
        "examples": [
            {
                "format": business.FORMAT,
                "namespace": namespace,
                "baseline": baseline,
                "definitions": {
                    "proposed_concept": {
                        "concept": "example proposed concept",
                        "role": "business",
                        "category": "meaning",
                        "label": "Example proposed concept",
                        "statement": (
                            "An illustrative model proposal, not a source fact or approved policy."
                        ),
                        "origin": "inferred",
                        "contributor": "model",
                        "version": 1,
                        "targets": [],
                        "purpose": {
                            "stakeholder": "Business reviewer",
                            "decision": "Clarify the proposed concept",
                        },
                    }
                },
            }
        ],
    }
