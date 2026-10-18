# Registered sources, checked scans and review navigation

This is the integration design agreed for detailed review on 2026-10-18.
The Sudograph reader implements bounded source navigation. The Sudowork
connector bridge, PostgreSQL/MySQL projection ports and automatic FDE onboarding
below are proposed work, not deployed capabilities.

## Repository boundary

| Repository | Owns | Integration boundary |
| --- | --- | --- |
| Sudowork | Source connection UX, workspace/source registration, scan progress and review launch | Its agent discovers registered sources and requests scans by opaque source ID. Reuse current probe, rescan and preview UX. The UI cannot declare coverage complete. |
| Sudocode | Agent lifecycle, tool discovery/execution, context loading and execution environment | Runs the Sudowork agent with versioned tools and capabilities. No parallel Sudograph agent framework. |
| Sudowork connector adapters | Database transport, credential resolution, introspection, source-side read-only query/record operations | Extend the existing provider implementation; do not implement a second database connector in Sudograph. The bridge exposes the required projection operations and returns unsupported capabilities explicitly. |
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

## Connection and scan state are different axes

Connection status is `unconfigured`, `probing`, `connected`, `unreachable`,
`unauthorised` or `unsupported`. It proves reachability and observed operations at
a time, not complete discovery. Credential references and connection status are
host-owned; passwords never enter model YAML, HTML or prompts.

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

The existing SQLite source identity includes its resolved path. Introducing a
registered remote identity requires an explicit identity migration mapping:
retain old object/field IDs and comment references, or produce a checked migration
receipt. Silently changing the identity algorithm would break references.
Connection display names, rotated passwords and UI ordering never create a new
source. Host registration deduplicates equivalent endpoint/database/principal
scope using an opaque registry key; secrets themselves are not identifiers.

PostgreSQL and MySQL need separate provider acceptance. Record snapshot isolation,
pagination ordering, keyless results, views, generated columns, composite keys,
types, timezone/decimal/binary values and permission-limited enumeration all need
evidence. Do not promise a globally consistent snapshot across independent
databases. For large production databases, prefer complete structure plus
authorised live record paging; a sample must not masquerade as an offline full
record projection. The current Northwind offline record baseline stays intact.

## FDE onboarding from an unstructured list

The proposed fast path accepts endpoints and supplied credentials in one intake.
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

The shared reader now has a searchable, lazily expanded source/object/field
catalogue. Names select a bounded structural subgraph; disclosure arrows expand
the directory. SQLite has no invented schema grouping. The view menu identifies
the active `Subgraph: <target>`, and a visible bar reports object scope, omitted
objects, boundary relationships, hop distance and cap. A complete source view and
back navigation remain available. Source grouping uses declared FK/SQL edges,
not connector supply edges. Field drilldown and record paging reuse existing IDs.

The offline selector uses the compiler-generated parameter contract. Node tests
require the same results/refusals as the server selector for every catalogue
level, limits, distances and continuation. The host can reuse the same reader
module; its authenticated integration is a further deployment step. Navigation
is not authorisation: the client only receives the already-authorised model.

## Delivery and acceptance sequence

1. Review this boundary and the native catalogue/subgraph experience on the
   existing Northwind URL; all presentation changes come from shared app sources.
2. Add Sudowork's registered-source bridge and a real SQLite end-to-end journey:
   connect, scan, compiler refusal/recovery, coverage receipt, open review, exact
   field comment, model edit, regenerate and revisit the same anchor.
3. Port PostgreSQL, then MySQL using real databases. Include capped discovery,
   permission-scoped counts, interruption/resume, source mutation, stale revisions
   and keyless/view result fixtures. No partial result is accepted as complete.
4. Add unstructured FDE intake using the exact same source registry and scan tools.
5. Accept a fresh-context agent's discovery and repair workflow. Keep this separate
   from unit/browser checks and from business-meaning evaluation.

The browser session design is an upstream dependency. Existing production viewer
acceptance is recorded in Sudowork #1260 and its browser-sessions document. It
does not establish a production Sudograph host adapter or physical phone support.
