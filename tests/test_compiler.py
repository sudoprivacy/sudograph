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
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler import apply as apply_mod
from compiler import compile as compile_mod
from compiler import diff as diff_mod
from compiler import expr
from compiler import spec as spec_mod

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


def _group(view: dict, type_name: str) -> dict:
    """Look a group up by type. Indexing by position breaks the moment the spec
    gains a type, which is not a change any of these tests are about."""
    return next(g for g in view["groups"] if g["type"] == type_name)


def _mutated_real(**edits) -> spec_mod.Spec:
    return _mutate(REAL_FIXTURE, edits)


def _mutated(**edits) -> spec_mod.Spec:
    return _mutate(FIXTURE, edits)


def _mutate(path: str, edits: dict) -> spec_mod.Spec:
    """Build a Spec straight from a mutated document, bypassing load()'s check.

    Bypassing is the point: these tests call check() themselves so they can
    assert on the specific problem rather than on "it raised".
    """
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    doc = copy.deepcopy(doc)
    for where, value in edits.items():
        cursor = doc
        parts = where.split("/")
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
        checks=doc.get("checks") or {},
        bases=doc.get("bases") or [],
        bridges=doc.get("bridges") or {},
        dimensions=doc.get("dimensions") or [],
    )


#: The real fixture holds both sets of figures. 重述 is what the ontology itself
#: asserts; 账面 is what the company's books did. Every compile of it names one,
#: because "which figures are these" is not a question a caller may leave open.
BOOK, RESTATED = "账面", "重述"


def _real(**kw) -> compile_mod.Compiled:
    kw.setdefault("basis", RESTATED)
    return compile_mod.compile_spec(spec_mod.load(REAL_FIXTURE), **kw)


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
    unmoved = compile_mod.compile_spec(s).values["委外cap"]
    assert unmoved == before, "a proposal must not move the figures"

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

    with open(log, encoding="utf-8") as fh:
        entries = yaml.safe_load(fh)
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


def test_sum_needs_a_named_property():
    with pytest.raises(expr.ExprError, match="name the property"):
        expr.parse("select sum(*) from 委外合同")


def test_aggregated_types_come_from_the_ast_not_from_substring_matching():
    """Regression: a type whose name is a substring of another drew a phantom edge."""
    node = expr.parse(
        "(select sum(y) from 合同 where x = 1) + (select count(*) from 委外合同)"
    )
    assert expr.aggregated_types(node) == {"合同", "委外合同"}
    # The substring approach would have matched 合同 inside 委外合同 as well.
    assert "委外合同" not in expr.aggregated_types(expr.parse("select sum(y) from 合同"))


def test_the_syntax_is_sql_and_the_old_spellings_say_so():
    """An invented syntax nobody could read was replaced by a SQL subset. The
    spellings it used are still recognised — only so the error can name the SQL
    that takes their place, rather than leaving the author to guess."""
    with pytest.raises(expr.ExprError, match="projection arrow is gone"):
        expr.parse("sum(委外合同 where 认定 = '资本化' -> 金额)")
    with pytest.raises(expr.ExprError, match="use `=` for equality"):
        expr.parse("委外cap == 1")


def test_an_aggregate_outside_a_select_is_refused_with_the_form_to_use():
    with pytest.raises(expr.ExprError, match="needs a select around it"):
        expr.parse("sum(金额) + 1")


def test_a_bare_select_is_a_whole_expression_but_nests_only_in_parentheses():
    """Without the parentheses `select sum(x) from T where c + 1` has two
    readings, and a figure whose value depends on how the reader groups it is
    the opposite of the point."""
    expr.parse("select sum(金额) from 委外合同 where 认定 = '资本化'")
    expr.parse("(select sum(金额) from 委外合同) + 1")
    with pytest.raises(expr.ExprError, match="trailing input"):
        expr.parse("select sum(金额) from 委外合同 + 1")


def test_keywords_are_case_insensitive_as_in_sql():
    rows = {"T": [{"a": 3}, {"a": 4}]}
    for src in [
        "select sum(a) from T",
        "SELECT SUM(a) FROM T",
        "Select Sum(a) From T Where a > 0",
    ]:
        assert expr.evaluate(expr.parse(src), {}, rows) == 7


def test_comparing_with_null_is_refused_rather_than_silently_false():
    """`x = null` is never true in SQL, which reads as 'no such row' and means
    'the question was malformed'. Evaluating it to false would hide the mistake
    behind a plausible figure."""
    for src in ["select sum(a) from T where a = null", "select sum(a) from T where null <> a"]:
        with pytest.raises(expr.ExprError, match="is null"):
            expr.parse(src)


