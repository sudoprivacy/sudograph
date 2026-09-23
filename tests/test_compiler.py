"""What these tests are for.

Most of them assert a refusal. That is deliberate: the value of this compiler is
not that it computes a sum — it is that the rules we wrote down are enforced by
code rather than observed by convention. A rule with no test proving it refuses
is a rule that will quietly stop holding.

Every test that asserts a refusal also names the gate it is exercising, so a
failure says which property was lost.
"""

from __future__ import annotations

import copy
import io
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler import apply as apply_mod  # noqa: E402
from compiler import compile as compile_mod  # noqa: E402
from compiler import expr  # noqa: E402
from compiler import spec as spec_mod  # noqa: E402

REAL_FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "examples",
    "weiwai-real.yaml",
)

FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "examples",
    "weiwai-capitalisation.yaml",
)


@pytest.fixture
def s() -> spec_mod.Spec:
    return spec_mod.load(FIXTURE)


def _mutated(**edits) -> spec_mod.Spec:
    """Build a Spec straight from a mutated document, bypassing load()'s check.

    Bypassing is the point: these tests call check() themselves so they can
    assert on the specific problem rather than on "it raised".
    """
    with io.open(FIXTURE, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    doc = copy.deepcopy(doc)
    for path, value in edits.items():
        cursor = doc
        parts = path.split("/")
        for p in parts[:-1]:
            cursor = cursor[int(p)] if isinstance(cursor, list) else cursor[p]
        last = parts[-1]
        if isinstance(cursor, list):
            cursor[int(last)] = value
        else:
            cursor[last] = value
    return spec_mod.Spec(
        name=doc["ontology"],
        types=doc["types"],
        raw=doc.get("raw") or {},
        hooks=doc.get("hooks") or {},
        instances=doc.get("instances") or {},
        nodes=doc.get("nodes") or {},
        ops=doc.get("ops") or {},
    )


# ── the fixture itself ─────────────────────────────────────────────────

def test_fixture_loads_and_every_check_passes(s):
    c = compile_mod.compile_spec(s)
    assert c.passed, [(k.name, k.detail) for k in c.checks if not k.ok]
    assert len(c.checks) >= 8


def test_aggregates_compute_the_expected_figures(s):
    c = compile_mod.compile_spec(s)
    # C-001 + C-002 are the only contracts marked capitalisable.
    assert c.values["委外cap"] == 3_773_585 + 3_396_226
    assert c.values["委外待补金额"] == 4_314_151  # C-003 alone
    assert c.values["委外合同数"] == 5


# ── gate 1: owner ──────────────────────────────────────────────────────

def test_op_may_not_declare_a_source_property_in_writes():
    """Gate: owner. Upstream facts belong to connectors, never to ops."""
    bad = _mutated(**{"ops/标记可资本化/writes": ["供应商"]})
    problems = spec_mod.check(bad)
    assert any("owner is 'source'" in p for p in problems), problems


def test_ontology_property_may_not_claim_an_upstream_source():
    """Gate: owner. A decision made here cannot also be an upstream fact."""
    bad = _mutated(**{"types/委外合同/props/可资本化/from": "R-CONTRACT"})
    problems = spec_mod.check(bad)
    assert any("not upstream" in p for p in problems), problems


def test_source_property_must_name_the_raw_that_supplies_it():
    """Gate: owner. A number with no declared provenance is a number nobody can check."""
    doc_edit = {"type": "string", "owner": "source"}  # no 'from'
    bad = _mutated(**{"types/委外合同/props/供应商": doc_edit})
    problems = spec_mod.check(bad)
    assert any("needs 'from'" in p for p in problems), problems


def test_apply_refuses_to_write_a_source_property(s):
    """Gate: owner, enforced again at write time and not only at load."""
    with pytest.raises(apply_mod.Refused, match="owner is 'source'"):
        apply_mod.apply_op(
            s, "标记可资本化", "委外合同", "C-003", {"供应商": "X"},
            intent="try to rewrite an upstream fact",
            refs=["R-CONTRACT"], by="agent:test",
        )


# ── gate 2: reversibility tier ─────────────────────────────────────────

def test_recordable_op_lets_an_agent_propose_but_not_land(s):
    """An agent has proposal rights, not landing rights. A refusal with nowhere
    to go is a dead end; a proposal is the gate done properly."""
    s.ops["标记可资本化"]["class"] = "RecordableOp"
    before = compile_mod.compile_spec(s).values["委外cap"]

    edit = apply_mod.apply_op(
        s, "标记可资本化", "委外合同", "C-003", {"可资本化": "是"},
        intent="OCR revealed the clause", refs=["R-CONTRACT"],
        by="agent:test", actor="agent",
    )
    assert edit.status == "proposed"
    assert compile_mod.compile_spec(s).values["委外cap"] == before, "a proposal must not move the figures"

    apply_mod.approve(s, edit, by="human:partner", note="checked the scan")
    assert edit.status == "landed"
    assert edit.decided_by == "human:partner"
    assert compile_mod.compile_spec(s).values["委外cap"] > before, "approval lands it"


def test_a_proposal_is_validated_as_strictly_as_a_landing(s):
    """Otherwise 'propose' becomes a way to record something unapplicable."""
    s.ops["标记可资本化"]["class"] = "RecordableOp"
    with pytest.raises(apply_mod.Refused, match="is not in"):
        apply_mod.apply_op(
            s, "标记可资本化", "委外合同", "C-003", {"可资本化": "也许"},
            intent="reason", refs=["R-CONTRACT"], by="agent:test", actor="agent",
        )


def test_a_stale_proposal_is_refused_rather_than_overwriting(s):
    """Between proposal and approval someone else may have moved the value.
    Landing anyway would silently discard their decision."""
    s.ops["标记可资本化"]["class"] = "RecordableOp"
    edit = apply_mod.apply_op(
        s, "标记可资本化", "委外合同", "C-003", {"可资本化": "是"},
        intent="reason", refs=["R-CONTRACT"], by="agent:test", actor="agent",
    )
    row = next(r for r in s.instances["委外合同"] if r["合同编号"] == "C-003")
    row["可资本化"] = "否"  # somebody else decided meanwhile

    with pytest.raises(apply_mod.Refused, match="stale"):
        apply_mod.approve(s, edit, by="human:partner")


def test_an_approved_proposal_replaces_its_own_log_entry(tmp_path, s):
    """Two records of one decision read as two decisions."""
    s.ops["标记可资本化"]["class"] = "RecordableOp"
    log = str(tmp_path / "x.edits.yaml")
    e = apply_mod.apply_op(
        s, "标记可资本化", "委外合同", "C-003", {"可资本化": "是"},
        intent="reason", refs=["R-CONTRACT"], by="agent:test", actor="agent",
    )
    apply_mod.append_edit(log, e)
    apply_mod.approve(s, e, by="human:partner")
    apply_mod.append_edit(log, e)

    entries = yaml.safe_load(io.open(log, encoding="utf-8"))
    assert len(entries) == 1, "the proposal and its approval are one decision"
    assert entries[0]["status"] == "landed"
    assert entries[0]["decided_by"] == "human:partner"


def test_approving_something_already_landed_is_refused(s):
    edit = apply_mod.apply_op(
        s, "标记可资本化", "委外合同", "C-003", {"可资本化": "是"},
        intent="reason", refs=["R-CONTRACT"], by="agent:test",
    )
    assert edit.status == "landed"
    with pytest.raises(apply_mod.Refused, match="not awaiting a decision"):
        apply_mod.approve(s, edit, by="human:partner")


def test_blocked_op_refuses_everyone(s):
    """Gate: class. Some writes are not 'needs approval' — they are not legal yet."""
    s.ops["标记可资本化"]["class"] = "BlockedOp"
    with pytest.raises(apply_mod.Refused, match="does not constitute a legal write"):
        apply_mod.apply_op(
            s, "标记可资本化", "委外合同", "C-003", {"可资本化": "是"},
            intent="reason", refs=["R-CONTRACT"], by="human:me", actor="human",
        )


# ── gate 3: intent ─────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "intent,refs,expected",
    [
        ("", ["R-CONTRACT"], "intent is required"),
        ("looked about right", [], "must cite an existing raw or hook"),
        ("looked about right", ["R-NOPE"], "unknown"),
    ],
    ids=["missing", "uncited", "unknown-reference"],
)
def test_intent_must_exist_and_cite_real_provenance(s, intent, refs, expected):
    """Gate: intent. Machine-checkable provenance beats free text."""
    with pytest.raises(apply_mod.Refused, match=expected):
        apply_mod.apply_op(
            s, "标记可资本化", "委外合同", "C-003", {"可资本化": "是"},
            intent=intent, refs=refs, by="agent:test",
        )


