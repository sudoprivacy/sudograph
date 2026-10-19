# Registered sources, checked scans and review navigation

This is the integration design agreed for detailed review on 2026-10-18.
The Sudograph reader implements bounded source navigation. The Sudowork
connector bridge, PostgreSQL/MySQL projection ports and automatic FDE onboarding
below are proposed work, not deployed capabilities.
The first integration preserves all existing Sudograph features and human/agent
workflows. In particular, its full SQLite projection is the reference baseline,
not functionality to replace with a host's bounded discovery sample.

## Repository boundary

| Repository | Owns | Integration boundary |
| --- | --- | --- |
| Sudowork | Source connection UX, workspace/source registration, scan progress and review launch | Its agent discovers registered sources and requests scans by opaque source ID. Reuse current probe, rescan and preview UX. The UI cannot declare coverage complete. |
| Sudocode | Agent lifecycle, tool discovery/execution, context loading and execution environment | Runs the Sudowork agent with versioned tools and capabilities. No parallel Sudograph agent framework. |
| Sudowork connector adapters | Database transport, credential resolution, introspection, source-side read-only query/record operations | Extend existing providers for PostgreSQL/MySQL; retain the working Sudograph SQLite scanner through the bridge. Expose required projection operations and unsupported capabilities explicitly. |
| Nexus | Deployed identity, permissions, Vault/VFS and suitable registered provider capabilities | Resolve secret references and authorised access server-side. Reuse actual registered drivers. Filesystem/object access does not imply relational semantics. |
| Sudograph | Projection/identity contract, deterministic checks, coverage proof, business compiler, model context, catalogue and renderer | Accept adapter evidence, reject incomplete claims, retain source facts and compile the checked revision. The existing SQLite implementation remains the reference; remote database ports must meet the same contract. |
| ai-dev-browser | Browser lifecycle, automation and display adapters | Used for browser-only sources or same-browser human takeover; not an obligatory transport for model editing or native review. |
| ShareOne or an authorised review deployment | Review URL, stable comments and hosting | Serves a compiled revision; not a second source catalogue, connection registry or permission authority. |

For the first adapter, keep its host-facing registration/tool code in Sudowork
beside the existing ontology service, and its model validation in Sudograph.
Sudowork consumes a pinned Sudograph package/CLI release with one owned compiler
service per project. The integration must not require cloning an unpinned source
tree at each tool call. A desktop worker and a cloud worker implement the same
contract; a cloud worker must not accidentally scan a desktop-only SQLite path.
Remote SQLite needs an authorised file/snapshot transfer or a local execution
worker, not a reinterpretation of a remote path as a local file.

The cloud plan places the frontend on a separate VM, uses central
`nexusd-cluster` for control, and runs `nexusd-cohost` with scode in each user's
execution pod. The worker runs in the authorised execution location or reaches
it through an existing service route. It receives scoped source/access handles;
the WebUI VM is not implicitly the database or Nexus endpoint. Actual network
reachability, tenant isolation and execution routing are integration acceptance
items, not established by this topology description.

The host adapter routes source registration/access into the existing projection
and managed compiler, returns coverage/revision/recovery, launches the native
review and supplies compiled context to the existing prompt loader. It does not
create a second model authority, renderer or editable RDF copy.

## Connection and scan state are different axes

Sudograph already has a deterministic SQLite scanner; the agent does not write
a new scanner for each project. `compiler.catalog.inventory` enumerates source
tables, database views, fields, keys, SQL and counts. `compiler.project` directly
writes and validates the phase-one YAML. The YAML contains bindings and source
pointers, not a copy of every record. `compiler.source_schema` compiles canonical
source identities and, with record export enabled, lossless paged snapshots,
including keyless view results and binary values. No LLM transformation is needed
between introspection and that YAML. Optional business interpretation is a
separate checked overlay.

The existing Northwind baseline covers all 13 user tables, 17 database views and
204 fields, with complete result snapshots. That proves the accepted source
projection contract for that database; it does not promise every SQLite system
object, arbitrary database engine or unsupported feature is represented. For
example, the current source authoring path refuses unsupported composite FK
bindings rather than inventing a relationship. Coverage is checked against an
explicit contract, scope and source observation; unsupported facts must remain
visible as limitations, not silently become a complete claim.

Sudowork's scanner is also deterministic. Its SQLite path is not governed by the
same `maxAssets` cap as PostgreSQL/MySQL. However, its asset fields and bounded
previews do not yet provide the same complete SQL/key/snapshot coverage receipt.
Compare providers against that receipt, not just the number of source types or
an asset-list length. Reuse provider transport and registration while preserving
the stronger existing SQLite projection path. A later consolidation is welcome
only after equivalent evidence and no capability regression.

