# Reusing the Sudowork ontology host

Source inspection: Sudowork `dev` at
`c74f584ac999a5e8220f9ad2dbb15b70481adb22`, fetched on 2026-10-24.
This is an implementation design review, not a new Desktop/WebUI acceptance
result. Existing test sources were inspected; the Sudowork test suite was not
run as part of this read-only audit.

## What already exists

The host side of chat-to-ontology editing already has a substantial
implementation. The missing Sudograph adapter must extend these boundaries,
not build another conversation system, tool transport or workbench event bus.

| Capability | Existing source | Reuse and required change |
| --- | --- | --- |
| Workspace-scoped construction conversations | `packages/renderer/src/pages/ontology/studioConversation.ts`, `StudioConversationPanel.tsx` | Reuse creation, selection, duplicate-create coalescing and the existing ACP chat. Preserve explicit conversation binding for review events. |
| Persistent session ownership and recovery | `apps/desktop/src/process/bridge/ontologyAiBuilderBridge.ts`, `OntologyAiSessionRegistry.ts` | Reuse conversation ownership, idempotent registration and reaper cleanup. Workspace existence must resolve a registered model authority rather than require an editable legacy snapshot. |
| Per-session tool setup and restart | `OntologyMcpRegistration.ts`, `ontologyConversationRuntime.ts`, `AcpAgent.ts` | Reuse runtime preparation and fresh session tool configuration. Select tools/context from the server-owned project binding on creation and restore. |
| Scoped agent writes | `OntologyWriteBridge.ts`, `resources/ontology-builder-mcp/src/index.ts` | Reuse the authenticated tool boundary. Route Sudograph projects to the checked model writer; all legacy mutation routes must reject that authority. Ordinary model edits do not require GitLab approval. |
| Manual save, compare-and-swap and idempotency | `OntologyService.saveStudioModel`, `OntologyStudioDatabase.saveSnapshot` | Reuse the contract and conflict UX. The current persistence implementation reconciles RDF; do not use it as a second writable store for Sudograph YAML. |
| Changes refresh the UI | `workbenchChanged`, `OntologyStudio.onServerSnapshot` | Reuse host event transport and dirty-edit protection. Add an authority-aware revision/artifact event, rather than pretending a Sudograph model is a legacy RDF snapshot. |
| Check, locate and ask AI to repair | `StudioChecksPage`, `requestStudioAiRepair`, `OntologyStudio.onRepair` | Reuse controls and the bound conversation path; adapt compiler issue IDs/recovery. The current helper rejects busy conversations and chooses a default session: durable review delivery needs explicit bindings and inbox handling. |
| Version candidates and release UI | `StudioReleasePage`, `OntologyService.publishCurrentDraft` | Reuse useful history and inspection UX without a manual release gate on ordinary model editing. GitLab gates production source-change plans; the old model-publishing prototype remains optional. |
| Object/relation review | `OntologyEngine.reviewTarget` | A dedicated confirmation action is not required. Preserve real chat/comment agreement and target/revision/evidence; the legacy `local-user` label is not authenticated authorship. |
| Published-version agent registration | `getRegisteredAgentRuntime`, `OntologyAgentRegistry` | Reuse optional agent/skill registration and context injection hooks. Loading compiler knowledge into an arbitrary authorised agent must not require creating a new skill and registered assistant. |
| WebUI conversation/browser transport | `apps/webui/src/client/bridgeAdapter/mossAdapter.ts`, `ConversationCoordinator.ts` | Reuse authenticated sessions, locking, stream and browser lifecycle. Ontology channels have no WebUI mapping at this revision; they return `not-supported-on-web`. |

The active renderer ontology page uses Studio. The separate older
`packages/ontology-ai/src/OntologyAIBuilderPage.tsx` is not the right starting
point for a third parallel entry. Its existing-workspace shortcut also reopens
the newest conversation; that is a default navigation convenience, not a
review-event routing policy.

The current Desktop builder is scoped to a workspace, and the bridge rejects
builder approval, publication and business actions server-side. Runtime tokens
are pinned to a published version. These are implemented checks, not merely
prompt advice. Their loopback/per-launch credentials do not establish WebUI
tenant identity, revocation or row/field permissions.
Studio's save API carries `expectedRevision` and `operationId`; the older
incremental builder tool schemas do not carry a client base revision. The
existing database transaction guard is not proof that stale agent intent has
been checked across all entrances.