def test_is_null_selects_the_rows_a_gap_lives_in():
    rows = {"T": [{"a": 1}, {"a": None}, {"a": 2}]}
    n = lambda src: expr.evaluate(expr.parse(src), {}, rows)  # noqa: E731
    assert n("select count(*) from T where a is null") == 1
    assert n("select count(*) from T where a is not null") == 2
    # SQL's own semantics: SUM skips nulls, COUNT(<prop>) counts the non-null.
    assert n("select sum(a) from T") == 3
    assert n("select count(a) from T") == 2


def test_sql_is_subtracted_from_not_dialected():
    """Each of these would let a figure mean two things. The refusal names where
    the capability actually lives, because a restriction with no redirection
    reads as an omission — and "trailing input 'group'" reads as a typo."""
    for src, says in [
        ("select sum(a) from T group by b", "grouping is a view decision"),
        ("select sum(a) from T order by b", "must not depend on row order"),
        ("select sum(a) from T limit 1", "not the figure"),
        ("select sum(a) from T having a > 1", "filter in WHERE"),
        ("select sum(a) from T join U on x = y", "modelled as a link"),
        ("select sum(a) from T union select sum(b) from U", "add the two selects"),
    ]:
        with pytest.raises(expr.ExprError, match=says):
            expr.parse(src)


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
    g = _group(_real(fold_over=5, top_n=3).view, "委外合同")
    assert g["folded"] and g["members"] == []
    assert g["count"] == 16

    by_status = {b["value"]: b for b in g["buckets"]["状态"]}
    assert by_status["已确认"]["count"] == 9
    # Buckets and node values must agree; they are computed from the same rows.
    stuck = sum(b["totals"].get("金额_不含税", 0) for k, b in by_status.items() if k != "已确认")
    assert stuck == _real().values["待坐实金额"]

    top = g["top"]["金额_不含税"]
    assert len(top) == 3
    assert top == sorted(top, key=lambda r: r["value"], reverse=True)


def test_buckets_only_form_on_enums_whose_values_the_spec_closed():
    """An open-ended column would produce as many buckets as rows, which is the
    long list again under another name."""
    g = _group(_real().view, "委外合同")
    assert set(g["buckets"]) == {"认定", "状态"}
    assert "供应商" not in g["buckets"]


def test_cycles_among_derived_nodes_are_reported_not_hung():
    bad = _mutated(**{
        "nodes/委外cap": {"kind": "derived", "label": "a", "op": "委外待补金额"},
        "nodes/委外待补金额": {"kind": "derived", "label": "b", "op": "委外cap"},
    })
    with pytest.raises(ValueError, match="cycle"):
        compile_mod.compile_spec(bad)


# ── lineage, provisionality, completeness ──────────────────────────────

def test_provisionality_travels_along_lineage():
    """A total whose input is provisional is provisional too. Nobody propagates
    that by hand, which is why it is derived rather than declared."""
    nodes = {n["id"]: n for n in _real().view["nodes"]}
    total = nodes["委外合计"]
    assert set(total["lineage"]["inputs"]) == {"委外cap", "待坐实金额"}
    # No hook names 委外合计 directly; it inherits all three from its inputs —
    # including 供应商未派人, which is a gap about *staffing* two hops away and
    # still reaches the total. Nobody would have propagated that by hand.
    assert set(total["provisional_because"]) == {"H-待IP条款", "H-待合同", "H-供应商未派人"}
    assert total["completeness"] == "partial"


def test_a_node_no_hook_reaches_is_complete():
    nodes = {n["id"]: n for n in _real().view["nodes"]}
    assert nodes["合同笔数"]["completeness"] == "full"
    assert nodes["合同笔数"]["provisional_because"] == []


def test_lineage_is_exposed_as_edges_a_renderer_can_draw():
    edges = _real().view["edges"]
    feeds = {(e["from"], e["to"]) for e in edges if e["rel"] == "feeds"}
    assert ("委外cap", "委外合计") in feeds
    assert ("待坐实金额", "委外合计") in feeds


# ── articulation checks: the unit tier ─────────────────────────────────

def test_a_false_articulation_check_fails_and_quotes_itself():
    bad = _mutated_real(**{"checks/合计闭合": "委外合计 = 1"})
    c = compile_mod.compile_spec(bad, basis=RESTATED)
    failed = [k for k in c.checks if k.name == "articulation/合计闭合"]
    assert failed and not failed[0].ok
    assert "is false" in failed[0].detail


def test_a_check_scoped_to_another_period_is_not_counted_either_way():
    """Skipping is not passing. A check that did not run must never read as
    evidence, so it is absent from the tally rather than marked ok."""
    def names(c):
        return {k.name for k in c.checks}

    whole = names(_real())
    only_2023 = names(_real(at={"期间": "2023"}))
    assert "articulation/台账总额" in whole
    assert "articulation/台账总额" not in only_2023
    assert "articulation/二三年合计" in only_2023
    assert "articulation/二三年合计" not in whole


