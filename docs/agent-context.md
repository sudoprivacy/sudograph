# Agent context from the shared model

Phase three uses the source projection and versioned business model established
in the first two phases. The graph and agent context are derived presentations;
neither becomes a second editable business authority. Source records remain
owned by their registered source. A frozen snapshot is explicitly historical.

## Existing inputs and derived outputs

The phase-one generation YAML contains discovery/mapping configuration, not all
scanned facts and source rows. `compiler.source_schema` scans the database into
compiler-owned source objects, fields, original SQL, relationships and optional
lossless record snapshots. The accepted Northwind baseline currently embeds that
model in a locked HTML artifact. `compiler.context` reuses the established
baseline checker and model extractor; it does not scrape visible graph labels.

Phase-two YAML records canonical meanings, rules, issues, purposes, metric grain
and scope, source targets, evidence and definition versions. Compiler-owned IDs
and the shared registry are reused. Layouts, translations and trial models are
not alternative definitions. The current pilot's definitions retain their
`unreviewed` state; publication/merge approval does not confirm their meaning.

Business input may arrive before source discovery, through conversations or
documents. The v5 overlay accepts business definitions with `targets: []` and
derives `binding_status: unbound`. Binding and rebinding preserve the canonical
concept ID through the operator registry; changed content still needs a higher
version. An unbound metric retains its declared scope with empty source grain.
The context reader carries this status unchanged, as does the native graph.
Source reviews still require real source targets. See the
[identity contract](business-identity-and-binding.md), including legacy migration.
Unbound definitions do not acquire fabricated columns or executable status.
Evidence intake must also accept trusted supplied
conversation/document references; the current document format requires HTTPS
text evidence and does not itself capture arbitrary host conversations.

Reviewing a business meaning changes the canonical model, not source records.
For example, agreeing that sales uses order date rather than ship date changes
the definition and its references; it does not update either source column.
Semantic review state records agreement about a definition. It neither implies
a source write-back nor introduces a mandatory new approval click for every edit.

## Where information belongs

| Information | Where it exists today | Default destination | Authority and lifetime |
| --- | --- | --- | --- |
| Source structure, names, identities, source SQL | Generation YAML plus scanner-produced `source_schema` in the locked baseline artifact | Stable source context block | Registered source revision |
| Current meanings, rules, unresolved questions, relevant rationale | `pilot.yaml` / managed `model.yaml`, canonical registry, Git/MR history | Versioned knowledge blocks | Checked model; preserve confirmation state |
| Addresses for full models, evidence, review and customer data gateways | Operator `knowledge_pointers` and compiler-produced request templates | Pointer block | Operator registers addresses; tool authenticates access |
| Source records and query results | Source DB, frozen source column snapshots, tool result/session records | Tool reads during the task | Snapshot/live-data distinction and result evidence remain explicit |
| Raw discussion and abandoned drafts | Native agent sessions and ShareOne parent/reply threads, selections, state and agent stance; Git draft history where saved | Collaboration history | Retrieved when investigating a decision, not automatically preloaded |
| Reviewed corrections and successful modelling/use trajectories | Sessions, structured/free-text ShareOne feedback, Git/MR intents and diffs, compiler/tool diagnostics and `docs/trials` receipts; not yet a curated training corpus | Candidate training/evaluation corpus | Curated, permissioned, versioned; not an authority for current facts |
| Task observations and reusable working techniques | Existing agent/project memory stores and the runtime memory provider | Existing agent memory | Agent chooses what to retain; canonical references and revisions remain necessary |
| Authentication policy, credentials and validation implementation | Operator service configuration, authority adapters, compiler and trusted CI | Server | No policy dump or credentials in prompts; tools report contracts and refusals |
| Temporary debug output, transient states and presentation text | Local logs/temp files, session/tool output, locale and renderer files | Neither preload nor automatic training | Retain only when an investigation or explicit task needs it |

Not preloading information does not imply training on it. Dynamic discovery,
tool-result context, session history and persistent memory have different
lifetimes. Durable conclusions from a discussion belong in the model with their
evidence; raw conversation is not needed for every business answer. Useful
decision rationale must not be discarded merely because it originated in chat.