# ── the write-back loop ────────────────────────────────────────────────

def test_landing_an_op_recomputes_the_total_so_detail_and_total_cannot_disagree(s):
    before = compile_mod.compile_spec(s)
    edit = apply_mod.apply_op(
        s, "标记可资本化", "委外合同", "C-003",
        {"IP归属": "归甲方", "可资本化": "是"},
        intent="OCR revealed clause 12: the IP is ours",
        refs=["R-CONTRACT", "H4-委外待补"], by="agent:scode-1",
    )
    after = compile_mod.compile_spec(s)

    moved = after.values["委外cap"] - before.values["委外cap"]
    assert moved == 4_314_151, "the total must move by exactly the contract's amount"
    assert after.values["委外待补金额"] == 0
    assert after.passed

    assert edit.target == "委外合同/C-003"
    assert {c["prop"] for c in edit.changes} == {"IP归属", "可资本化"}
    assert edit.refs == ["R-CONTRACT", "H4-委外待补"]


def test_an_op_that_changes_nothing_records_nothing(s):
    """An empty edit in the history is a lie about what happened."""
    with pytest.raises(apply_mod.Refused, match="would change nothing"):
        apply_mod.apply_op(
            s, "标记可资本化", "委外合同", "C-001", {"可资本化": "是"},
            intent="already true", refs=["R-CONTRACT"], by="agent:test",
        )


