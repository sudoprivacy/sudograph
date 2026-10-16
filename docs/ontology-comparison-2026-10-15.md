# Ontology implementations: source inspection, 2026-10-15

This compares Sudograph with its three existing references and the Sudowork
package family added as the fourth reference. It proposes integration boundaries;
it does not merge runtimes or establish production acceptance of another project.

## The five approaches

| Project | Starting point and authority | Execution and agent access | Useful integration boundary |
| --- | --- | --- | --- |
| Sudograph | Business people and agents iteratively review complete source projections, meanings and unresolved questions. Sources own facts; checked YAML/Git owns business definitions. Frozen projections are evidence, not a live source replica. | SQLGlot admits a checked expression language; registered services enforce reads and publication. Deterministic context and exact reads now exist. Current business proposals remain unreviewed and are not new executable metrics. | Keep source identity, provenance, definition/version checks, review anchors and independent evaluation as explicit contracts. |
| TheApeironLab/ontology | Agent-facing ontology runtime over PostgreSQL, with types, links, object sets, derived properties, functions and actions. Definitions live in PostgreSQL. Table-backed objects avoid copying upstream rows. | Agent CLI navigation, transactional actions with intent, draft/publish operations and deterministic read/build evaluation suites. The inspected known-issues document limits claims about uniform row/property read enforcement. | Borrow runtime/action/evaluation ideas. PostgreSQL-owned definitions and Git-owned definitions need an explicit authority decision before integration. |
| fuyuxiang/ontology (Yuanshu) | An integrated enterprise ontology platform: object/attribute/relation models, data bindings, document evidence, versions and publication. | Current documentation describes Logic/Action, business skills, agents, REST/MCP/SDK, approval and execution auditing. These capabilities are not limited to browser storage. | Compare its published-version, data-binding and runtime contracts; do not rely on the older browser-only critique. Live deployment behaviour was not independently accepted in this study. |
| Microsoft Ontology-Playground | Static learning/catalogue/designer application around a supported RDF/XML/OWL subset. | Interactive graph exploration and supported import/export. It is not Sudograph's database execution or publication authority. | UI and interchange examples. A documented RDF subset does not by itself carry our metric scope, approvals, source bindings or enforcement. |
| Sudowork ontology packages | A host-integrated workbench: common contracts, engine, React studio and AI builder. A semantic RDF statement document retains information beyond the editor's object/relation projection. Desktop SQLite persists workspace/model/review/version state. | Version snapshots, checks, mappings, quality rules, logic/actions, published-version agent registration and tool manifests. Host services integrate sessions, MCP/tool calls and data access. | Particularly relevant for the host wiring and agent lifecycle missing from Sudograph. Reuse through adapters after defining authority, IDs, review events and execution contracts. |

The references have different objectives. A static designer, an agent runtime
and a review compiler should not be ranked by the same feature count.

## Sudowork source evidence

Inspected `origin/dev` at
`d4973e0bd2d202a2eeed7ec43e66f3390fec83a6`, without changing its checkout:

- [`ontology-common`](https://github.com/sudoprivacy/sudowork/tree/d4973e0bd2d202a2eeed7ec43e66f3390fec83a6/packages/ontology-common):
  shared snapshot/review/version/mapping/action contracts and a parsed quality-rule
  expression language. `studio.ts` defines RDF terms/statements and the editor
  projection of the retained semantic document.
- [`ontology-engine`](https://github.com/sudoprivacy/sudowork/tree/d4973e0bd2d202a2eeed7ec43e66f3390fec83a6/packages/ontology-engine):
  asset/schema reconciliation, model edits, consistency checks, publication and
  version-bound agent blueprints. Standard exchange retains unexposed statements
  and supported opaque OWL axioms; unsupported conversions are refused.
- [`ontology-ui`](https://github.com/sudoprivacy/sudowork/tree/d4973e0bd2d202a2eeed7ec43e66f3390fec83a6/packages/ontology-ui):
  model, data, capabilities, checks and release pages. `ontology-ai` hosts AI
  builder sessions rather than being another database semantics authority.
- Desktop [`OntologyService`](https://github.com/sudoprivacy/sudowork/blob/d4973e0bd2d202a2eeed7ec43e66f3390fec83a6/apps/desktop/src/process/services/ontology/OntologyService.ts),
  `OntologyDatabase`, `OntologyAgentRegistry` and `OntologyWriteBridge`: persisted
  snapshots with expected-revision checks, operation deduplication, host prompt
  construction and recoverable agent installation. Scoped builder credentials
  are denied publication/approve-all/action operations; runtime credentials are
  restricted to version-bound capabilities.
- Tests inspected include `ontologyStandard.test.ts`,
  `ontologyAgentToolRoundtrip.test.ts`, `ontologyAgentRegistry.test.ts` and
  `ontologyQualityRuleExpression.test.ts`. They cover retained RDF statements,
  unrelated edits, unsupported-conversion refusal, an independent RDF parser,
  tool roundtrips and typed validation errors. This study read those tests; it did
  not execute the complete Sudowork suite or its production deployment.

Review records in this local-workbench engine use local reviewer names or input
reviewer labels. That is a different trust contract from Sudograph's authenticated
GitLab review event bound to an exact commit. The scoped bridge is real authority
code; neither its existence nor a reviewer-label string establishes cross-system
business approval. Resolve this distinction in an integration contract.

Sudowork mappings use asset/field addresses and imported IRIs/scoped model IDs;
Sudograph uses compiler-owned source-object-field IDs plus canonical business
identity/version registries. Both preserve references, but their identity domains
must be mapped deliberately rather than allocating a second identity on import.

## Suggested integration sequence, for discussion

1. Decide who owns each fact: source facts, business definitions, identities,
   review decisions, runtime registrations and execution history.
2. Specify a versioned adapter: stable identity mapping, exact model/source pins,
   origin, review status, metric grain/scope, typed refusals and permissions.
3. Let Sudowork host sessions, tool registration and context installation while
   Sudograph supplies checked model/context and review/evaluation capabilities,
   if that ownership split is chosen.
4. Evaluate a small read-only scenario and round-trip every supported semantic
   field. Preserve unsupported RDF statements, or refuse; do not silently drop
   them. A round trip of classes/labels alone does not prove business equivalence.
5. Integrate actions only after their approval, transaction, audit and revocation
   semantics agree. Do not dual-write editable YAML and editable RDF snapshots.

These are proposed seams, not an integration already selected or deployed.

## Source types, presentation views and large graphs

Database tables store records. Database views are source SQL queries, possibly
including joins and aggregation. Both are phase-one source objects. A Sudograph
presentation view chooses how authorised source/definition identities are shown;
it is not a database view. Object-type filtering does not select local versus
complete source coverage and grants no permissions. The renderer now labels
these options explicitly rather than using an unexplained "All".

Reuse a common selection recipe for kind/component/neighbourhood/named-view
presentation where appropriate. Apply it after server authorisation, and reuse
the same identity references; the menu itself cannot become an ACL. This does
not require three new business views for table/view/both object kinds.

For graph scale, preserve a complete catalogue but render a bounded subset:

- Use weak components to identify structurally independent regions, ignoring
  source-connector supply edges and field containment when partitioning objects.
- A large component still needs a bounded neighbourhood, search/path navigation
  or proposed community grouping. Communities are structural suggestions, not
  inferred approved business domains.
- Keep edges across the displayed boundary discoverable and explicitly mark a
  partial presentation. Boundary counts must come only from authorised content.
- Reuse the same IDs across overlapping subgraphs, so comments and definitions
  follow the object. A bounded neighbourhood need not be a disjoint partition.
- SCCs are useful for cycle/dependency analysis, but require mutual reachability;
  ordinary one-way foreign keys are often split into singleton components.

On the accepted Northwind catalogue, using declared foreign keys and source-view
dependencies yields one weak component of 30 objects, versus 30 singleton strong
components. Thus neither simply putting each weak component on a canvas nor
using SCCs alone solves the large-canvas problem. This is an algorithm finding,
not a new business interpretation. No automatic partition UI is shipped here;
the existing one-hop focus is not a full large-graph solution.

## Evaluation should survive every model revision

Computational self-checks (`compiler.measure`) and independent source questions
(`compiler.blind`) already existed. The working frozen/overlay path had zero
measurements and no attached challenge. That delivery gap made the capability
disappear during iteration; it was not evidence that no generic code existed.

New source/overlay builds automatically carry questions generated from the raw
source catalogue: counts, missing values, numeric extrema and declared-reference
coverage. They include source database views, preserve target identities, contain
no oracle SQL/answers, and do not depend on an LLM inventing a question. The
business renderer refuses a removed or modified bank; the managed context
contract advertises `context_read` with `id: evaluation`.

`compiler.evaluation` prepares a reproducible sample with operator-owned source
identity/file-hash registrations. Only the judge reads those databases and
executes oracle SQL. Public questions and the private run must be stored in
different directories. Grade against the registered model digest; missing answers
remain in the denominator. Preparation is explicitly `prepared_not_run` and the
reader displays `not_run`; neither is an LLM comprehension score.

Source registrations must name the accepted source data revision, not a newer
database chosen by an answerer. A production sandbox must withhold raw DBs,
source credentials, judge files and oracle SQL from the answerer. Local test
fixtures establish compiler/transport boundaries, not OS-level isolation.

Business-meaning tests still need reviewed expected interpretations. A source
count or numerical self-check cannot establish that "sales" means what a
stakeholder intended. Keep that evaluation gap visible.

## Reference status

- TheApeironLab local snapshot: `dafdcd4b1ab2531144e60fbc481b88ef22bc54e8`,
  `README.en.md`, `docs/TECHNICAL.md`, `docs/KNOWN_ISSUES.md`, `apps/onto/EVAL.md`.
  Its public GitHub URL returned 404 during this audit; current remote contents
  were not verified. Conclusions above are scoped to that local revision.
- [Yuanshu current project documentation](https://github.com/fuyuxiang/ontology/blob/master/README.en.md).
- [Microsoft supported RDF subset](https://github.com/microsoft/Ontology-Playground#rdf-import--export).
- NetworkX definitions of
  [weak components](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.components.weakly_connected_components.html)
  and [strong components](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.components.strongly_connected_components.html).
