# Source review and authorised graph interfaces

These are usage contracts. Design decisions remain in the design page linked by README.

## Source coverage and records

Use `compiler.catalog.scan(dsn, base)` before modelling. It inventories all tables,
views (including empty ones), columns, primary keys, foreign keys and row counts.
Set `raw.<source>.coverage: complete` to make loading refuse uncovered tables,
columns or foreign keys. `exclude` maps an exact source object or `table.column`
to a nonempty reason; exclusions remain visible in the graph. This proves the
inventory is accounted for, not that the business interpretation is correct.

`types.<type>.display` names the property shown as a record label. Identity always
remains the checked single or composite key. No implicit monetary totals are
invented by grouping.

`python -m compiler.cli examples/northwind.yaml --app northwind.html --records`
exports compressed, paginated records. A portable export contains every record
included in that export and cannot be revoked. It must not contain data its
recipients are forbidden to read. Without `--records`, the app clearly reports
that record pages are not included. `compiler.browse.page` serves bounded pages
from the source with stable key ordering; it never requires loading the full
table into a graph.

Cytoscape 3.30.2 renders the active graph, with ELK layered or fCoSE and DOM labels for text
selection. The ShareOne application-anchor protocol supplies canvas node bounds.
Source rows are paged separately: a large database does not imply placing all its
rows on one canvas. No million-node rendering performance claim has been made.

Business-mode views start with source connectors folded out of the canvas and
edge labels shown around a selected node. Source provenance remains in each
type's details; `Show sources` restores its nodes and edges. `Focus neighbors`
shows one hop around a selected object; `Full graph` restores the overview.
Neither control changes the compiled model or access permissions. The default is
ELK layered with its own orthogonal edge routes, including bends and endpoints.
Cytoscape keeps a curved self-loop for self-relations. fCoSE is an optional
comparison: it uses relative placement constraints from the acyclic ordering
and straight ordinary edges as in the official demo,
but the tested configurations still have some edges crossing nodes. The metrics
overview limits layers to four nodes with Coffman-Graham layering so fan-out
does not put every measure on one long row. Dense views still need zoom or focus
for reading. ELK offers
left-to-right and top-to-bottom layouts; `Rearrange` discards manual placement
for the current view. Dragging node borders moves their text and attached edges.
Placements survive projection/focus/language switches during the current page
session; they are not saved to the server or across a reload.

The template includes a Chinese/English selector. Controls, legend and panels
switch together without changing graph identities or coordinates. Business
names, authored descriptions and property names use the spec's `translations`
catalogue. Keys are original display text, values are translated display text:
`translations: {en: {Customer: Customer, Sales: Revenue}}`. A declared locale
must cover the ontology name, all node/type/source/hook labels, descriptions,
resolution criteria and property display names; the compiler rejects incomplete
catalogues before binding rows. IDs, refs, formulas and source values stay stable.
Legacy specs without a business catalogue retain original business text. Missing
template translations fail rendering rather than silently falling back.

`Data projection` and `Metrics and rules` are display choices, not workflow
stages. Node colours describe kinds and unresolved upstream gaps; they do not
encode stage, permission or a claim that a business definition is correct.
`mode: source_projection` rejects authored rows, business formulas, gaps and
undeclared relationships in every spec load. `compiler.project` generates and
requires this contract. Operators can pin it independently of author-editable
YAML with `compiler.cli --mode source_projection` or a registered view's
`expected_mode: source_projection`; changing or deleting the YAML mode refuses.
`examples/northwind.yaml` uses this source contract. Draft interpretations are
kept separately in `examples/northwind-business.yaml`; they are not confirmed
business policy. A display selector never selects a workflow contract.
The [draft provenance](../examples/northwind-business.provenance.md) separates
stored upstream formulas from the agent's rounding, scope and workflow proposals.

For public delivery, `compiler.cli --app graph.html --records --lang en --pack-html`
and corresponding `compiler.project` flags generate an English presentation with
lossless gzip packaging of the whole native HTML. The reader unpacks locally
before rendering; it does not fetch source data or recalculate metrics. Native
contracts are validated before packaging. `compiler.html_export.unpack` and the
baseline checker inspect the same model and records as a plain export.