# ── periods ────────────────────────────────────────────────────────────

def test_one_spec_serves_every_period_without_duplicating_nodes():
    """The figures come from the real ledger; each period must match it."""
    for period, expected in [("2023", 7_170_000), ("2025", 9_498_000), ("26H1", 10_820_000)]:
        c = _real(at={"期间": period})
        assert c.values["委外合计"] == expected, period
        assert c.passed, [(k.name, k.detail) for k in c.checks if not k.ok]
    assert _real().values["委外合计"] == 27_488_000


def test_an_unquoted_year_is_refused_rather_than_silently_matching_nothing():
    """YAML types bare tokens: 2025 becomes an int while 26H1 stays a string,
    so a period filter would match one and not the other. Coercing would hide
    that the spec and the data disagree."""
    bad = _mutated_real(**{"instances/委外合同/4/期间": 2025})
    problems = spec_mod.check(bad)
    assert any("not a string" in p for p in problems), problems


# ── plugs ──────────────────────────────────────────────────────────────

def test_a_plug_reports_its_divergence_every_run():
    """A balancing figure is the one place a discrepancy can hide. Computing the
    difference every time is what stops it drifting quietly between runs."""
    assert _real().values["台账账面差__residual"] == 668_000
    for period in ("2023", "2025"):
        assert _real(at={"期间": period}).values["台账账面差__residual"] == 0
    assert _real(at={"期间": "26H1"}).values["台账账面差__residual"] == 668_000


def test_a_plug_with_nowhere_to_register_its_difference_is_refused():
    """'Do not silently absorb' becomes a refusal rather than a discipline."""
    bad = _mutated_real(**{"nodes/台账账面差": {
        "kind": "derived", "label": "x", "op": "委外合计", "plug_against": "账面委外投入",
    }})
    problems = spec_mod.check(bad)
    assert any("absorbs it silently" in p for p in problems), problems


def test_residual_to_must_name_a_real_hook():
    bad = _mutated_real(**{"nodes/台账账面差/residual_to": "H-nope"})
    problems = spec_mod.check(bad)
    assert any("is not a hook" in p for p in problems), problems


# ── people ─────────────────────────────────────────────────────────────

def test_a_hook_owner_resolves_to_a_person_the_graph_can_show():
    """So an agent can chase a gap without a human first working out who
    '供应商对接人' refers to."""
    v = _real().view
    owned = {(e["from"], e["to"]) for e in v["edges"] if e["rel"] == "owned_by"}
    assert ("H-待合同", "人/P-01") in owned
    people = {
        r["props"]["工号"]: r["props"]
        for g in v["groups"] if g["type"] == "人"
        for r in g["members"]
    }
    assert people["P-01"]["联系"] == "wecom:jia"


def test_an_owner_pointing_at_a_missing_person_is_refused():
    bad = _mutated_real(**{"hooks/H-待合同/owner": "人/P-99"})
    problems = spec_mod.check(bad)
    assert any("no 人 with id" in p for p in problems), problems


def test_a_type_definition_pasted_under_instances_says_so():
    """Without this the first row access raises an AttributeError that says
    nothing about where to look."""
    bad = _mutated_real(**{"instances/人": {"label": "oops", "id": "x", "props": {}}})
    problems = spec_mod.check(bad)
    assert any("not a list of rows" in p for p in problems), problems


# ── two bases: adjusting entries are derived, not authored ─────────────

def test_a_spec_with_two_bases_refuses_to_compile_without_one():
    """The books say one number and the restatement says another. A caller who
    did not name a basis would get whichever the author wrote first."""
    s = spec_mod.load(REAL_FIXTURE)
    with pytest.raises(ValueError, match="computes under a basis"):
        compile_mod.compile_spec(s)
    with pytest.raises(ValueError, match="unknown basis"):
        compile_mod.compile_spec(s, basis="税务")


def test_the_two_bases_produce_different_figures_from_one_structure():
    book, restated = _real(basis=BOOK), _real(basis=RESTATED)
    assert book.values["委外cap"] == 27_488_000       # books capitalised the lot
    assert restated.values["委外cap"] == 20_863_000    # only what materials support
    assert book.values["待坐实金额"] == 0
    assert restated.values["待坐实金额"] == 6_625_000
    # The reclassification moves the split, not the total.
    assert book.values["委外合计"] == restated.values["委外合计"] == 27_488_000
    for c in (book, restated):
        assert c.passed, [(k.name, k.detail) for k in c.checks if not k.ok]


