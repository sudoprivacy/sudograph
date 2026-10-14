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

## Where information belongs

| Information | Default destination | Authority and lifetime |
| --- | --- | --- |
| Source structure, names, identities, source SQL | Stable source context block | Registered source revision |
| Current meanings, rules, unresolved questions, relevant decision rationale | Versioned knowledge blocks | Checked model; preserve confirmation state |
| Addresses for full models, evidence, review and customer data gateways | Pointer block | Operator registers addresses; tool authenticates access |
| Source records and query results | Tool reads during the task | Snapshot/live-data distinction and result evidence remain explicit |
| Raw discussion and abandoned drafts | Collaboration history | Retrieved when investigating a decision, not automatically preloaded |
| Reviewed corrections and successful modelling/use trajectories | Candidate training/evaluation corpus | Curated, permissioned, versioned; not an authority for current facts |
| Task observations and reusable working techniques | Existing agent memory | Agent chooses what to retain; canonical references and revisions remain necessary |
| Authentication policy, credentials and server validation implementation | Server | No policy dump or credentials in prompts; tools report contracts and refusals |
| Temporary debug output, transient states and duplicate presentation text | Neither preload nor automatic training | Retain only when an investigation or explicit task needs it |

Not preloading information does not imply training on it. Dynamic discovery,
tool-result context, session history and persistent memory have different
lifetimes. Durable conclusions from a discussion belong in the model with their
evidence; raw conversation is not needed for every business answer. Useful
decision rationale must not be discarded merely because it originated in chat.

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