Node text selects details; explicit `+`/`×` controls expand/collapse records or
fields. Wheels over selectable labels use the same zoom rule as the canvas.
Source snapshots live in the document head, outside body text anchoring scans;
all records remain available. Neither comments nor repeated text scanning should
scale with the byte size of the data snapshot.

### Field-first source review

The native phase-one bundle always includes `source_schema`, generated by the
compiler from the read-only source, including keyless tables/views and binary
columns. This is independent of the authored business-object bindings. The
default `Structure relationships` graph expands source objects into fields.
Collapsed objects connect at their containers; expanding them exposes declared
FK field endpoints in the same presentation. The formerly separate object/field
menus duplicated the collapsed state and are consolidated. A source-object
selector shows tables, views, or both. Existing record projections remain available.
Compiler-owned source identities appear as data-source nodes in both phase-one
presentations. They are shown by default and can be hidden with the source
control; provenance edges derive from the source catalogue and checked field
bindings, without a second mapping registry. Public source details report a
snapshot's provenance and do not publish connection configuration or assert a
live connection state.

The renderer measures container headers across languages and reserves the same
padding in ELK and Cytoscape. Bounded DOM edge labels remain selectable, with
positions chosen to avoid node bodies, container headers and other edge labels.
Placement is recomputed on selection/drag; pan/zoom only transforms the labels.
Narrow gaps can use captions wrapped to a measured height. If there is no clear
position, the label stays available in relationship details. The reader reports
the omitted label count even when only selected relationships are named. This
does not promise legibility for arbitrarily dense or manually overlapping layouts.
The shared Back control restores presentation, selected node/relation, expansion,
focus, record page, camera and panel scroll; language preference is kept.
Clicking empty canvas clears selection and restores the overview panel without
running layout again. Source-object and source-field text selections both use
app-declared identities; legacy text-only comments cannot be safely relabelled as
known hidden identities without a mapping or a confirmed migration.

Source view SQL is preserved verbatim. SQLGlot identifies source dependencies
with scope resolution; these object edges do not claim complete field lineage or
invent view foreign keys. Parse failures remain explicit.

`--records` also streams every source object into compressed source-record pages.
NULL and duplicate keyless rows remain unchanged. Binary values use lossless
base64 with byte count and SHA256, and can be downloaded from record details.
The `dictionary-u32le-segments/v1` format stores a typed value dictionary per
source and gzip-compressed column segments. Identical column pages share bytes;
row positions and multiplicity remain intact. Each segment declares its byte
encoding (`u32le`, `byteplane`, or `delta-byteplane`); decoding only reverses
compression and dictionary references. Integers outside JavaScript's exact
range and nonfinite floats use explicit string envelopes. Record pages decode
lazily with bounded caches. Historical record anchors reuse primary-key column
segments rather than exporting a second copy of all record identities.
Keyless rows have positions within that export, never fabricated business keys.
One source read transaction covers its catalogue, counts and source snapshots;
this is not a transaction spanning sources or separately compiled business views.

`source-object-field/v1` IDs are generated, not authored: the canonical SQLite
connection path identifies the source, escaped source object/column names its
objects/fields. Ontology aliases, labels, translations, layout and changing data
do not participate. Source relocation or physical object/column renaming requires
an identity migration. Bound phase-two and authorised properties receive the
same IDs in `groups[].field_ids`.

Identity names are definitions, not per-view allocations. Loading rejects
duplicate explicit YAML keys, including nested properties, with both locations;
YAML merge defaults remain supported. Graph identities cannot be reused across
`raw`, `hooks`, `types` and `nodes`. References and the same property name under
different types are valid. New business definitions should be looked up in the
canonical identity index and created only when no definition exists; reuse the
identity across views, comments, policy and versions. Changing a definition must
create a content version, not another identity. Immutable lifecycle/migrations
are next-stage work; current spec keys and collision checks cannot determine
whether two differently named business meanings are actually the same concept.