Connection status is `unconfigured`, `probing`, `connected`, `unreachable`,
`unauthorised` or `unsupported`. It proves reachability and observed operations at
a time, not complete discovery. Credential references and connection status are
host-owned. If a user explicitly pastes credentials into chat, the agent can see
that input. Store them through the existing secret mechanism and then use
references; do not repeat them in generated prompts, summaries or artifacts.

Each scan is separately `queued`, `running`, `partial`, `complete`, `failed` or
`cancelled`, tied to the exact source registration, scope, capability version and
source observation. A previously complete scan can be stale while the connection
is still connected. An interrupted rescan does not erase the previous revision;
show both the last accepted revision and current scan state.

Coverage has independent dimensions:

| Dimension | Required evidence | Honest partial result |
| --- | --- | --- |
| Inventory | Exhausted object/schema pagination, exact authorised scope, excluded objects and reasons | A `maxAssets` limit, unresolved cursor, enumeration failure or unknown total |
| Structure | Every enumerated object's fields, declared keys, original view SQL, dependencies and per-object errors | Unsupported metadata or parse failure; preserve original SQL and the limitation |
| Records | For an offline full-record export: every included result row/field, counts and source revision evidence | Samples, truncated pages or unreadable fields remain partial |
| Consistency | Database-specific snapshot/transaction evidence, with start/end observations | Best-effort observations must not be labelled a consistent whole-database snapshot |

The scan validator derives these dimensions from adapter events and reconciled
manifests. Agent input such as `complete: true` or `approved: true` cannot promote
them. Product acceptance is a separate trusted event referencing the exact
manifest hash; a structurally complete scan is not business approval.

“Complete” always means complete within an explicit authorised scope. A requested
database-wide scan with excluded schemas/objects is partial for that request.
An intentionally smaller approved scope can be complete for that scope, with the
scope visible in the UI. Never disclose names/counts of inaccessible objects.
Unknown authorised totals stay unknown; zero observed objects is not proof of an
empty database when enumeration failed.

## Proposed provider and tool contract

The host registers `source_id`, source kind and execution location. Tools receive
that ID, a requested scope and a revision; they resolve credentials internally.
Sudowork uses the existing Sudocode/service Vault boundary for this access; this
integration does not introduce a second Nexus lifecycle or secret manager in the UI.
Providers report observed capability/version information for:

- `probe`, `enumerate_objects(cursor)`, `describe_object` and original SQL;
- declared primary/foreign keys and relation metadata;
- `begin_observation`, consistency/isolation semantics and completion evidence;
- bounded `read_records(object_id, cursor, fields)` and any supported read-only
  query operation, using server-side row/field policy before counts or joins;
- structured refusal/error, stable code, recovery hint and retryability.

Sudowork's agent discovers `sources.list`, requests a projection scan and watches
its receipt. These are proposed tool responsibilities; the final names/parameters
should be generated from their core implementation, not separately maintained
tool instructions. Sudograph receives normalised source-object/field evidence
and a coverage manifest, validates it and publishes a revision. Source relations
must carry declarations or SQL evidence; a guessed join goes through phase two.

Today, the connection form's probe calls `scanConnectorAssets` in the ontology
service, commits the resulting workbench snapshot and emits `workbenchChanged`.
This refreshes the UI; it is not an automatic chat turn. Snapshot/sample reads
exist in the builder MCP, but connector registration/probe is not currently an
exposed builder tool. First-version work must add the missing scoped operation
and bind scan events to the relevant agent session. Include only source ID,
revision, status, receipt pointer and recovery in that event. Persist it for an
idle session; avoid injecting full records or changing the stable prompt prefix.
The user should not have to copy a readiness message from the connection form.

The existing SQLite source identity includes its resolved path. Introducing a
registered remote identity requires an explicit identity migration mapping:
retain old object/field IDs and comment references, or produce a checked migration
receipt. Silently changing the identity algorithm would break references.
Connection display names, rotated passwords and UI ordering never create a new
source. Keep canonical `source_id` separate from a principal-scoped
`connection_id`/access handle. Two users reading the same registered database
reference the same object/field identities; permission filters do not clone those
facts. Registration deduplicates source identity using trusted execution location,
provider/database identity and explicitly verified endpoint aliases. Separately
deduplicate connection handles for the same source/principal/scope. Equal IP text
alone cannot prove identity across isolated networks/tenants, and secrets are
never identity inputs. Alias reconciliation or a real source move needs an
audited mapping rather than merging two sources on an agent's guess.

