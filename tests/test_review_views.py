"""Default navigation must not require authored view lists or model access."""

import copy

import pytest
import test_business

from compiler import business, review_views


@pytest.fixture
def base(tmp_path):
    return test_business.base.__wrapped__(tmp_path)


def test_view_free_compilation_is_stable_under_author_order_and_key_changes(base):
    model, doc = base
    doc.pop("views")
    first = business.build(doc, model)
    selected = first["business"]["views"]
    assert len(selected) == 2
    assert all(v["selection_kind"] == "subject" for v in selected.values())
    doc["definitions"] = dict(reversed(list(doc["definitions"].items())))
    second = business.build(doc, model)
    assert selected == second["business"]["views"]
    assert first["business"]["navigation"] == second["business"]["navigation"]
    business.validate(second)
    doc["definitions"]["new-local-key"] = doc["definitions"].pop("observed-total")
    assert selected == business.build(doc, model)["business"]["views"]
    assert first["source_schema"] is model["source_schema"]
    assert first["records"] is model["records"]


def test_shared_rules_and_pending_questions_follow_canonical_links(base):
    model, doc = base
    doc.pop("views")
    rule = copy.deepcopy(doc["definitions"]["refund-question"])
    rule.pop("purpose")
    rule.update(concept="price policy", category="rule", applies_to=list(doc["definitions"]))
    doc["definitions"]["price-policy"] = rule
    question = copy.deepcopy(rule)
    question.update(concept="tax question", category="issue", applies_to=["observed-total"])
    doc["definitions"]["tax-question"] = question
    result = business.build(doc, model)["business"]
    views = result["views"]
    subjects = [v for v in views.values() if v["selection_kind"] == "subject"]
    pending = [v for v in views.values() if v["selection_kind"] == "questions"]
    rule_id = next(i for i, n in result["definitions"].items() if n["key"] == "price-policy")
    issue_id = next(i for i, n in result["definitions"].items() if n["key"] == "tax-question")
    assert len(subjects) == 2 and len(pending) == 1
    assert all(rule_id in v["definitions"] for v in subjects)
    assert issue_id in pending[0]["definitions"] and rule_id not in pending[0]["definitions"]
    assert pending[0]["subject"] in pending[0]["definitions"]
    old_keys = list(views)
    del doc["definitions"]["tax-question"]
    updated = business.build(doc, model)["business"]["views"]
    assert list(updated) == [k for k in old_keys if views[k]["selection_kind"] == "subject"]


def test_default_custom_views_do_not_follow_yaml_entry_order(base):
    model, doc = base
    first = business.build(doc, model)["business"]["navigation"]
    doc["views"] = dict(reversed(list(doc["views"].items())))
    assert business.build(doc, model)["business"]["navigation"] == first
    assert first["mode"] == "custom" and first["default"] == "schema"


def test_source_review_needs_no_business_views_or_business_subjects(base):
    model, doc = base
    doc.pop("views")
    doc["definitions"] = {"question": test_business.source_question(model)}
    result = business.build(doc, model)
    assert result["business"]["views"] == {}
    assert result["business"]["navigation"]["default"] == "schema:review"
    assert result["source_schema"] is model["source_schema"]
    business.validate(result)


def test_default_selection_checks_capacity_and_never_invents_review_approval(base, monkeypatch):
    model, doc = base
    doc.pop("views")
    doc["definitions"]["refund-question"]["applies_to"] = ["observed-total"]
    monkeypatch.setattr(review_views, "MAX_DEFINITIONS", 1)
    with pytest.raises(ValueError, match="dependencies cannot be silently omitted"):
        business.build(doc, model)
    monkeypatch.setattr(review_views, "MAX_DEFINITIONS", 200)
    doc["definitions"]["refund-question"]["review_status"] = "confirmed"
    with pytest.raises(ValueError, match="allowed keys"):
        business.build(doc, model)