Rendering refuses a phase-one bundle without this contract, duplicate IDs,
substituted field IDs or missing field inventory/record chunks. YAML cannot
substitute a source-schema manifest. Field comments use ShareOne's `app_declared`
IDs from `Comment on field` and text selection on a field label; ordinary node
clicks inspect details. Hidden fields retain known IDs and comment reveal expands
their source object. Historical text comments retain text-anchor semantics.
Object identities address the whole source table/view; field identities address
individual source columns for comments, source navigation and phase-two rule
references. Neither is a record key or an authorisation credential. Records with
declared keys use those full keys; keyless snapshot positions have no identity
promise across exports. Reader-created relation anchors derive from canonical
endpoints and relation kind, independent of edge numbering, placement or language.

The complete source catalogue/snapshot is not automatically attached to
Gateway's permission-limited views. Those keep their registered properties, row
scope and generated field IDs; source-wide discovery remains unavailable.

## Server-side visibility

Use **View** for a named projection of the shared model. Reuse source and
business identities, definition references, graph selection, pagination, focus
and anchor mechanics across presentation and authorised scopes. The target
View definition supplies both the renderer and server projection; policy grants
refer to that same view identity. Its effective selection is restricted on the
server by the caller's policy before records, counts, aggregates or graph objects
are sent. The existing Gateway registry and reader selectors still have separate
descriptors; a unified, versioned registry is next-stage work. Distinguish
**graph view**, database **source view**, and server **authorised view** when
needed. The shared reader selector says **View**, not **Show**.

Presentation and authorisation are different dimensions of that system. Phase-two definitions,
metrics and rules should have separately named business presentations, while
phase-one source presentations remain free of authored business definitions.
Preserving the accepted source artifact/version is a baseline requirement; a
menu choice alone does not preserve a historical snapshot. The combined reader
and versioned overlays are next-stage design, not current Gateway capabilities.
Adding a business rule does not require another selector entry or another copy
of source facts. An authorised server view defines which objects, fields, records and
definitions may be returned. The reader then chooses an available presentation
of that authorised graph. Policy can also restrict which presentations are
offered, but one presentation may still contain different data for two readers.
Menu filtering alone never provides data security. The public ShareOne snapshot
does not implement identity-based view discovery or deployed Nexus login.

`compiler.gateway.Gateway` takes **operator-registered** views and a mandatory
authority. View definitions and authority policy are outside agent-editable
ontology YAML. A view registers a projection spec, optional basis and optional
dimension slice. Its spec must contain only the properties, objects, formulas
and sources that members of that view may inspect. The same source can have
several projections. Slices reach backing reads before counts, sampling,
aggregates and relationship traversal.

Every graph, query, page and export request reauthorises the credential. Export
requires a separate `export` grant. Discovery returns only authorised view names;
the caller cannot supply a spec path, basis, source connection or policy. No
source-wide coverage report or connector credential is returned. A browser
projection selector is presentation, never the permission boundary.

The authorised graph can reuse the renderer's filtering, pagination, focus and
identity anchors. Authorisation must filter source reads and returned graph
objects on the server first. Do not reuse client-side show/hide as enforcement,
or send inaccessible identities merely to display that something is hidden.
Stage-two metrics and rules can use the same renderer and stable identities,
with bounded drill-down; their policy and calculation contract remain explicit.

`NexusAuthority(client, grant_paths)` uses the **caller's credential** to read an
operator-owned grant resource through the official client's typed Read RPC.
ReadResponse supplies bytes, not a subject. The sealed operator grant therefore
binds a credential digest to a subject:
`{"resource":"view/a","subject":"alice","credential_sha256":"<SHA-256>","actions":["read"]}`.
A missing grant, mismatch, denied read or unavailable backend denies access.
Install `npm ci --prefix nexus-client` for the pinned official Node client.
Credentials reach its bridge on stdin, never argv or logs. An operator config can
replace `policy` with `nexus: {endpoint: "127.0.0.1:<port>", grant_paths:
{sales: "/grants/sales.json"}}`. The daemon must enforce permission on those
resources; use the `zone-grants` policy from the companion cluster change and
read-only zone keys. That policy refuses combination with `--enable-rebac`
instead of silently replacing a provider. This bootstrap binding is not
fine-grained Nexus ReBAC.
The bootstrap client refuses remote plaintext and TLS configurations, because
certificate identity can take precedence over the supplied token. A production
certificate adapter must prove the caller identity instead of forwarding a node
certificate beside somebody else's token.
The SQLite still runs in the data owner's Gateway process. The actual SQL driver
has not been connected, so this does not finish design §7.9. Data-side syscall/driver integration
and network egress restrictions are still required by design §7.9.