def test_the_adjusting_entry_is_computed_from_the_difference():
    """Nobody writes the entry. Change either side and the amount moves with it,
    which is exactly what a hand-kept reconciliation cannot promise."""
    d = diff_mod.diff(spec_mod.load(REAL_FIXTURE), BOOK, RESTATED)
    booked = {e.node: e for e in d.entries}
    assert set(booked) == {"委外cap", "待坐实金额"}
    assert booked["委外cap"].amount == -6_625_000
    assert booked["委外cap"].debit == "研发费用-委外"
    assert booked["委外cap"].credit == "开发支出-委外"
    assert booked["委外cap"].because == "H-待合同"
    assert booked["委外cap"].ops == {
        BOOK: "select sum(金额_不含税) from 委外合同 where 认定 = '资本化'",
        RESTATED: "select sum(金额_不含税) from 委外合同 where 认定 = '资本化' and 状态 = '已确认'",
    }
    # Only what actually posts is totalled: the holdback is a memo figure and no
    # account moves for it, so adding it would report a net effect nothing shows.
    assert d.posted() == -6_625_000
    assert d.total() == 0
    assert d.explained


def test_an_entry_moves_when_the_underlying_data_does():
    """The point of deriving it. Reclassify one contract and the entry follows;
    a transcribed entry would still read as it did."""
    before = diff_mod.diff(spec_mod.load(REAL_FIXTURE), BOOK, RESTATED)
    s = spec_mod.load(REAL_FIXTURE)
    row = next(r for r in s.instances["委外合同"] if r["合同编号"] == "W-004")
    row["状态"] = "已确认"
    after = diff_mod.diff(s, BOOK, RESTATED)
    moved = {e.node: e.amount for e in after.entries}
    assert moved["委外cap"] == before.entries[0].amount + 4_036_000 == -2_589_000


def test_a_difference_nobody_decided_is_attributed_not_booked_again():
    """A total that moved because an entry above it moved is a consequence, not
    a second adjustment. Booking it would double-count every level of the graph."""
    s = spec_mod.load(REAL_FIXTURE)
    # Break the equality that currently keeps the total identical under both
    # bases, so there is something downstream to attribute.
    s.nodes["待坐实金额"]["op@账面"] = "0"
    s.nodes["委外合计"]["op"] = "委外cap"
    d = diff_mod.diff(s, BOOK, RESTATED)
    carried = {c.node: c for c in d.carried}
    assert "委外合计" in carried and "委外合计" not in {e.node for e in d.entries}
    assert carried["委外合计"].origins == ["委外cap"]
    assert carried["委外合计"].amount == -6_625_000
    # 台账账面差 plugs against the total, so it inherits the same movement.
    assert carried["台账账面差"].origins == ["委外cap"]
    assert d.explained


def test_a_divergence_with_no_reason_is_refused():
    """The difference becomes an adjusting entry, and an entry needs a reason —
    so the reason is a load-time refusal rather than a review-time question."""
    bad = _mutated_real(**{"nodes/委外cap/because": None})
    problems = spec_mod.check(bad)
    assert any("declares no reason" in p for p in problems), problems


def test_a_reason_must_cite_a_raw_or_a_hook_not_free_text():
    bad = _mutated_real(**{"nodes/委外cap/because": "管理层认为应该这样"})
    problems = spec_mod.check(bad)
    assert any("not a raw or a hook" in p for p in problems), problems


def test_silence_under_one_basis_is_refused_rather_than_read_as_zero():
    """Exactly the ambiguity absent:'gap' exists to prevent, one level up: 'nil
    under the book figures' and 'we have not worked this one out' look the same."""
    bad = _mutated_real(**{"nodes/待坐实金额": {
        "kind": "derived", "label": "x", "op@重述": "1", "because": "H-待合同",
    }})
    problems = spec_mod.check(bad)
    assert any("no expression under '账面'" in p for p in problems), problems


def test_half_an_entry_does_not_balance():
    bad = _mutated_real(**{"nodes/委外cap/entry": {"debit": "研发费用-委外"}})
    problems = spec_mod.check(bad)
    assert any("needs both 'debit' and 'credit'" in p for p in problems), problems


def test_an_expression_naming_an_undeclared_basis_is_refused():
    bad = _mutated_real(**{"nodes/委外cap/op@税务": "0"})
    problems = spec_mod.check(bad)
    assert any("not listed in 'bases'" in p for p in problems), problems


def test_the_diff_refuses_a_basis_the_spec_never_declared():
    s = spec_mod.load(REAL_FIXTURE)
    with pytest.raises(ValueError, match="unknown basis"):
        diff_mod.diff(s, BOOK, "税务")