ShareOne `status` describes thread workflow and `agent_stance` describes the
agent's response. Neither alone confirms a business definition. A training
extractor must retain authorship, target identity, evidence and the actual model
revision when known; it must not infer a comment's revision from its timestamp.

Training examples should capture inputs, relevant model context, desired output,
tool evidence and reviewed corrections. Rejected claims must not be relabelled
as correct answers. Keep evaluation cases separate from training, and do not
turn private customer discussions into public examples. Training aims to improve
behaviour; changing customer facts and current policy remain retrievable data.
No training export or training job is implemented or implied by this adapter.

## Deterministic context compiler

`compiler.context.Reader` validates the same source and business contracts as the
renderer. Its ordered blocks are source catalogue, business definitions, source
review questions, supplied evidence, then pointers/revision metadata. It retains
source SQL, IDs, version, purpose, grain, scope, attribution, review status and
qualifications without an LLM paraphrase. Duplicate translations, drawing code,
record dictionaries and compressed column pages are not prompt content.

All current definitions and source structure are preloaded. This first adapter
does not silently truncate a model to a token limit. Larger deployments need a
measured catalogue/retrieval strategy before reducing that coverage. Repeated
ID prefixes can be abbreviated later only with a reversible identity mapping.

Exact lookup uses existing source/definition IDs. `id: catalog` returns the full
normalised knowledge catalogue, including business views; records remain paged.
A business lookup includes
forward references and definitions attached through `applies_to`, including
rules, issues and evidence notes. Source-target and document references remain
available through their IDs/pointers. Record reads are bounded to 100 rows,
retain row/column correspondence and declared keys, preserve NULL/binary/large
integer wire values, and label keyless rows as snapshot positions. The registered
snapshot is queried; no caller SQL, filesystem path or database connection is
accepted by this reader. This is not a new business-metric execution engine.

Python hosts call `Reader(checked_model).pack()`. Operator diagnostics may run:

```sh
python -m compiler.context examples/northwind/business/pilot.yaml --text
```

The agent is not responsible for remembering this command. Its host fetches and
injects the packet at session creation, and refreshes on an explicit stale-model
response. Automatic host session wiring is a deployment integration, not a
property of a saved prompt file.

## Reuse sudocode's prompt runtime

The existing sudocode implementation supplies:

- `runtime/src/prompt.rs`: `SystemPromptBuilder`, ordered static/dynamic sections,
  `load_system_prompt*`, and `append_static_section`/`extend_dynamic_sections`.
- `engine-host/src/prompt.rs`: shared system-prompt construction for CLI and ACP.
- ACP `_meta.sudocode.appendSystemPrompt`: an existing host-controlled append
  consumed by `SystemPromptOverrides.apply` and appended to static sections.
- `runtime/src/compact.rs`: conversation checkpoints, with the structured todo
  list carried separately across compaction.

The packet includes a directly usable `_meta.sudocode.appendSystemPrompt`
object; it does not replace the existing prompt builder, conversation compactor
or memory provider. A native Rust host can instead append its ordered blocks
through the existing `SystemPrompt` methods. This repository has not patched or
deployed sudocode session-start code; the adapter payload and authenticated
reader are implemented, while automatic cross-repository wiring remains next.

The packet's `text` and ordered blocks are also host-neutral outputs. Multiple
authoring conversations and review shares may refine one canonical model, and
any authorised downstream agent can load its compiled knowledge through a host
adapter. The editable model remains the SSOT; prompt copies are derived,
versioned and potentially stale. Each receiving host supplies an authorised
projection and authenticated tools rather than assuming every recipient has
the author's access. Records remain on-demand reads. Current `Reader.page`
reads a pinned snapshot; the agreed live-record default requires the data/host
adapter and must not be claimed from a static prompt or HTML export.

Keep shared runtime instructions first, followed by stable source knowledge,
versioned business knowledge and pointers; task messages and changing memory use
the runtime's existing paths. Source blocks remain byte-identical for business-
only edits. Do not insert timestamps, whole-context hashes or user-specific
memory before otherwise stable blocks. This preserves usable prefixes; actual
provider cache hit rates require measurement with the real transport, tools and
cache boundaries. Never share an unfiltered knowledge packet between subjects
merely to improve caching.

## Existing managed service transport

