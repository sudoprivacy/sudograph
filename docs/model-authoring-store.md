# Transactional model authoring

`compiler.workspace` implements ordinary model edits without GitLab review. It
shares the checked YAML entrance with the optional GitLab publisher through
`compiler.model_contract`; neither path accepts generated HTML or caller-chosen
source paths. The existing publisher's review gates remain unchanged.

The canonical payload is YAML in a host-owned SQLite store. Each immutable
revision retains its parent, YAML, identity reservations, compiled model, shared
renderer HTML, deterministic context and host actor. HTML and context carry the
same model revision. These products are committed with the current-version
pointer and operation receipt in one transaction. Compiler or renderer failure
leaves the previous usable revision intact. This store is the authoring
authority; a Git export must be a derived history, not a second writable model.

## Operator registration

Register a complete read-only SQLite projection before exposing model tools:

```sh
python -m tools.model_workspace --source sqlite:///customer.sqlite --store models/customer.db --namespace customer --lang en
```

The default registers complete source structure without embedding record rows.
`--snapshot-records` explicitly chooses a frozen record export. Neither mode
turns this adapter into a live record gateway. The existing permission-aware
gateway must still be connected to source catalogue paging in the host.

Registration is a deployment operation. Paths, namespace, locale, pointers and
the source baseline belong to the host. An existing store cannot be rebound by
running registration again. Source relocation and rename mappings are separate
work; this change does not replace the source scanner's current path identity.

## Checked writes and concurrent sessions

`Workspace.apply(request, actor=host_actor)` accepts exactly:

```json
{"base_revision":"<revision from contract>","operation_id":"<stable retry identity>","model":"<complete checked YAML>"}
```

The source pin and registered namespace are enforced. Every branch passes the
business compiler and canonical identity registry before merging. Independent
processes serialize commits through SQLite. Disjoint edits merge by canonical
concept identity; changing an author key does not create a new concept. The
same definition, evidence document or view is atomic during a concurrent merge.
Conflicting changes return `MODEL_CONFLICT` with affected paths. A merged model
must pass the compiler again, including dependency and version checks.

The same operation, payload and actor reuse the original receipt after restart
or a lost response. Reusing an operation ID for a different payload or actor is
refused. Retired identity reservations remain available to later revisions.

The host subprocess protocol is JSON lines:

```sh
python -m compiler.workspace --store models/customer.db --actor <authenticated-host-actor>
```

It exposes `contract`, `apply`, `read` and version-bound `context_read` operations.
The context compiler emits MCP tool names and exact argument objects for this
host path; agents do not translate generic HTTP pointers themselves. The shared
renderer previews the same transport and registered pointers. Existing HTTP
context exports retain their original contract.
Only the host launches this process. It is not an authenticated public server.
The embedding service must authorize the project before every call and retain
its tenant/session binding. The subprocess cannot authorize a caller from YAML.

## Sudowork implementation boundary

The matching Sudowork branch introduces a project authority registry, separates
conversation ownership from RDF payload storage, refuses legacy RDF access to
registered Sudograph projects and selects canonical MCP tools from the persisted
authority. Creation and restoration read the current deterministic context.
Successful MCP edits emit a versioned `ontology.model-changed` event.

This is the first host adapter slice. It is not deployed product acceptance.
Connector UI registration, standalone review-page refresh, active-session
context refresh, durable ShareOne comment delivery, account revocation and the
Moss/WebUI provider still require implementation and joint acceptance. The
native local-profile transport does not establish multi-tenant authorization.
No new business-summary model call or production-data executor is included.

## Reproducible host-boundary acceptance

With Bun and both implementation checkouts available:

```sh
python -m tools.accept_workspace_adapter --sudowork ../sudowork --receipt adapter-receipt.json
```

On Windows, `--bun` may name the actual `bun.exe` when the interactive command
is a PowerShell wrapper. The test uses the real TypeScript client and Python
compiler against an unrelated SQLite fixture: two actors, separate worker
processes, compatible merge, incompatible edit, durable retry, one graph/context
revision and an unchanged source database. The context preloads zero rows.
This receipt proves the subprocess boundary, not browser or cloud deployment.