def test_the_diff_is_period_scopable_like_every_other_figure():
    """One spec, every period, both bases — the three axes compose rather than
    multiplying into a document per combination."""
    s = spec_mod.load(REAL_FIXTURE)
    amounts = {}
    for period in ("2023", "2025", "26H1"):
        d = diff_mod.diff(spec_mod.load(REAL_FIXTURE), BOOK, RESTATED, at={"期间": period})
        amounts[period] = d.posted()
    assert amounts["2023"] == 0 and amounts["2025"] == 0
    assert amounts["26H1"] == -6_625_000
    whole = diff_mod.diff(s, BOOK, RESTATED).posted()
    assert whole == sum(amounts.values())


# ── links: one object reaching another ─────────────────────────────────

def test_a_ref_to_a_type_becomes_an_edge_at_both_zoom_levels():
    """Type level always, because "these two are related, and this much of it is
    unmatched" is the question a reviewer opens with. Instance level only when
    the group is not folded — 556 edges on a canvas that folded the rows away is
    the long list again wearing a different hat."""
    v = _real().view
    type_edge = next(
        e for e in v["edges"] if e["rel"] == "links" and e["from"] == "委外合同"
    )
    assert type_edge["to"] == "供应商" and type_edge["via"] == "供应商"
    assert type_edge["linked"] == 16 and type_edge["unlinked"] == 0

    inst = {(e["from"], e["to"]) for e in v["edges"] if e["rel"] == "link"}
    assert ("委外合同/W-001", "供应商/供应商01") in inst
    assert ("供应商/供应商04", "人/P-01") in inst


def test_instance_edges_fold_away_with_their_group():
    folded = _real(fold_over=5).view
    assert _group(folded, "委外合同")["folded"]
    kept = [e for e in folded["edges"] if e["rel"] == "link" and e["from"].startswith("委外合同/")]
    assert kept == []
    # The type-level edge survives, still carrying the counts.
    still = next(e for e in folded["edges"] if e["rel"] == "links" and e["from"] == "委外合同")
    assert still["linked"] == 16


def test_a_link_pointing_at_a_missing_object_fails_the_check():
    """An edge to nowhere teaches a reviewer only that the graph lied."""
    bad = _mutated_real(**{"instances/委外合同/0/供应商": "供应商99"})
    c = compile_mod.compile_spec(bad, basis=RESTATED)
    failed = [k for k in c.checks if k.name.startswith("link/委外合同/W-001")]
    assert failed and not failed[0].ok
    assert "does not exist" in failed[0].detail


def test_a_ref_must_say_what_it_points_at():
    bad = _mutated_real(**{"types/供应商/props/对接人": {
        "type": "ref", "owner": "ontology", "nullable": True, "absent": "gap",
    }})
    problems = spec_mod.check(bad)
    assert any("a ref needs 'to'" in p for p in problems), problems

    bad = _mutated_real(**{"types/供应商/props/对接人/to": "不存在的类型"})
    problems = spec_mod.check(bad)
    assert any("neither a declared type nor 'hook'" in p for p in problems), problems


def test_a_nullable_link_must_say_what_absence_means():
    """Same ambiguity as a nullable number, one level over: 'not matched yet'
    and 'determined to have no counterpart' are opposite findings."""
    doc = {"type": "ref", "owner": "ontology", "to": "人", "nullable": True}
    bad = _mutated_real(**{"types/供应商/props/对接人": doc})
    problems = spec_mod.check(bad)
    assert any("not matched yet" in p and "no counterpart" in p for p in problems), problems


def test_an_unmatched_link_with_no_hook_is_reported():
    """An unmatched row reads exactly like a matched one on the graph unless
    something says otherwise."""
    bad = _mutated_real(**{"instances/供应商/0/缺口": None})
    c = compile_mod.compile_spec(bad, basis=RESTATED)
    failed = [k for k in c.checks if k.name == "absent/供应商/供应商01/对接人"]
    assert failed and not failed[0].ok
    assert "nobody is chasing the counterpart" in failed[0].detail


def test_filtering_by_a_link_needs_no_join():
    """A ref holds the target's id, so `where <ref> = '<id>'` is plain equality.
    That is why JOIN can be subtracted without losing the common case."""
    s = spec_mod.load(REAL_FIXTURE)
    total = expr.evaluate(
        expr.parse("select sum(金额_不含税) from 委外合同 where 供应商 = '供应商07'"),
        {},
        s.instances,
    )
    assert total == 817_000 + 1_226_000


# ── corroboration: two systems, or it is only an assertion ─────────────

