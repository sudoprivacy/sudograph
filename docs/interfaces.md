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

Cytoscape 3.30.2 renders the active graph, with ELK layout and DOM labels for text
selection. The ShareOne application-anchor protocol supplies canvas node bounds.
Source rows are paged separately: a large database does not imply placing all its
rows on one canvas. No million-node rendering performance claim has been made.

The data projection starts with source connectors folded out of the canvas and
edge labels shown around a selected node. Source provenance remains in each
type's details; `Show sources` restores its nodes and edges. `Focus neighbors`
shows one hop around a selected object; `Full graph` restores the overview.
Neither control changes the compiled model or access permissions. ELK offers
left-to-right and top-to-bottom layouts; `Rearrange` discards manual placement
for the current view. Dragging node borders moves their text and attached edges.
Placements survive projection/focus/language switches during the current page
session; they are not saved to the server or across a reload.

The template includes a Chinese/English selector. Controls, legend and panels
switch together without changing graph identities or coordinates. Business
names and authored evidence retain the source language. Missing template
translations fail rendering rather than silently falling back to one language.

`Data projection` and `Metrics and rules` are display choices, not workflow
stages. Node colours describe kinds and unresolved upstream gaps; they do not
encode stage, permission or a claim that a business definition is correct.

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
operator-owned grant resource through Nexus. Its client must return authenticated
`subject` and `content`, and perform `sys_read` with the caller's OperationContext.
The grant content is `{"resource":"view/a","subject":"alice","actions":["read"]}`.
A missing grant, mismatch, denied read or unavailable backend denies access.
It is an integration adapter, not proof that the actual Nexus SQL driver and
permission provider have been deployed. The data-side syscall/driver integration
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