POST `/v1` with the existing bearer authentication:

```json
{"operation":"context"}
```

The response includes ordered blocks, their hashes, a context digest, the current
model revision and exact read request templates. A subsequent request includes
that revision and digest:

```json
{"operation":"context_read","revision":"<returned revision>","context_digest":"<returned digest>","id":"<canonical ID>"}
```

For source records add `records: true`, `offset` and `limit`. Every read rechecks
the existing project membership and operator policy. An updated model returns
`CONTEXT_STALE` rather than mixing revisions. No source path, SQL, approval flag
or permission override is a valid read parameter. These endpoints use the
managed project's existing author/reviewer scope, not a new unrestricted
end-user API or per-field authorisation system. Permission-scoped customer
answerers must receive a separately authorised model at their own boundary.

An optional operator policy `knowledge_pointers` lists objects with exactly
`name`, `kind`, `uri`, `description`. Kinds are `data_gateway`, `model_repository`,
`documents`, `review`. Addresses must use credential-free HTTPS or loopback HTTP;
tokens/DSNs are not pointers. For example a registered `data_gateway` points to
the customer's existing Gateway contract, which discovers permitted views and
enforces query/page access. Listing an address neither grants access nor proves
that an external deployment is reachable. This adapter's own record pointer
works over the pinned source snapshot even without a live-data gateway.

## Bounded source-graph navigation

The standalone reader exposes this workflow through **Views and catalogue**,
combining named presentations and source navigation in one entry. The top level
opens the complete authorised source graph; a source root restricts it to that
source. Object/field names select related subgraphs; disclosure arrows lazily
expand directory entries. The active subgraph and its banner report scope,
omitted objects and boundary relationships. Distance/cap controls and Back/return
to full source presentation do not alter facts or permissions. The offline
selector's results and typed refusals are checked against the server core.
Run `python -m tools.check_source_navigation --help` for the optional real-browser
journey; this is distinct from fresh-agent evaluation. The Sudowork host adapter
and registered-source scan bridge remain separate integration work, described in
the [source connection and scan contract](source-connection-and-scan-contract.md).

The upper **Review views** entries come from standard source presentations and
checked subject/question selectors, or optional custom overlay view declarations.
They are not a ranked subset of source
objects. The lower catalogue is the structural inventory of the same authorised
model. The optional `tools.check_canvas_labels` browser journey starts a generated
reader in a hidden iframe, then checks actual text/node rectangles after reveal,
field expansion and language switches. Node-body separation alone is not proof
that selectable DOM captions do not overlap.

See the [navigation and responsibility contract](review-navigation-contract.md)
for the exact generation triggers, default filtering and business-author
discretion. Raw scanning does not invent source-review questions or business
meanings. Default business selections are derived once checked meanings exist;
compilation does not certify the usefulness of authored semantics.

Use `context_read` with `id: subgraph` and an optional `selection` object when a
whole source graph is too large. The packet includes request templates, including
`context_read` with `id: subgraph_contract` for on-demand tool documentation.
That read returns parameters, description and role boundaries from the core
selector; full help and recovery instructions are not preloaded. Actual failures
include recovery from the same core docstring. Help reads require the same current
revision/digest and authentication as other managed reads.
The existing operator CLI accepts the same JSON selection through `--selection`
with `--read subgraph`; the JSON result is the same as `Reader.read`.

```json
{"operation":"context_read","revision":"<revision>","context_digest":"<digest>","id":"subgraph","selection":{"root":"<source/object/field ID>","hops":1,"max_nodes":40}}
```

Selection uses weak components and bounded BFS over declared foreign keys and
source SQL dependencies. Source-connector supply edges do not join otherwise
independent objects. Results retain canonical IDs and include scope, omitted
object/crossing-edge counts, component summaries and continuation parameters.
Pagination and bounds are explicit; this does not promise that an entire large
component fits one canvas. Field roots retain field focus while selecting their
parent object's neighbourhood.

LLMs may name or explain a structural group. They cannot inject new links, SQL
or approval into a selection request. New business relationships go through the
checked phase-two model. HTTP and CLI preserve the selector's error code,
recovery hint and `retryable: false`; stale revisions still require a refresh.
The service authenticates before selection and the selector grants no access.
The managed project scope remains unchanged. The shared standalone catalogue
is implemented; its Sudowork embedding and registered-source adapter are not
deployed.

