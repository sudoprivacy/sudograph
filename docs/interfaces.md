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

Both views start with source connectors folded out of the canvas and
edge labels shown around a selected node. Source provenance remains in each
type's details; `Show sources` restores its nodes and edges. `Focus neighbors`
shows one hop around a selected object; `Full graph` restores the overview.
Neither control changes the compiled model or access permissions. The default is
ELK layered with its own orthogonal edge routes, including bends and endpoints.
Cytoscape keeps a curved self-loop for self-relations. fCoSE is an optional
comparison: it uses relative placement constraints from the acyclic ordering,
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
The Northwind example currently includes draft business interpretations (net
sales, gap-resolution criteria and an illustrative owner role). They demonstrate
stage-two mechanisms but are not user-confirmed business policy. The current
work remains source projection and infra validation; the display selector cannot
prove that a spec contains only source facts.

## Server-side visibility

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
read-only zone keys. This bootstrap binding is not fine-grained Nexus ReBAC.
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