def test_agreeing_sources_resolve_to_the_agreed_figure():
    """A figure asserted by one system is a figure taken on trust. Two systems
    that do not talk to each other saying the same thing is what audit evidence
    actually is, so the model holds both."""
    c = _real()
    agreed = [k for k in c.checks if k.name.startswith("corroboration/账面委外")]
    assert len(agreed) == 3 and all(k.ok for k in agreed)
    assert c.values["账面委外投入"] == 26_820_000


def test_a_disagreement_with_no_hook_fails_and_quotes_both_sides():
    """The 26H1 figures genuinely differ by 668,000. Removing the hook that
    tracks it must turn the check red rather than let a preference bury it."""
    bad = _mutated_real(**{"instances/账面委外/2": {
        "科目": "5301-委外开发-26H1", "期间": "26H1",
        "金额@R-KINGDEE": 10152000, "金额@R-LEDGER": 10820000,
    }})
    c = compile_mod.compile_spec(bad, basis=RESTATED)
    failed = [k for k in c.checks if k.name.startswith("corroboration/") and not k.ok]
    assert len(failed) == 1
    assert "10152000" in failed[0].detail and "10820000" in failed[0].detail
    assert "cites no hook" in failed[0].detail
    # The disputed figure is unusable, so the total drops it rather than picking
    # a side — and the red check is what stops that reading as the answer.
    assert c.values["账面委外投入"] == 16_668_000


def test_prefer_alone_does_not_bury_a_disagreement():
    """A preference written once would otherwise absorb every future
    disagreement silently — the same fault as a plug with no residual_to."""
    s = spec_mod.load(REAL_FIXTURE)
    rules = s.types["账面委外"]["props"]["金额"]["corroboration"]
    assert rules["prefer"] == "R-KINGDEE"
    bad = _mutated_real(**{"instances/账面委外/2": {
        "科目": "5301-委外开发-26H1", "期间": "26H1",
        "金额@R-KINGDEE": 10152000, "金额@R-LEDGER": 10820000,
    }})
    c = compile_mod.compile_spec(bad, basis=RESTATED)
    assert not c.passed, "prefer is declared, yet the unhooked disagreement must still fail"


def test_a_disagreement_needs_prefer_to_say_which_source_governs():
    bad = _mutated_real(**{
        "types/账面委外/props/金额/corroboration": {"at_least": 2},
    })
    c = compile_mod.compile_spec(bad, basis=RESTATED)
    failed = [k for k in c.checks if k.name.startswith("corroboration/") and not k.ok]
    assert failed and "which source governs" in failed[0].detail


def test_too_few_sources_spoke():
    bad = _mutated_real(**{"instances/账面委外/0": {
        "科目": "5301-委外开发-2023", "期间": "2023", "金额@R-KINGDEE": 7170000,
    }})
    c = compile_mod.compile_spec(bad, basis=RESTATED)
    failed = [k for k in c.checks if k.name.endswith("/5301-委外开发-2023/金额")]
    assert failed and not failed[0].ok
    assert "1 of 2 sources" in failed[0].detail


def test_a_corroborated_figure_may_not_also_be_written_bare():
    """A bare value alongside the per-source ones is a third figure with no
    source — exactly what corroboration exists to prevent."""
    bad = _mutated_real(**{"instances/账面委外/0/金额": 7170000})
    problems = spec_mod.check(bad)
    assert any("written bare" in p for p in problems), problems


def test_a_per_source_value_must_name_a_declared_source():
    bad = _mutated_real(**{"instances/账面委外/0/金额@R-ROSTER": 1})
    problems = spec_mod.check(bad)
    assert any("not among the sources declared" in p for p in problems), problems


def test_corroboration_needs_more_than_one_source():
    bad = _mutated_real(**{"types/账面委外/props/金额": {
        "type": "money", "owner": "source", "from": "R-KINGDEE",
        "corroboration": {"at_least": 1},
    }})
    problems = spec_mod.check(bad)
    assert any("agreeing with itself" in p for p in problems), problems


def test_an_unreachable_at_least_is_refused_at_load():
    bad = _mutated_real(**{"types/账面委外/props/金额/corroboration": {"at_least": 5}})
    problems = spec_mod.check(bad)
    assert any("can never be met" in p for p in problems), problems


def test_prefer_must_be_one_of_the_sources():
    bad = _mutated_real(**{
        "types/账面委外/props/金额/corroboration": {"at_least": 2, "prefer": "R-ROSTER"},
    })
    problems = spec_mod.check(bad)
    assert any("not among its sources" in p for p in problems), problems


def test_every_declared_source_must_own_up_to_providing_it():
    """A second source that never claimed to supply the figure is not
    corroboration; it is one source and a hopeful entry in a list."""
    bad = _mutated_real(**{"raw/R-LEDGER/provides": ["合同编号", "供应商", "期间", "供应商编号"]})
    c = compile_mod.compile_spec(bad, basis=RESTATED)
    failed = [k for k in c.checks if k.name == "provenance/账面委外.金额@R-LEDGER"]
    assert failed and not failed[0].ok