## Persistent source questions and a private judge

Source discovery and business-overlay builds attach a source question bank by
default. The compiler derives it from the scanned source catalogue, including
database views: record counts, NULL counts, numeric extrema and resolvable
declared foreign-key coverage. Questions reference canonical source identities;
they contain no oracle answers or SQL. Removing or changing the bank makes a
business-model export invalid. The reader exposes it through the packet's
`evaluation` pointer and `context_read` with `id: evaluation`; it is not another
large preloaded prompt block.

The renderer's evaluation entry separates calculation self-checks from source
blind questions. Questions remain available even without executable metrics;
the separate coverage inventory checks source omissions. It reports an unrun evaluation separately from numerical
self-checks. Neither an empty self-check nor a generated question proves agent
comprehension.

An operator prepares a reproducible sample using `compiler.evaluation`:

```sh
python -m compiler.evaluation prepare MODEL_YAML SOURCES_PRIVATE_JSON PUBLIC_QUESTIONS_JSON PRIVATE_RUN_JSON --sample 3 --seed 42
python -m compiler.evaluation grade PRIVATE_RUN_JSON SUBMISSION_JSON
```

These are operator/judge commands, not instructions the answerer must remember.
Source registrations contain `source`, `dsn`, `sha256` and an optional `base`.
They must match the accepted source identity and data revision. The judge checks
file hashes, source counts and question inventory, then executes the selected
oracle SQL against raw source data. Public questions and the private run require
different directories. Deployments must separately deny the answerer access to
raw DBs, judge files and credentials; directory separation alone is not a sandbox.
SQLite judge inputs must be checkpointed snapshots without unregistered WAL data;
hashing the main file alone cannot pin pending WAL changes.

The private run binds question IDs and random seed to a model digest. A
submission contains exactly `model_digest` and an `answers` map keyed by those
IDs. The judge refuses another model digest or unregistered questions and keeps
missing answers in the denominator. Preparation reports `prepared_not_run`;
only a submitted answer set produces a score. Business-meaning tests still
need reviewed expected interpretations, which source questions cannot supply.

## Phase-three gaps and evaluation

Business use can uncover a new question, changed source data, a missing scenario,
a modelling error, a stale context or an execution bug. Missing business meaning
returns to the phase-two review loop. Source changes require source review;
reader/compiler defects require infrastructure fixes. A phase-three question
does not reopen every previously accepted definition.

The fresh-context authoring trial tests model creation. It does not establish
correct use of someone else's reviewed definitions. A use evaluation must fix
the model/data revision, identity, permissions, tool access and ground truth,
then test meaning, numerical answers, unknowns and evidence. Compare normalised
YAML, a documented RDF/Turtle profile and the reader representation using equal
information. Report token cost, task success and model behaviour separately.
One mapping or one model run cannot establish a universal format winner.

The reader's contract/regression tests and Northwind source-page checks are not
an LLM comprehension benchmark. No YAML-versus-Turtle quality result is claimed
in this implementation. RDF interchange still needs a defined vocabulary and
round-trip tests for identity, datatypes, lists, NULL, provenance, state and
execution bindings; it must not become a second editable SSOT.

## References

- [sudocode prompt runtime](https://github.com/sudoprivacy/sudocode/blob/main/rust/crates/runtime/src/prompt.rs)
- [sudocode host assembly](https://github.com/sudoprivacy/sudocode/blob/main/rust/crates/engine-host/src/prompt.rs)
- [OpenAI context and behaviour optimisation](https://developers.openai.com/api/docs/guides/optimizing-llm-accuracy)
- [OpenAI supervised fine-tuning](https://developers.openai.com/api/docs/guides/supervised-fine-tuning):
  as checked on 2026-10-15, the official page says the platform is winding down
  and is unavailable to new users. Do not make the corpus architecture depend
  on a particular training provider; verify account eligibility before a job.
- [RDF concepts](https://www.w3.org/TR/rdf-concepts/) and
  [Microsoft's documented RDF/XML subset](https://github.com/microsoft/Ontology-Playground#rdf-import--export).