def test_enum_values_are_enforced_on_write(s):
    with pytest.raises(apply_mod.Refused, match="is not in"):
        apply_mod.apply_op(
            s, "标记可资本化", "委外合同", "C-003", {"可资本化": "大概吧"},
            intent="reason", refs=["R-CONTRACT"], by="agent:test",
        )


# ── the expression language ────────────────────────────────────────────

def test_expressions_are_parsed_not_evaluated():
    """Anything outside the whitelist is a syntax error, including plain Python."""
    for src in ["__import__('os').system('echo hi')", "open('/etc/passwd')", "a.b.c"]:
        with pytest.raises(expr.ExprError):
            expr.parse(src)


def test_aggregate_without_a_property_to_sum_is_rejected():
    with pytest.raises(expr.ExprError, match="which property"):
        expr.parse("sum(委外合同 where 可资本化 == '是')")


def test_aggregated_types_come_from_the_ast_not_from_substring_matching():
    """Regression: a type whose name is a substring of another drew a phantom edge."""
    node = expr.parse("sum(合同 where x == 1 -> y) + count(委外合同)")
    assert expr.aggregated_types(node) == {"合同", "委外合同"}
    # The substring approach would have matched 合同 inside 委外合同 as well.
    assert "委外合同" not in expr.aggregated_types(expr.parse("sum(合同 -> y)"))


def test_division_by_zero_is_an_error_not_an_exception_from_python():
    with pytest.raises(expr.ExprError, match="division by zero"):
        expr.evaluate(expr.parse("1 / 0"), {}, {})


def test_unknown_name_says_what_it_looked_for():
    with pytest.raises(expr.ExprError, match="unknown name"):
        expr.evaluate(expr.parse("没见过的东西"), {}, {})


# ── the view model ─────────────────────────────────────────────────────

def test_view_model_carries_owner_so_the_graph_app_knows_what_is_editable(s):
    c = compile_mod.compile_spec(s)
    group = next(g for g in c.view["groups"] if g["type"] == "委外合同")
    assert group["owners"]["供应商"] == "source"
    assert group["owners"]["可资本化"] == "ontology"


def test_view_model_folds_a_group_larger_than_the_threshold(s):
    c = compile_mod.compile_spec(s, fold_over=2)
    group = next(g for g in c.view["groups"] if g["type"] == "委外合同")
    assert group["folded"] is True
    assert group["members"] == [], "a folded group ships no members"
    assert group["count"] == 5, "but still reports how many there are"


def test_hook_appears_in_the_view_with_the_node_it_makes_provisional(s):
    c = compile_mod.compile_spec(s)
    hook = next(n for n in c.view["nodes"] if n["id"] == "H4-委外待补")
    assert hook["resolve_when"]
    assert {"from": "H4-委外待补", "to": "委外cap", "rel": "affects"} in c.view["edges"]