# ── more than two readings ─────────────────────────────────────────────

def _three_readings(**extra) -> dict:
    """The real fixture plus a third reading, as a mutable document."""
    edits = {
        "bases": ["账面", "重述", "税务"],
        "bridges": {
            "重述桥": {"from": "账面", "to": "重述", "label": "会计重述调整"},
            "税会差": {"from": "重述", "to": "税务", "label": "税会差异"},
        },
        "nodes/委外cap/op@税务": "select sum(金额_不含税) from 委外合同 where 认定 = '资本化'",
        "nodes/委外cap/because@税务": "R-KINGDEE",
        "nodes/待坐实金额/op@税务": "0",
        "nodes/待坐实金额/because@税务": "R-KINGDEE",
    }
    edits.update(extra)
    return edits


def test_readings_are_a_flat_list_not_a_product_of_dimensions():
    """Three readings give three named readings, not eight worlds. Each is a
    complete reading of all the facts; they do not compose into coordinates, and
    the business does not talk that way either."""
    s = _mutated_real(**_three_readings())
    assert spec_mod.check(s) == []
    seen = {b: compile_mod.compile_spec(s, basis=b).values["委外cap"] for b in s.bases}
    assert seen == {"账面": 27_488_000, "重述": 20_863_000, "税务": 27_488_000}


def test_each_reading_carries_its_own_reason():
    """'Why is the restated figure different' and 'why is the tax figure
    different' are not the same answer, so they are not the same field."""
    s = _mutated_real(**_three_readings())
    assert s.reason_for("委外cap", "重述") == "H-待合同"
    assert s.reason_for("委外cap", "税务") == "R-KINGDEE"
    restate = diff_mod.diff(s, "账面", "重述")
    tax = diff_mod.diff(s, "重述", "税务")
    assert {e.node: e.because for e in restate.entries}["委外cap"] == "H-待合同"
    assert {e.node: e.because for e in tax.entries}["委外cap"] == "R-KINGDEE"
    # Crossing back the other way is the same entry with the sign reversed.
    assert tax.posted() == -restate.posted()


def test_past_two_readings_the_bridges_must_be_declared():
    """Three readings offer three pairings and only some are anything anyone
    wants. An undeclared bridge is a deliverable nobody agreed to produce."""
    edits = _three_readings()
    del edits["bridges"]
    problems = spec_mod.check(_mutated_real(**edits))
    assert any("no 'bridges'" in p for p in problems), problems


def test_two_readings_need_no_bridge_declaration():
    """Generalise on the third instance, not the second: with exactly two there
    is one meaningful pairing and naming it adds nothing."""
    s = spec_mod.load(REAL_FIXTURE)
    assert len(s.bases) == 2 and s.bridges == {}


def test_a_bridge_must_span_two_declared_readings():
    for bridge, says in [
        ({"from": "账面", "to": "税收"}, "not a declared reading"),
        ({"from": "账面"}, "needs 'to'"),
        ({"from": "重述", "to": "重述"}, "bridges nothing"),
    ]:
        edits = _three_readings()
        edits["bridges"] = {"坏桥": bridge}
        problems = spec_mod.check(_mutated_real(**edits))
        assert any(says in p for p in problems), (bridge, problems)


def test_two_bridges_may_not_span_the_same_pair():
    """Two names for one deliverable is two people disagreeing about what it is."""
    edits = _three_readings()
    edits["bridges"] = {
        "重述桥": {"from": "账面", "to": "重述"},
        "另一个名字": {"from": "账面", "to": "重述"},
    }
    problems = spec_mod.check(_mutated_real(**edits))
    assert any("one pair, one bridge" in p for p in problems), problems


def test_a_reading_with_no_reason_is_refused_even_when_others_have_one():
    edits = _three_readings()
    del edits["nodes/委外cap/because@税务"]
    edits["nodes/委外cap/because"] = None
    problems = spec_mod.check(_mutated_real(**edits))
    assert any("reads differently under '税务'" in p for p in problems), problems


def test_a_per_reading_key_must_name_a_declared_reading():
    bad = _mutated_real(**{"nodes/委外cap/because@税务": "H-待合同"})
    problems = spec_mod.check(bad)
    assert any("names a reading not listed in 'bases'" in p for p in problems), problems


# ── dimensions compose; bases do not ───────────────────────────────────

