# sudograph

A business ontology as code: one YAML spec → compiler → graph.

Objects, links, and permissioned ops. **Git is the history.**

## Where the decisions live

**All design decisions are recorded in [Sudo Cloud 架构与设计 §7](https://s.shareone.vip/s/sudo-cloud-plan). This repo does not restate them.**

That section covers the harness elements, the SSOT rules, agent working
discipline, the reversibility tiers, the three-layer split, read governance, the
interaction surface, and the two measurement axes. If this README and that page
disagree, the page wins. To change a decision, change the page and comment on the
node there — not here.

This README only covers how to use the repo.

## Layout

```
schema/spec.schema.json   JSON Schema for a spec — the owner rule as validation
examples/*.yaml           fixtures
compiler/
  expr.py                 restricted expression language: parsed, never eval'd
  spec.py                 loading + validation; the owner rule refuses at load
  compile.py              dependency order, values, checks, view model
  diff.py                 two bases -> derived adjusting entries
  lineage.py              lineage, provisionality, completeness — all derived
  history.py              edit timelines, pending proposals
  apply.py                the only path by which anything changes
tools/check_examples.py   CI gate: every example loads, validates, and reconciles
```

## Language

Field names are English because they are the contract. Values keep the
customer's own business vocabulary, because translating business terms loses
them. So `owner: source` and `resolve_when:` are English; `委外合同` and
`可资本化` are not.

## What a spec looks like

See `examples/weiwai-capitalisation.yaml`.

- `types` declare object types; every property carries an `owner`
  (`source` or `ontology`)
- `raw` entries are fetch points holding **one executable command**, not data
- `hooks` register gaps by name, with a `resolve_when` and an `owner`
- `nodes` of `kind: derived` carry an `op` expression
- `ops` are write-back actions; `intent` is required
- `bases` hold two sets of figures over one structure — see below

## Two bases, one structure

A restatement is two sets of figures over the same business: what the books say,
and what they should say. The usual shape is two documents plus a hand-written
list of adjusting entries. Then it drifts — a figure moves on one side, the entry
still reads as it did, and the reconciliation is fiction that balances.

Here both live in one spec. Only the expressions that genuinely differ are
written twice:

```yaml
bases: [账面, 重述]

nodes:
  委外cap:
    kind: derived
    op@账面:  "select sum(金额_不含税) from 委外合同 where 认定 = '资本化'"
    op@重述:  "select sum(金额_不含税) from 委外合同 where 认定 = '资本化' and 状态 = '已确认'"
    because: H-待合同          # must cite a raw or a hook, not free text
    entry:
      debit:  研发费用-委外
      credit: 开发支出-委外
```

```bash
python -m compiler.cli examples/weiwai-real.yaml --basis 重述
python -m compiler.cli examples/weiwai-real.yaml --diff 账面:重述
python -m compiler.cli examples/weiwai-real.yaml --diff 账面:重述 --period 26H1
```

The entries are **computed from the difference**, never transcribed. Change
either side and the amount moves with it.

| | What it is | Why it is separate |
|---|---|---|
| **entry** | a node whose *expression* differs between bases | this is where the restatement was decided, so this is where it is booked |
| **carried** | a node whose expression is identical but whose value moved anyway | a consequence, not a decision. Booking it would double-count every level of the graph. `origins` names the entries that moved it |
| **unexplained** | a difference with no entry above it | the one outcome this exists to prevent. Reported, and fails CI |

Four refusals hold the shape:

- a node that diverges but declares no `because` — an entry needs a reason
- a `because` that is not a raw or a hook — free text is not provenance
- an `entry` with only one side — half an entry does not balance
- **silence under one basis** — write `op@账面: "0"` if it is genuinely nil
  there. "Nil in the books" and "we have not worked this out" look identical and
  mean opposite things; this is `absent: gap|zero` one level up

And compiling a spec that declares `bases` without naming one is refused
outright. "Which set of figures is this" is not a question a caller may leave
open.

## The expression language is a SQL subset

The compiler parses it. It never calls `eval`, because a spec that can eval hands
execution to the model that wrote it.

It is **SQL**, not a language of our own. An earlier version used an invented
syntax (`sum(T where c -> p)`); it parsed fine and nobody could read it. The
expressions are the part of a spec a business reviewer actually has to check, so
the syntax has to be one both a person and a model already know.

```sql
select sum(金额_不含税) from 委外合同 where 认定 = '资本化' and 状态 = '已确认'
select count(*) from 委外合同
委外cap + 待坐实金额                                   -- node values are bare names
(select sum(金额) from 账面委外) - 委外合计             -- nested = scalar subquery
```

A node's whole expression may be a bare `select`; anywhere else an aggregate is a
**scalar subquery in parentheses**, exactly as in SQL. That is not ceremony —
without them, `select sum(x) from T where c + 1` has two readings.

**Subtracted from SQL**, each because it would let a figure mean two things: no
joins or subqueries in `FROM` (one type per aggregate), no `GROUP BY` (grouping is
a view decision and lives in the compiler), no `ORDER BY` / `LIMIT` (a total does
not depend on row order), no `DISTINCT`, no `CASE`, no functions beyond `SUM` and
`COUNT`. Keywords are case-insensitive, as in SQL.

**SQL's semantics kept**: `SUM` skips nulls and `COUNT(<prop>)` counts the
non-null. The risk that creates — a total silently understated by a missing
figure — is not fixed by changing the arithmetic, which would surprise every
reader; it is caught one level up by `absent: gap`.

**One refused instead**: `x = null` is never true in SQL, which reads as "no such
row" and means "the question was malformed". It is rejected, naming `is null`.

## Three gates on every write

`apply.py` refuses in this order, because each gate answers a different question:

| Gate | Question | Refusal |
|---|---|---|
| owner | is this field writable at all? | only `owner=ontology` may be written |
| class | may this actor land it? | `DerivedOp` agent · `RecordableOp` human · `BlockedOp` nobody |
| intent | why is it changing? | required, and must cite an existing raw or hook |

A write that passes all three appends an edit record beside the spec:

```yaml
- at: '2026-09-23T13:42:32Z'
  by: agent:scode-1
  op: 标记可资本化
  target: 委外合同/C-003
  changes:
    - { prop: 可资本化, from: 待补, to: 是 }
  intent: OCR 后读出 IP 条款第十二条，知识产权归甲方
  refs: [R-CONTRACT, H4-委外待补]
```

That record travels with the spec into git, so there is no second place where
"what changed and why" could disagree with the graph.

## Running it

Requires Python 3.11+ and `pyyaml`. Nothing else — the compiler is meant to run
wherever an agent runs.

```bash
python -m compiler.cli examples/weiwai-capitalisation.yaml        # values + checks
python -m compiler.cli examples/weiwai-capitalisation.yaml --view # view model JSON
python -m pytest                                                  # tests
python -m tools.check_examples                                    # what CI runs
```

Exit codes are a branching protocol, so a calling agent can tell the cases apart
without parsing prose: `0` green · `2` the spec (or the invocation) is wrong ·
`3` the spec is valid but a check failed · `1` a bug in the tool.

## References

Three implementations we read before designing this one. Each took a different
position, and the differences are the reason several rules here are phrased the
way they are.

| Repo | What it is | What we took, or deliberately did not |
|---|---|---|
| [TheApeironLab/ontology](https://github.com/TheApeironLab/ontology) | A Palantir-Foundry-shaped ontology engine on PostgreSQL: objects, links, action types, markings | The closest in spirit. We took the per-property owner split, the audit spine with a required intent, approval defaulting to two people, and the eval harness shape. We did not take PostgreSQL as the store — the spec lives in git, so history and rollback come for free |
| [fuyuxiang/ontology](https://github.com/fuyuxiang/ontology) (元枢) | A Python/Vue platform where an LLM drafts the ontology from documents and schemas | The wizard idea is right, and its prompts deliberately avoid modelling jargon when talking to business users. But human corrections there live only in browser storage, so the loop never closes. That is why edit records here are structured and versioned |
| [microsoft/Ontology-Playground](https://github.com/microsoft/Ontology-Playground) | A static teaching site and catalogue for Microsoft Fabric IQ | Worth borrowing for interaction patterns — inspector panels, path finding, honest "lost anchor" behaviour. Not for the data model: its RDF/OWL carries 956 classes and zero `rdfs:subClassOf`, so the standard's syntax is paid for without its semantics |

## Data discipline

- Specs go into git; **source material does not** — scans, statements and
  contract PDFs are data, not spec
- Credentials never enter a spec, and never enter this repo
- Suppliers in the fixture are desensitised to an industry and a line of
  business; amounts are rescaled, but the with-tax to without-tax relationship
  is real, because that is the part the compiler has to get right
