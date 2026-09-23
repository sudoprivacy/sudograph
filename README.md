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
  apply.py                the only path by which anything changes
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

## The expression language

The compiler parses it. It never calls `eval`, because a spec that can eval hands
execution to the model that wrote it. Whitelist:

- arithmetic `+ - * / ( )`
- bare identifiers (instance properties, then computed node values)
- aggregates `sum(<Type> where <cond> -> <prop>)`, `count(<Type> where <cond>)`
- comparison `== != < <= > >=`, boolean `and or not`
- literals: numbers, single-quoted strings, `null`

No function definitions, attribute chains, imports, or arbitrary calls. Adding a
capability means adding a rule — deliberately, with no back door.

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
```

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