Evidence links:
[Studio conversation](https://github.com/sudoprivacy/sudowork/blob/c74f584ac999a5e8220f9ad2dbb15b70481adb22/packages/renderer/src/pages/ontology/studioConversation.ts),
[scoped write bridge](https://github.com/sudoprivacy/sudowork/blob/c74f584ac999a5e8220f9ad2dbb15b70481adb22/apps/desktop/src/process/services/ontology/OntologyWriteBridge.ts),
[transactional store](https://github.com/sudoprivacy/sudowork/blob/c74f584ac999a5e8220f9ad2dbb15b70481adb22/apps/desktop/src/process/services/ontology/OntologyStudioDatabase.ts),
[WebUI adapter](https://github.com/sudoprivacy/sudowork/blob/c74f584ac999a5e8220f9ad2dbb15b70481adb22/apps/webui/src/client/bridgeAdapter/mossAdapter.ts).

## Project authority is the integration switch

Extend the existing host project/session registry with an operator-owned model
authority reference. A Sudograph binding identifies the tenant/project, canonical
model, registered source handles and allowed operations. Git history is optional
storage/delivery, not a per-edit approval workflow. A legacy binding
retains its existing engine. Callers cannot change authority by supplying an
extra flag, namespace, source path or another workspace ID.

Resolve this binding in one shared host contract, with Desktop and WebUI
transport implementations. Enforce it at every write entrance: Studio saves,
legacy MCP, imports, asset-generated drafts, upserts and publish operations.
Hiding a tool or deleting a prompt does not prevent a legacy endpoint from
writing. Sudograph-managed projects must not have a writable RDF mirror.

The existing session table references `studio_workspaces`; creation and recovery
also check a legacy snapshot. Decouple host workspace/session bookkeeping from
the model payload. Do not create an empty RDF ontology merely to satisfy the
registry foreign key or recovery helper. Keep host metadata and model authority
references; load canonical model content through its provider.

Desktop can reuse the local runtime boundary. WebUI needs authenticated provider
routes and execution-side tool configuration through Moss/Nexus. Its current
`create-conversation` mapping forwards selected agent/skills/model, not the
ontology purpose, ID or Desktop MCP configuration. Copying an Electron loopback
URL or local Node/script path into a cloud session cannot supply that integration.

## Prompt replacement includes session restoration

The old AI Builder initial message and `presetContext` are not the only injection
points. Studio's `createStudioConversation` contains another construction
prompt; `prepareOntologyConversationRuntime` reinstalls construction/runtime
instructions and tools when preparing an ontology conversation.

For Sudograph projects, the authority resolver must select the actual managed
tools and compiler-produced context at all these points. Preserve the user's
business goal, conversation and source evidence. Detailed workflow reminders
must not become the enforcement mechanism. Legacy projects keep their current
runtime until explicitly migrated. This is a scoped provider substitution,
not global deletion of ontology functionality.

## Agreed editing and production boundaries

### Checked model edits update the review directly

Every effective model edit receives compiler checks and automatically regenerates
the authorised review graph from the canonical revision. Invalid inputs retain
the last usable graph and return repair diagnostics. Neither graph updates nor
read-only phase-three context consumption requires a GitLab merge request,
formal model release or human publication approval. Git may retain history in
the background. Semantic graph edits write the same model; generated HTML is
never an independent editing authority.

The existing `compiler.managed` GitLab model-publishing prototype is a tested,
optional delivery path and keeps its existing approval checks. It is not the
new default host writer. Reuse its pinned compiler/export verification where
useful, not its synchronous model-approval workflow. The new host authoring
adapter is still an implementation gap. Frozen acceptance baselines stay immutable.

Production source effects require the exact SQL/API/file change plan, validation,
GitLab review, operation authority and source preconditions at execution. The
existing model publisher is not that executor; source write-back is undeployed.

### Business agreement

A business person's comment and the agent's eventual agreement can establish
agreement about that discussed meaning. Explicit agreement in the bound chat is
also sufficient; the LLM interprets normal input without a new workflow prompt.
Disagreement continues in the same discussion. No separate confirmer role,
confirmation button or mandatory structured `confirmed` flag is required.

Preserve actual authorship, conversation/thread evidence, canonical targets,
revision and unresolved scope for traceability and context refresh. This is
derived provenance, not another authority or acceptance gate. A resolved thread
does not confirm unrelated definitions or authorise production execution. The
compiler's current blanket `unreviewed` presentation must be adapted during
integration rather than mistaken for a required product approval workflow.

### Phase-three context

Compile exact knowledge, stable references and authorised read pointers first.
The main conversation's LLM may then organise/compress this versioned packet.
Do not add an LLM compression call to every phase-one/two convergence step.
Retain exact critical definitions alongside the summary, validate references and
evaluate summary answers against the original packet. The summary is derived;
it cannot become another writable model or grant access. Only deterministic
context generation exists today; summary and runtime-refresh wiring remain work.

### Concurrency and delivery

Use a common checked submission contract carrying `base_revision`,
`operation_id`, intent and model input. Retry of the same operation/payload
returns the original receipt; reusing its ID with a different payload fails.
Three-way merge may combine changes to disjoint canonical definitions only after
revalidation. Incompatible edits to the same definition, deleted dependencies,
baseline changes and shared evidence changes return structured conflicts. Do
not ask an LLM to decide whether a stale overwrite is safe.

Reuse host session/inbox and event transport. Persist per-destination delivery
before ACK, deduplicate by event and binding, and recheck current permissions.
Busy sessions enqueue; they are not a reason to start another process or drop
the event. Resolve an explicit originating/subscribed conversation, never the
newest conversation as a fallback. The existing Studio repair helper alone is
not a durable external-comment receiver.

### Source baseline evolution

The current managed publisher registers one baseline and replays history against
it. Replacing it changes the required source pin, so old documents cannot be
replayed against that replacement. Production rescans and business-first
projects need immutable, registered catalogue revisions and a resolver for each
historical model's own pin. Archive schema/SQL/identity evidence; this does not
require copying all live records into every model revision.

A read-only compile check reproduced the boundary: the current Northwind
document compiles with its registered baseline; replacing only the baseline's
observation metadata makes historical compilation return `SOURCE_PIN`. This is
the current guard working as designed, and evidence that baseline evolution
needs an explicit catalogue resolver rather than replacing one global file.

Discover a new catalogue, compare it algorithmically, preserve registered source
identity and report impacted bindings. A source removal or rename does not
silently erase/reinterpret business definitions. Promote a compatible source pin
and model together after validation; otherwise retain the usable revision and
surface the migration gap. Empty business-first catalogues must explicitly say
that no source is connected, rather than claim complete database coverage.

Record reads identify source revision/observation time and snapshot capabilities.
Schema drift, an inaccessible source, unsupported consistency and mixed revisions
need explicit results. Do not substitute a frozen snapshot for live data without
reporting it or promise a global snapshot across unrelated providers.

### Private live review

Reuse the host principal and source gateway permissions. A GitLab credential
authorises fetching an artifact, and a ShareOne gate authorises opening a share;
neither substitutes for source row/field grants. View selection cannot grant
access. Current static snapshot acceptance is not live private-data acceptance.

Before connected review deployment, specify and test the viewer-to-gateway
identity exchange, origin/session handling, revocation and scoped model/data
responses. ShareOne currently supplies its anchor SDK inside hosted pages; the
same SDK is absent from a standalone local file. A self-hosted authenticated
reader must not silently lose stable comments, and a ShareOne iframe must not
receive reusable credentials embedded in its persistent HTML. Preserve the
review carrier choice already agreed; prove the identity/SDK integration as a
separate acceptance item. GitLab remote fetching alone does not close this gap.

## Implementation ownership and first acceptance

- Sudowork owns the shared project-authority contract, existing conversation and
  runtime resolver extensions, Desktop/WebUI provider adapters, source handles,
  event/inbox routing and review entry UX.
- Sudograph owns scanner coordination, source-catalogue pin/history handling,
  canonical YAML/registry checks, merge validation, compiler diagnostics,
  checked review artifacts, native renderer and context compilation.
- ShareOne retains hosted review/comments and durable events. The GitLab remote
  source request is separate from authenticated live-source reads.

The first complete adapter acceptance includes two users/conversations and
multiple review bindings, an invalid edit and repair, a compatible concurrent
merge and a same-definition conflict, a busy recipient/retry, session restore,
an unbound concept then a source connection/rescan, automatic review updates
without GitLab approval, scoped records/context and the actual Desktop/WebUI
comment journey. Accept the production source-change executor separately.
One-session or local native-browser checks are useful smoke tests, not that
complete acceptance. RDF conversion remains a low-priority interchange task.
