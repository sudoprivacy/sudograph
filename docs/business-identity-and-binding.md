# Business identity and pending source bindings

`sudograph-business-overlay/v5` separates a concept's identity from its source
mapping. A business meaning, metric, rule or question may use `targets: []`.
The compiler derives `binding_status: unbound`; authors cannot supply status,
IDs, identity reservations or business approval in YAML. Graph nodes and agent
context expose the same state. This permits a checked concept before discovery,
including against an empty source catalogue, without pretending phase one has
complete coverage. The registered baseline and its actual coverage remain explicit.

The existing purpose, provenance, quotation and version requirements remain.
Business rules/questions must still reference named business subjects. A pending
metric declares scope and has empty grain; once source targets are present, its
grain must reference actual source fields in those targets. Source-review
questions and source evidence still require source targets. A reference alone
does not make a definition executable, complete or business-confirmed.

## Identity authority

New IDs are deterministic hashes of namespace and the NFKC/case-normalised
canonical `concept`. Source targets, labels, YAML keys, language, roles and view
selections do not allocate identities. `concept` is the canonical identity key,
not a display label. Different concepts need different keys; synonyms cannot be
deduplicated from prose by this algorithm.

The operator-owned v2 registry reserves one ID per canonical concept and keeps
retired entries. Recreating a concept reuses that reservation. Adding/removing
or changing bindings modifies content, so the registry requires an incremented
version; it refuses stale versions and same-version edits. It also refuses
recreating the same concept under an ID computed from different source targets.
The managed writer uses the registry reconstructed from protected GitLab
history, never a registry supplied by an agent. Source databases stay read-only.

Compiled bundles carry the derived reservations necessary for reproducible
validation. A reservation is either the new namespace/concept hash or a checked
historical v4 hash with its original targets. Historical targets are immutable
identity anchors, not current source mappings. The renderer recomputes and
checks reservations; the managed writer additionally enforces the canonical
history. Editing a bundle is not an authorised registry migration.

## Existing projects

V4 remains readable with its original identity algorithm and nonempty-target
requirement. There is no automatic renumbering of an existing graph. To upgrade
a CLI project:

1. Compile its existing v4 YAML against its existing v1 registry once. This
   records checked legacy reservations in v2, without changing definition IDs
   or content versions. If retired entries are absent from that document, replay
   canonical model history rather than dropping the entries.
2. Change the overlay format to v5 and compile using that same registry. All
   reservations are reused. Format migration alone does not require a content
   version increment. Subsequent binding changes do.
3. Run the complete export checks and publish the newly generated artifact.

GitLab-managed projects reconstruct reservations while replaying accepted
history, including the historical v3 decoder. New v3 submissions remain refused.
CLI `--registry` selects the operator's ledger; creating an empty ledger is not
proof that an identity migration was authorised. The context/evaluation readers
use the same adjacent registry as the business compiler.

## Model change and publication

Business input may arrive in chat, documents or graph comments. The host routes
it to an agent, which edits the canonical structured model. The checked writer
validates every effective change and automatically compiles/renders its graph.
Invalid changes return concrete diagnostics and leave the last usable revision
in place. Valid edits do not require GitLab review or manual release approval.
They also determine agent-context content and its revision/digest. Git history
can be retained without becoming a synchronous business-editing gate.

This is not a watcher for each chat message or file keystroke. Messages that do
not modify the ontology and camera/layout interactions do not publish model
versions. The Sudowork chat/document/comment adapter and accepted-revision event
fanout still need integration. Existing GitLab model-publishing code remains an
optional checked delivery path. Production source writes require a separately
reviewed executable plan and authorised executor, which are not deployed.
Business agreement is established through discussion/chat, with provenance and
scope retained; no additional formal confirmation role or flag is required.