def _two_dimensions(**extra) -> dict:
    """The real fixture partitioned along a second axis as well."""
    with open(REAL_FIXTURE, encoding="utf-8") as fh:
        rows = yaml.safe_load(fh)["instances"]["委外合同"]
    for i, r in enumerate(rows):
        r["主体"] = "北京" if i % 2 == 0 else "上海"
    edits = {
        "dimensions": ["期间", "主体"],
        "types/委外合同/props/主体": {"type": "string", "owner": "source", "from": "R-LEDGER"},
        "types/委外合同/dimensions": {"期间": "期间", "主体": "主体"},
        "raw/R-LEDGER/provides": ["合同编号", "供应商", "期间", "供应商编号", "金额", "主体"],
        "instances/委外合同": rows,
    }
    edits.update(extra)
    return edits


def test_dimensions_compose_and_partition():
    """A dimension divides the facts: the slices are disjoint and sum to the
    whole. That is what lets any number of them compose freely."""
    s = _mutated_real(**_two_dimensions())
    assert spec_mod.check(s) == []
    whole = compile_mod.compile_spec(s, basis=RESTATED).values["委外合计"]
    parts = [
        compile_mod.compile_spec(s, basis=RESTATED, at={"主体": e}).values["委外合计"]
        for e in ("北京", "上海")
    ]
    assert sum(parts) == whole == 27_488_000
    # And they cross: one coordinate per axis, no new nodes.
    corner = compile_mod.compile_spec(s, basis=RESTATED, at={"期间": "26H1", "主体": "北京"})
    assert corner.at == {"期间": "26H1", "主体": "北京"}
    assert corner.values["委外合计"] <= whole


def test_bases_do_not_partition_so_they_never_sum():
    """The asymmetry the view model's shape encodes: coordinates are a dict
    because they compose; the basis is a scalar because only one is ever in
    force. 账面 and 重述 are each a complete reading of all the facts."""
    s = spec_mod.load(REAL_FIXTURE)
    book = compile_mod.compile_spec(s, basis=BOOK).values["委外合计"]
    restated = compile_mod.compile_spec(s, basis=RESTATED).values["委外合计"]
    assert book == restated == 27_488_000  # each is the whole, not a share of it
    v = compile_mod.compile_spec(s, basis=RESTATED).view
    assert isinstance(v["dimensions"], dict) and v["basis"] == RESTATED


def test_a_coordinate_on_an_undeclared_dimension_is_refused():
    s = spec_mod.load(REAL_FIXTURE)
    with pytest.raises(ValueError, match="not declared dimensions"):
        compile_mod.compile_spec(s, basis=RESTATED, at={"主体": "北京"})


def test_a_type_may_not_name_an_undeclared_dimension():
    bad = _mutated_real(**{"types/委外合同/dimensions": {"主体": "期间"}})
    problems = spec_mod.check(bad)
    assert any("not a declared dimension" in p for p in problems), problems


def test_a_dimension_must_name_a_property_of_that_type():
    bad = _mutated_real(**{"types/委外合同/dimensions": {"期间": "不存在"}})
    problems = spec_mod.check(bad)
    assert any("is not among its props" in p for p in problems), problems


def test_reference_data_is_never_filtered_out():
    """人 and 供应商 declare no dimension, so slicing by period must not drop
    them — every row that points at them would break."""
    s = spec_mod.load(REAL_FIXTURE)
    sliced = compile_mod.compile_spec(s, basis=RESTATED, at={"期间": "2023"}).view
    assert _group(sliced, "人")["count"] == 2
    assert _group(sliced, "供应商")["count"] == 15
    assert _group(sliced, "委外合同")["count"] == 2


def test_a_check_scoped_to_a_coordinate_is_not_counted_elsewhere():
    names = lambda c: {k.name for k in c.checks}  # noqa: E731
    whole = names(_real())
    y2023 = names(_real(at={"期间": "2023"}))
    assert "articulation/台账总额" in whole and "articulation/台账总额" not in y2023
    assert "articulation/二三年合计" in y2023 and "articulation/二三年合计" not in whole


def test_a_check_may_be_scoped_to_one_reading():
    """"The books recognise no holdback" is true under 账面 and false under 重述.
    That it cannot be said everywhere is no reason to leave it unsaid."""
    book, restated = _real(basis=BOOK), _real(basis=RESTATED)
    assert "articulation/账面无待坐实" in {k.name for k in book.checks}
    assert "articulation/账面无待坐实" not in {k.name for k in restated.checks}
    assert book.passed and restated.passed


def test_a_check_scoped_to_an_undeclared_reading_is_refused():
    bad = _mutated_real(**{"checks/账面无待坐实": {"expr": "1 = 1", "basis": "税务"}})
    problems = spec_mod.check(bad)
    assert any("not a declared reading" in p for p in problems), problems