# ── checks ─────────────────────────────────────────────────────────────

def test_a_gap_pointing_at_a_missing_hook_fails_the_check():
    bad = _mutated(**{"instances/委外合同/2/缺口": "H-does-not-exist"})
    c = compile_mod.compile_spec(bad)
    assert not c.passed
    assert any(k.name.startswith("gap/") and not k.ok for k in c.checks)


def test_a_hook_that_affects_nothing_fails_the_check():
    bad = _mutated(**{"hooks/H4-委外待补/affects": []})
    c = compile_mod.compile_spec(bad)
    assert any(k.name.endswith("/affects") and not k.ok for k in c.checks)


def test_a_nullable_amount_must_say_what_absence_means():
    """'Not recorded yet' and 'determined to be zero' look identical in the data
    and are opposite in the business: one is a gap to chase, the other a finding.
    Declaring which is cheap at authoring time and unrecoverable afterwards."""
    bad = _mutated(**{
        "types/委外合同/props/验收日期": {
            "type": "money", "owner": "ontology", "nullable": True,
        }
    })
    problems = spec_mod.check(bad)
    assert any("must declare absent" in p for p in problems), problems


def test_an_absent_gap_with_no_hook_fails_because_the_total_understates():
    """A null in a gap column is a missing figure. Summing over it silently
    understates the total, and an understated total that passes every other
    check is the exact failure this design exists to prevent."""
    bad = _mutated(**{
        "types/委外合同/props/金额_含税": {
            "type": "money", "owner": "source", "from": "R-CONTRACT",
            "nullable": True, "absent": "gap",
        },
        "instances/委外合同/0/金额_含税": None,
    })
    c = compile_mod.compile_spec(bad)
    failed = [k for k in c.checks if k.name.startswith("absent/") and not k.ok]
    assert failed, "an uncovered gap must be reported"
    assert "understates" in failed[0].detail


def test_an_absent_gap_is_accepted_when_the_row_cites_a_hook():
    """The rule asks for provenance, not for a value: a gap that names how it
    gets filled is a legitimate state of the world."""
    bad = _mutated(**{
        "types/委外合同/props/金额_含税": {
            "type": "money", "owner": "source", "from": "R-CONTRACT",
            "nullable": True, "absent": "gap",
        },
        "instances/委外合同/2/金额_含税": None,  # C-003 already cites H4
    })
    c = compile_mod.compile_spec(bad)
    covered = [k for k in c.checks if k.name.startswith("absent/")]
    assert covered and all(k.ok for k in covered)


def test_a_folded_group_still_shows_buckets_and_top_rows():
    """Folding that shows nothing teaches the reader only that there are too many.
    A folded group must still answer the two questions a person actually asks of a
    long list: how does it break down, and which rows carry the weight."""
    s = spec_mod.load(REAL_FIXTURE)
    g = compile_mod.compile_spec(s, fold_over=5, top_n=3).view["groups"][0]
    assert g["folded"] and g["members"] == []
    assert g["count"] == 16

    by_status = {b["value"]: b for b in g["buckets"]["状态"]}
    assert by_status["已确认"]["count"] == 9
    # Buckets and node values must agree; they are computed from the same rows.
    stuck = sum(b["totals"].get("金额_不含税", 0) for k, b in by_status.items() if k != "已确认")
    assert stuck == compile_mod.compile_spec(s).values["待坐实金额"]

    top = g["top"]["金额_不含税"]
    assert len(top) == 3
    assert top == sorted(top, key=lambda r: r["value"], reverse=True)


def test_buckets_only_form_on_enums_whose_values_the_spec_closed():
    """An open-ended column would produce as many buckets as rows, which is the
    long list again under another name."""
    s = spec_mod.load(REAL_FIXTURE)
    g = compile_mod.compile_spec(s).view["groups"][0]
    assert set(g["buckets"]) == {"认定", "状态"}
    assert "供应商" not in g["buckets"]


def test_cycles_among_derived_nodes_are_reported_not_hung():
    bad = _mutated(**{
        "nodes/委外cap": {"kind": "derived", "label": "a", "op": "委外待补金额"},
        "nodes/委外待补金额": {"kind": "derived", "label": "b", "op": "委外cap"},
    })
    with pytest.raises(ValueError, match="cycle"):
        compile_mod.compile_spec(bad)
