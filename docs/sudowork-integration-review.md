# Sudowork integration: feature and experience review

This is a proposed first-version boundary, inspected on 2026-10-18. It does not
claim that the cross-repository integration has been implemented or deployed.
The source-graph selector and renderer fixes described below are Sudograph
capabilities; they do not establish a working Sudowork adapter.

The [navigation and responsibility contract](review-navigation-contract.md)
defines what fresh source projects generate, what business authors still decide,
and which integration work is independent of browser release completion.
The [bound-session and event contract](review-session-events.md) specifies
conversation binding, notification delivery and browser acceptance. Local
session identities and per-turn progress do not belong in this design.

The first integration must preserve **100% of existing Sudograph capabilities
and human/agent workflows**. Sudograph deliberately developed part of the
workflow in depth. Reuse the host around those capabilities, and compare against
the working Sudograph baseline before replacing any corresponding host feature.
The inventory below is an acceptance floor, not permission to remove an unlisted
working capability.

The responsibility split is agreed; the full production design is not yet
specified. The [remaining adapter boundaries](#remaining-adapter-design-boundaries)
distinguish missing interface decisions from capabilities that need actual
cross-repository/device acceptance.

## Existing implementation evidence

Sudowork `origin/dev` was inspected at
`36cecb4fb256e64428ac4dc94b55df28d38746cc`, without changing its checkout.

- `StudioDatabaseConnection.tsx` has PostgreSQL, MySQL and SQLite connection
  forms, a SQLite file picker and a probe operation. `StudioDataPage` lists
  connections/assets, rescans them and opens previews. Reuse that entry UX.
- `OntologyService.ts` has database/file/API adapters. Some discovery paths have
  `maxAssets` limits and record previews are bounded. A successful probe or a
  sample is not proof of Sudograph's complete authorised-source coverage.
  The current probe already runs `scanConnectorAssets`, updates the workbench
  snapshot and emits `workbenchChanged`. That UI event does not automatically
  start a chat turn. The builder MCP exposes snapshot/sample reads but currently
  has no connector-registration/probe tool.
- `StudioModelEditor.tsx` uses React Flow, with graph and structure modes; it is
  not simply Microsoft's application embedded in a tab. RDF document retention
  and the graph editor are separate concerns. Replacing a renderer must not drop
  retained statements or silently transfer model authority.
- `BrowserPanel.tsx` uses the shared `BrowserSessionPanel`. The latter already
  opens an authenticated viewer window/tab for the same execution browser.
  Relevant commits include `5783843e` (shared Desktop sessions and handoff) and
  `36de4f0f` (external-viewer acceptance), followed by PR #1260 documentation.
- `docs/sudowork-browser-sessions.md` distinguishes local standalone CDP,
  managed extension and cloud sessions. Existing personal Chrome attachment
  and optional WebUI-to-local-extension relay are still listed as planned.
  Do not claim that a managed extension proves arbitrary personal-profile access.
  Upstream implementation and AI production checks do not establish product-owner
  acceptance. Physical phone/takeover/input acceptance remains in progress.

Nexus VFS local source at `e8713a3ef` contains local/remote/S3/GCS driver wiring
and additional API transport modules. Modules, compiled features, registered
drivers and deployed capabilities are different states. Discover the actual
deployment before offering a connector. A file/object driver does not by itself
provide relational keys, original view SQL, query semantics or schema coverage.

## Feature and UX ownership proposal

| Feature | Human experience | Agent experience | Proposed owner / disposition |
| --- | --- | --- | --- |
| Connect a database | Existing source-type form, credential flow, probe and connection status | Discover registered source IDs and capabilities; never reconstruct credentials in prompts | Reuse Sudowork UI and its database adapters; expose capability gaps explicitly |
| Connect files, object storage or APIs | Same source entry with provider-specific setup and visible status | Operate on authorised handles and capability contracts | Reuse Nexus drivers where deployed; retain a source-specific adapter when relational semantics are needed |
| Browser-only sources | Login/consent and human takeover through existing browser UX | ai-dev-browser through the host's authenticated session and control lease | Browser fallback for supported tasks; extraction retains URL/time/evidence and does not become a fictitious SQL source |
| Discover source structure | Clear scan scope, progress, exclusions and failure/partial state | Deterministic source objects/fields/SQL/relations and machine-readable coverage | Preserve the existing complete SQLite scanner and coverage validator; extend host providers to satisfy the same contract |
| Browse objects and fields | Unified views/catalogue; full source roots and bounded object/field subgraphs | Current canonical IDs plus a bounded structural selector | Preserve Sudograph navigation; host embedding must use the same model and selection contract |
| Read real records | Same-row fields and keys, small samples, complete pagination when authorised | Snapshot/live distinction, versioned record reads and evidence | Preserve Sudograph behaviour; host adapters provide access without a second editable data store |
| Review graph | Large canvas, field drilldown, selected-object details and presentation views | Canonical model reads; browser used when visual inspection is necessary | Replace the corresponding review experience, not just add another independent model editor |
| Comment | Stable object/field anchors, readable text selection, preserved threads | Read/reply with stance and workflow state; changes return to the checked model | Preserve Sudograph + ShareOne review behaviour |
| Edit and repair | See proposed changes, provenance, unresolved questions and validation errors | Submit model changes; compiler refuses invalid structure and gives recovery | Sudograph compiler/publisher contract; host routes tools through it |
| Version and approve | Authenticated reviewer, exact revision, source evidence and separate business confirmation | Cannot self-approve by setting a YAML/UI field | Choose one review authority per event; map existing host records explicitly |
| Launch business agent | Existing host conversation and agent lifecycle | Version-pinned compiled context plus authorised pointers/tools | Reuse Sudowork runtime and registration; add the Sudograph model adapter |
| Evaluate | One evaluation entry separates calculation self-checks from source questions; coverage is an inventory | Source questions and private, pinned judge; business-meaning tests added separately | Preserve Sudograph question generation and independent grading |
| Permissions and views | Existing named views, source/business separation and authorised record visibility | Scoped reads, counts, queries and separate export grants | Preserve Sudograph's server enforcement; subgraph/menu selection never grants access |
| Managed delivery | Traceable regeneration, review and publication of an exact revision | Compiler recovery, generated-export guard and managed GitLab checks | Preserve existing Sudograph harness and delivery gates, including context compilation and pointers |

Choosing to reuse a form does not choose the underlying model authority. For a
Sudograph-managed project, source systems own source facts and checked model/Git
owns business definitions. Sudowork stores host/session/UI state and references
the checked revision. Retained RDF must be mapped, kept as immutable evidence or
refused explicitly; do not silently discard it or dual-write editable definitions.

## Connector contract to align before implementation

The detailed [registered-source and scan contract](source-connection-and-scan-contract.md)
now specifies repository ownership, the host-agent workflow, independent
connection/scan/coverage states, provider operations, snapshot evidence, identity
migration and the proposed FDE intake. These connector integrations remain planned.

Use one connection entry and credential flow. Each registered source should
report the capabilities actually available: schema enumeration and pagination,
declared keys/relations, original database-view SQL, record paging, read-only
access, revision/snapshot strategy and authorised scope. These are proposed
adapter fields, not a declaration that every provider currently implements them.

Connection credentials remain with the host/provider after intake. If the user
explicitly supplies a password in chat, the model may see that input; do not claim
otherwise. Register it through the existing secret boundary, then use references
without echoing it into artifacts, logs or summaries. Basic chat onboarding of
an explicitly supplied endpoint is part of the proposed first version, using the
same registry/probe as the form. Bulk ambiguous-source discovery is a further
extension. Neither registration path is wired to Sudograph yet.

An agent receives a
registered source identity, available operations, observable status and typed
recovery. Do not turn an arbitrary browser extraction into database coverage or
use a capped asset list to claim a full scan. Sudograph's current source scanner
is SQLite-only; reusing the PostgreSQL/MySQL form does not complete those ports.
Do not replace that complete scanner with a capped asset probe. Extend existing
PostgreSQL/MySQL providers for exhausted pagination and coverage receipts; simply
removing a query limit does not establish completeness.

The host adapter is thin routing and registration code: registered source/access
handle and execution location into the existing scan/compiler harness; checked
model revision into the native reader and existing prompt builder; canonical
target IDs back into host navigation. It does not create a second ontology,
renderer, credential store or editable RDF representation.

The deployment separates the frontend, Nexus control plane and execution worker.
Do not assume a cluster/cohost inside each user pod. The inspected Moss K8s
backend requires external Nexus and supervises pod scode through it. Place the worker
where the authorised source is reachable and route through existing services.
Never interpret a pod or desktop SQLite path on the WebUI VM. Network routing,
tenant isolation and the deployed adapter still require end-to-end acceptance.

## Display surfaces: first-version recommendation

| Surface | Benefit | Limit | Proposed first-version role |
| --- | --- | --- | --- |
| Standalone browser window/tab | Large canvas outside the small ontology tab | Local native rendering and remote viewer transport have different interaction limits | Primary surface: actual Chrome on Desktop, authenticated execution-browser viewer on WebUI |
| Direct review URL in a local browser | Direct text selection, comments and normal browser interaction | Shares model/anchor identities, not automatically an execution DOM or control lease | Independent review/share route; not a substitute for same-browser acceptance |
| Shared Sudowork BrowserPanel | Conversation and browser together; existing authenticated session/handoff | Smaller canvas, viewer transport latency, remote selection/clipboard must be accepted | Companion for agent browser activity; offer the existing external viewer when more space is needed |
| Existing ontology graph tab | No new navigation surface | Current editor/model semantics and canvas size differ | Keep a review entry/summary; replace corresponding review functionality after the adapter is agreed |

A native local tab opening the review URL renders the page locally. A new tab
opening the authenticated browser viewer displays the execution browser remotely.
They are different experiences even when both use a browser tab. The independent
viewer is the WebUI execution-browser route. Selection, comments, clipboard and latency must be accepted
on the actual viewer, not inferred from a local URL test.

Desktop retains a separate Chrome/CDP window and attachment to personal Chrome
through extension. Direct review without agent control still needs no extension.
WebUI uses the authenticated independent viewer for the same cloud execution
browser, reusing its session/lease. It can retain both cloud extension and CDP;
those are control transports, not a choice between current and old browser
binaries. Different transport/device combinations require separate evidence;
accepting one does not establish every additional extension or phone path.

Business review must not require extra Return to AI / Return to human buttons.
The existing browser protocol still enforces write exclusion and operation
epochs. Adapt that protocol to bound chat/comment/model events rather than
placing workflow instructions in a prompt. Reuse the existing conversation
registry and durable inbox as described in the session/event contract.

Do not automatically publish customer data to a public service merely to open
a large view. Use an authorised review deployment or an explicitly permitted
snapshot. ShareOne is the review carrier, not the canonical model or ACL engine.

## Catalogue and subgraphs

Design the navigation for both hosts. Source, schema where available, object and
field entries are selectable. Selection and expansion are separate actions.
The unified **Views and catalogue** lists existing named views above the source
tree. Its top level shows the complete authorised source-object graph; a source
root shows all its source objects. Object selection gives a bounded neighbourhood;
field selection also focuses its parent and field references. Directory arrows
expand children without changing the canvas. Whole-source structure does not
eagerly expand every field or load every record into the canvas. Large-source
scaling may require another explicit overview mode, not a silently truncated
result under a full-source label. Label source SQL views **Database views** to
distinguish them from presentation views.

The upper **Review views** list is task-based navigation, not a popularity ranking
or a sample of database objects. The standard source projection and conditional
source-review entry come from shared infrastructure; phase-two views come from
checked subjects and declared dependencies, with optional custom view lists.
Default subject/question selections are algorithmic. The lower source catalogue enumerates
objects/fields from the authorised model. Both reference the same identities.

The core selector now uses weak components followed by bounded undirected BFS
over declared foreign keys and source SQL dependencies. It excludes the common
source-connector star and returns canonical IDs, scope/boundary counts and
continuation parameters. Its contract is derived from the same parameter model
used for validation. The existing context reader and authenticated transport
expose it. The shared native reader now implements a searchable, lazily expanded
catalogue, bounded source subgraphs, scope/boundary counts, distance/cap controls,
back navigation and a distinctly labelled active subgraph. Its offline
transport is checked against the server selector. Sudowork host integration is
not yet deployed.

LLMs can name/explain a selected group and propose additional business links
through phase two. They cannot supply invented edges, approval flags or arbitrary
SQL to the selector. A structural group is not a confirmed business domain.
Permissions apply before selection; counts must never reveal unauthorised objects.

## Acceptance before replacing the old experience

1. Connect and rescan through the existing source UX; preserve identity and
   show partial/failed discovery honestly. Port and accept each database separately.
2. Open a selected object/field in a large review surface; the same identity and
   model revision work in the host and standalone page.
3. Read samples and page records with keys/NULLs intact. Enforce access and stale
   revision checks server-side; no credentials or hidden objects in exported packets.
4. Comment, change view/language, expand fields and revisit the thread. The target
   remains the same; resolve workflow never substitutes for business approval.
5. Submit an invalid edit and repair it using the returned compiler error.
   Publication requires the selected trusted approval process and exact revision.
6. Inspect real graph geometry after layout. Overlapping fCoSE results fall back
   to ELK with a visible notice; dragging and zooming do not rerun layout.
7. Compare native-page and BrowserPanel selection, comments, clipboard, pan/zoom,
   canvas area and takeover. A narrower viewport alone is not a phone benchmark.
8. Fetch versioned context, browse a bounded subgraph and find evaluation questions
   with a fresh agent. Keep actual LLM scores separate from preparation/unit tests.

## Replacement of the legacy builder prompts

The inspected Ontology AI Builder builds both an initial conversation message
and an `extra.presetContext`. The latter repeats a ten-step workflow and lists
legacy write tools. For a Sudograph-managed project, retire both templates when
the corresponding entry is replaced. Preserve the user's business goal, existing
conversation lifecycle, project/source binding and useful host UX. The replacement
discovers scoped tools through actual contracts and loads checked business
knowledge through the model adapter.

Removing a prompt is not a write guard. The bound project must expose the managed
write/publish authority, reject stale revisions and self-approval, and prevent
parallel writes to a legacy ontology store. Existing unrelated legacy projects
keep their current runtime until an explicit migration is accepted. Do not remove
their tools globally or silently reinterpret RDF as a Sudograph definition.

## Remaining adapter design boundaries

Responsibilities, SSOT, the standalone route, deterministic compilation and
reuse of existing agent/browser/notification layers are agreed. The product
also supports multiple people, conversations, review shares and downstream
agents over one canonical model; there is no single maintenance-session limit.
Complete authorised structure plus on-demand records is the common connected
default, independent of whether the deployment is a demo or customer system.
These requirements are not a complete production interface specification.

### Business-first and source-first modelling

Both directions refine the same ontology. Source-first discovery supplies
observed fields/records for business review. Business-first intake turns supplied
conversation, prompts and documents into versioned candidate concepts, rules,
questions and evidence; source mappings can follow later. Business narratives
are domain input. Parser, identity, permission and publication rules stay in
code rather than being replaced by a workflow prompt.

The v5 compiler/registry now supports pending business concepts and stable late
binding, retaining existing IDs through checked legacy reservations. The graph
and context reader expose an unbound status; source-review questions still need
actual source IDs. See the [identity contract](business-identity-and-binding.md).
Collect host conversation evidence
through an authenticated intake reference, not by inventing an HTTPS citation.

Business confirmation concerns the meaning of a model definition. Editing or
reviewing that meaning publishes model changes; it does not commit anything to
the raw database. Its precise review UX still needs agreement, without assuming
a separate mandatory approval workflow. Source corrections use their own
explicitly authorised write path.

Every submitted model revision enters the managed compile/CI/render path;
invalid changes return repair diagnostics and leave the previous published graph
in place. A valid proposal produces derived artifacts automatically, while
publication follows the existing GitLab gate. Chat text, a comment by itself,
and camera changes are not model commits. The host chat/comment-to-proposal
adapter is still an integration deliverable. Review graphs and agent context
must reference the same accepted revision, without manual HTML edits.

GitLab owns model YAML and revision history; a ShareOne remote source would
point at the generated HTML artifact. ShareOne's current fetch whitelist does
not support GitLab or private repository credentials. This is a separate
hosting integration, tracked in the [GitLab remote-source request](shareone-gitlab-remote-source-fr.md).

### Adapter interfaces

The remaining engineering contracts and product details are:

| Boundary | What still needs a concrete specification | Recommended starting point |
| --- | --- | --- |
| Scanner/provider wire contract | Versioned request/result schemas, exact type/SQL/key representation, observation tokens, cancellation/resume and capability equivalence across Python and host providers | One coordinator, batched provider operations, explicit unsupported/partial results; prove SQLite first, then port each provider against the same receipt |
| Source identity, execution and permissions | Path-based identity migration, trusted source aliases, credential/access handles, host principal to project/row/field grants, worker packaging and reachable execution placement | Reuse registered identity/secret/permission services; preserve existing canonical IDs through a checked mapping and pin the compiler package; never infer execution location from a UI URL |
| Business confirmation | How agreement about definition meaning is captured, who may record it, and which version/evidence it covers | Preserve review state and evidence; separate ontology changes, GitLab revision review, comment resolution and raw database writes; do not assume an additional per-edit approval process |
| Concurrent sessions, shares and events | Base-revision checks, compatible edit merging, same-definition conflict results, subscription routing, ACK/idempotency and active-session delivery | Support multiple bindings to one canonical model from the first adapter contract; durably enqueue per destination and never start a second process over an active conversation |
| YAML/RDF interchange | Explicit vocabulary and reversible mapping for identities, versions, definitions, evidence and review state | Low-priority bidirectional converter for the checked semantic model; prove model-to-RDF-to-model fidelity; retain unsupported external statements or refuse them explicitly |
| Browser review lifecycle | Accept actual graph/comment behavior over the upstream conversation-control protocol, including continuous interaction and devices | Reuse ordinary conversation continuation and the input barrier; no mandatory business handoff buttons; keep real graph latency and physical-device acceptance separate |

End-to-end facts still require acceptance even after these interfaces are
specified: authenticated principal/scoped reads, real remote selection/comment/
clipboard/IME, large-graph interaction latency, device support, event crash/retry,
and each database's consistent observation and complete coverage. Measure local
UI work separately from frame transport/network delay before setting a supported
performance budget. No production/device result follows from a local viewport
or a source-code audit.

The recommended first implementation slice is one registered SQLite source,
managed project, conversation and standalone browser. Exercise connect through
the existing form/basic chat entry, full scan, compiler rejection/repair, review,
comment delivery, checked publication and versioned context read. Then extend
the same contracts to PostgreSQL/MySQL and other deployments. A one-conversation
smoke fixture is only a test simplification; multi-user/multi-conversation and
multi-share concurrency must be accepted before the first adapter is complete.
The first product release preserves the agreed Sudograph capability floor.

YAML/RDF conversion is the general interchange capability; migrating an existing
workspace adds identity mapping, authority and history handling around it. Keep
that migration low priority unless an actual project requires it. Defining our
own RDF vocabulary can preserve all supported model fields; arbitrary third-party
RDF must not be advertised as automatically understood or losslessly converted
without a supported mapping. Conversion never creates a second editable SSOT.
