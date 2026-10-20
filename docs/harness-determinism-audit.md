# Harness determinism audit

Scope: the checked Sudograph `compiler/`, `app/` and acceptance tools as of
2026-10-20. An external host agent reasons with a model; this does not imply the
compiler calls a model or needs a system prompt to enforce its contracts.

No runtime model SDK or inference request was found in these paths. Network
clients target GitLab, the source gateway or Nexus; browser acceptance tools
control a real browser. This is a source audit, not a claim about every external
host, every plugin or every future deployment.

| Responsibility | Enforcement or input | Decision |
| --- | --- | --- |
| Source discovery, SQL definitions, keys, fields and record projection | `catalog`, `project`, `source_schema`, `bind` and `browse` | Deterministic. The complete scanner currently targets SQLite; PostgreSQL/MySQL completeness is separate work. |
| Allowed expressions, aggregates and source references | `spec`, `sql_parser`, `expr`, `query` and `dependencies` | Parser/compiler refusals, including SQLGlot parsing. No prompt instruction authorizes unsupported syntax. |
| Identity, duplicate signatures, evidence and definition versions | `source_schema`, `business`, canonical registry | Deterministic checks. Different wording can still express the same meaning; arbitrary semantic deduplication is not guaranteed. |
| Default business selections | `review_views`, then `business` dependency closure | Derived subject/question selections; no model call or manually maintained view list. Custom selections are optional inputs. |
| Source subgraphs and catalogue | `subgraph_select`, shared browser selector and catalogue | Stable explicit structural traversal, bounded object count; no inferred domain labels. |
| Bilingual controls, colours, layout, record drilldown and comments | Shared `app` sources and full HTML regeneration check | Authors supply checked models, not page code. CI and managed publishing verify the entire export. |
| Access, revision approval and publication | `gateway`, `serve`, `managed`, GitLab/Nexus authority adapters | Server enforcement. Static public examples are not proof of deployed host-principal integration. |
| Source question bank and private judge | `blind`, `evaluation` | Source-owned deterministic templates, private answers. They test projection/reading, not full business understanding. |
| Business purpose, interpretation, rule and evidence selection | Business participant or external model supplies candidates | Domain input. Compiler checks structure and provenance but cannot establish that a sentence expresses the right business policy. |
| Ordered agent context | `context` compiles the accepted model and read pointers | Business knowledge as data. Reuses host prompt assembly; not workflow instructions replacing enforcement. Records remain on-demand tool reads. |
| Agent memory and training | Host/model owner | Outside the model SSOT and compiler enforcement. |

## Closed authoring gap

Previously the default business UI required an author to choose view names and
seed membership lists. That was configuration dependence, not evidence of a
hidden system prompt. With `views` omitted, checked meanings/metrics generate
subject selections. Typed rules/questions attach through canonical `applies_to`
links, evidence stays in details, and unresolved issues generate question
selections. IDs and initial selection use canonical identities rather than YAML
entry order. A model cannot mark a proposal confirmed by adding a field.

This algorithm selects declared meaning; it never discovers business intent
from a label or guarantees that all relevant questions have been supplied.
Oversized closures are refused explicitly instead of silently dropping required
context. See the [navigation contract](review-navigation-contract.md).

## Remaining integration work

- The Sudowork registered-source bridge, chat discovery event and deployment
  wiring are not implemented by documenting their contracts. Host connectivity
  and complete source coverage must be accepted separately.
- The shared viewer can display a remote execution browser in an independent
  tab. Sudograph selection, text comments, clipboard and interaction latency
  still need acceptance in that actual viewer. A native local URL and a remote
  viewer are different transports even if both appear in a browser tab.
- Human confirmation of pilot definitions needs an authenticated review-state
  endpoint. The current overlay contract only produces `unreviewed` proposals;
  it rejects author-supplied approval. GitLab revision approval is not a per-rule
  business confirmation. Do not invent a confirmed-state test or prompt workaround.
- Arbitrary business-policy correctness and complete business understanding
  require real domain review and phase-three evaluation. They are not mechanical
  harness guarantees.

## Reader tutorial

The local SudoAPI implementation uses Driver.js with role-specific steps,
versioned per-user preferences, replay and a restricted admin-only auto-start.
Sudograph reuses the interaction principles with a small native dialog; it does
not import Vue, Pinia or a tour dependency into the standalone reader.

`app/reader-policy.json` is operator-controlled build configuration:
`tutorial: manual` is the default, `first-visit` offers the guide once per source
project/browser/version, and `off` disables it. This input participates in full
export regeneration checks. Skipping or finishing marks it seen; a checkbox
disables future automatic display. **Quick tour** always allows deliberate
replay unless the operator disables it. Storage failure never prevents reading.
Standalone `?guide=start` deliberately replays it, while `?guide=off` suppresses
auto-start; neither overrides operator `off` or changes permissions. A hosting
iframe must explicitly forward a query option; the outer ShareOne URL does not
automatically forward it.

The guide has no canvas listeners, recurring polling or automatic navigation.
It does not modify definitions, records, comments, camera state or authorization.
It explains business questions, source fields, real records and the review loop.