For local boundary tests, `FileCapabilities` reads an operator-owned policy on
every request. It stores SHA-256 hashes of random high-entropy bearer tokens:

```json
{"credentials":[{"subject":"alice","sha256":"<token hash>",
  "grants":{"sales":["read","export"]}}]}
```

Omit `export`
for a reader who may inspect but may not export. The operator config is:

```json
{"policy":"policy.json","views":{"sales":{"spec":"sales-projection.yaml"}}}
```

Run `python -m compiler.serve operator-config.json --port 8765`. This local
transport binds only loopback. A deployment must put it behind authenticated
TLS ingress and keep the policy, database and process out of the agent sandbox.
Local file capabilities are a bootstrap test backend, not a replacement for
Nexus ReBAC. Neither backend relies on a caller-supplied `--as` identity.

`python -m tools.check_northwind_access /absolute/path/northwind.db` starts an
isolated HTTP server and proves authentication, registered row scope, graph
counts, pagination, aggregates, omitted address fields, cross-view denial,
separate export permission and immediate revocation on the real Orders table.
This test does not contact Nexus. The browser identifies authorised exports
with a scope notice without revealing unavailable objects or their counts.
The public Northwind ShareOne page is labelled a public demo snapshot; its share
password, if any, is separate from data authorisation.

`python -m tools.check_nexus_access --binary <patched-nexusd-cluster> <northwind.db>`
repeats that acceptance against a fresh Nexus data/identity directory and random
loopback port, including anonymous/invalid-key denial, cross-zone denial and a
read-then-write attempt against the same dummy grant. It also reruns the Northwind
view checks through `NexusAuthority`, and removes its isolated daemon afterward.
The [recorded acceptance](trials/nexus-northwind-2026-10-07.json) states the
tested commits and limitations. Its revocation case removes the view grant;
it does not claim to test Nexus API-key revocation.

Send JSON to `POST /v1` with `Authorization: Bearer <credential>`:

```json
{"operation":"contract"}
{"view":"sales","operation":"graph"}
{"view":"sales","operation":"page","params":{"type":"Order","offset":100,"limit":100}}
{"view":"sales","operation":"query","params":{"expression":"SELECT COUNT(*) FROM Order"}}
{"view":"sales","operation":"export"}
```

The contract declares SQLGlot, dialect, supported aggregates and traversal rules.
The implementation enforces them whether or not an agent reads the contract.
Invalid requests return reason/recovery fields; unauthorised requests return 403.

## Independent question generation

`python -m compiler.blind <dsn> <answerer-dir/questions.json> <judge-dir/oracle.json>`
generates questions from raw schema and data, independently of the ontology.
Templates cover row counts, missing values, extrema and missing FK targets.
They do not invent business definitions such as which revenue recognition rule
is correct. A business reviewer can supply those questions separately.

The public half contains question IDs, source object names and prompts. Expected
answers and SQL stay in the judge's directory. Generation refuses to place both
files in the same directory. This file separation alone is not an OS sandbox:
the answerer must run separately with access only to the public questions and
its authorised gateway, without database files, oracle, service policy, source
credentials or filesystem/process tools on the data server. Scores include
missing/unanswerable questions in the denominator. Creating questions or passing
compiler tests is not an LLM evaluation result.

`--measure` continues to report computational self-consistency and is labelled
accordingly. It never substitutes for this isolated answerer experiment.
Pass `--questions answerer-dir/questions.json` together with `--app` to display
the public questions in the graph. The export refuses oracle-shaped input or
extra question fields such as answers and SQL.

The [2026-10-07 preliminary trial](trials/northwind-2026-10-07.json) sampled three
questions once from the 162-question pool and scored 3/3. A fresh answerer used
only a public graph snapshot and one relayed Gateway query. Access limits in
that run were instructions, not an OS sandbox or reduced tool capabilities;
this is not evidence that adversarial raw-data access is impossible. Two answers
were zero and the sample tests source structure, not business definitions. The
recorded seed, questions, query and answers make that limitation reviewable.