PostgreSQL and MySQL need separate provider acceptance. Record snapshot isolation,
pagination ordering, keyless results, views, generated columns, composite keys,
types, timezone/decimal/binary values and permission-limited enumeration all need
evidence. Do not promise a globally consistent snapshot across independent
databases. For large production databases, prefer complete structure plus
authorised live record paging; a sample must not masquerade as an offline full
record projection. The current Northwind offline record baseline stays intact.

## Chat onboarding and FDE intake

Basic chat connection of an explicitly supplied endpoint and credentials belongs
in the proposed first version, using the same registry/probe as the form. It is
not implemented by telling the user to fill in a second form. Preserve the full
SQLite scan and all existing coverage checks after registration succeeds.

The extended fast path accepts an unstructured endpoint list in one intake.
The agent normalises host/port/database candidates, sends credentials directly to
the host's existing secret storage, and receives secret references. Raw secrets
are excluded from chat summaries, logs, Git and model artifacts.

A deterministic discovery operation probes only the supplied/authorised targets
with bounded timeouts and read-only protocol handshakes. It reports observed
provider candidates and confidence/evidence. The agent resolves ambiguity or
missing input, selects an actually available connector and registers it through
the same deduplicating operation used by the connection form. Multiple matching
protocols remain candidates; no blind credential spraying or unrestricted subnet
scan is implied by an IP list. Connector install/pairing requirements remain
visible. Successful registrations can proceed directly into the requested scan;
each endpoint has an individual result and recovery path.

This is a second intake UX over one registration/scan pipeline. Human forms and
agent onboarding must not maintain separate connection stores or bypass policy.

## Human review and navigation

Both Desktop and WebUI open the native review URL in a local browser tab for
formal review. It renders locally, with native selectable text and comments. The
agent edits through model tools; human and agent reference the same revision and
canonical target IDs. Reuse Sudowork's remote viewer only when the human needs to
operate the exact execution browser. Independent native pages do not implicitly
share DOM state, camera position or an execution control lease.

Retain Sudograph compiler, ELK/Cytoscape renderer, stable comments, bilingual
catalogue, records and evaluation. Reuse Sudowork's source forms, scan job shell,
agent integration, capability status and review launch. Its React Flow graph is
not needed as a second renderer. Its asset descriptions are potential proposed
business annotations, not source facts. Retained RDF needs a separately checked
mapping; replacing its UI must not discard it or establish a second editable SSOT.

The shared reader combines named presentations and the searchable, lazily
expanded source/object/field tree in **Views and catalogue**. Its top level shows
the full authorised source-object graph; a source root shows that source's
objects. Object/field names select a bounded structural subgraph; disclosure
arrows expand the directory. SQL queries saved in the source are labelled
**Database views**, distinct from presentation views. SQLite has no invented
schema grouping. The active `Subgraph: <target>` and a visible bar report scope, omitted
objects, boundary relationships, hop distance and cap. A complete source view and
back navigation remain available. Source grouping uses declared FK/SQL edges,
not connector supply edges. Field drilldown and record paging reuse existing IDs.

The offline selector uses the compiler-generated parameter contract. Node tests
require the same results/refusals as the server selector for every catalogue
level, limits, distances and continuation. The host can reuse the same reader
module; its authenticated integration is a further deployment step. Navigation
is not authorisation: the client only receives the already-authorised model.
Reuse existing named-view identities and the server permission system. Different
principals may receive different fields/rows for one view. Scope is enforced
before counts, queries, joins and record reads; exports retain their separate
grant. The navigation menu presents permitted views and subgraphs only narrow
that authorised model. Do not clone facts per user or treat a menu choice as an
authorisation grant.

## Delivery and acceptance sequence

1. Review this boundary and the native catalogue/subgraph experience on the
   existing Northwind URL; all presentation changes come from shared app sources.
2. Add Sudowork's registered-source bridge and a real SQLite end-to-end journey:
   connect through either the form or basic chat intake, notify the agent, run
   the existing full scanner, compiler refusal/recovery, coverage receipt, open review, exact
   field comment, model edit, regenerate and revisit the same anchor.
3. Port PostgreSQL, then MySQL using real databases. Include capped discovery,
   permission-scoped counts, interruption/resume, source mutation, stale revisions
   and keyless/view result fixtures. No partial result is accepted as complete.
4. Add unstructured FDE intake using the exact same source registry and scan tools.
5. Accept a fresh-context agent's discovery and repair workflow. Keep this separate
   from unit/browser checks and from business-meaning evaluation.

The browser session design is an upstream dependency. Implementation and AI
production checks are recorded in Sudowork #1260 and its browser-sessions
document. User/device acceptance is still in progress. Those checks do not
establish a fully accepted browser experience, a production Sudograph host
adapter or physical phone support.
