# Bounded source records

`compiler.source_records.SourceRecords` reads one registered source object on
demand. It reuses the source catalogue, stable object/field IDs, read-only SQLite
connection and scalar wire codec. It does not introduce a second model, accept
raw SQL from an agent, or put source records in the context packet.

## Registration and reads

`tools.model_workspace` registers complete SQLite structure and a private
source-ID-to-DSN mapping by default. `--snapshot-records` retains the explicit
frozen-export path. A store created through the Python API uses snapshots unless
the operator supplies `record_sources`.

The source binding is stored only in host settings. Compiled products contain
`projection.record_delivery: live`, not the DSN. Existing MCP
`sudograph_context_read` requests select a source object ID, context revision and
digest, `records: true`, offset and limit. They cannot select a path, SQL,
columns, credentials or scope. The compiler emits the exact MCP pointer.

Each page validates the object's current SQL definition, type, columns, keys
and foreign keys against the registered catalogue. A renamed field, removed
table or changed database view returns `SOURCE_SCHEMA_CHANGED` with recovery
instructions. An unavailable source returns `SOURCE_UNAVAILABLE` without exposing
its operator path. Model edits do not change these bindings.

Rows remain aligned across fields, with declared keys, NULL, binary values,
large integers and duplicate view results preserved. Tables use declared key
order. A keyless result uses deterministic column order and request-local
positions; those positions are not durable business identities. NULL in a
declared key is an explicit source-identity error.

## Observation and limits

Count and rows use one read transaction. Separate pages may observe source
changes; this is not a historical data snapshot. The response carries
`data_kind: live_source_page`, an observation ID/time, current `total`, earlier
`catalog_total` and the registered source digest. A live count does not silently
rewrite the catalogue or its model revision.

Requests accept 1–100 rows and a nonnegative offset. The adapter enforces a 4 MiB
page/SQLite-value budget and returns `RECORD_PAGE_TOO_LARGE` rather than truncating
values. Request fewer rows, or use a separately authorized export for an
oversized single record. Both the context packet and rendered context preview
identify live delivery; they still preload zero rows.

## Authorization and deployment boundary

This is a private adapter for an already-authorized model and complete registered
source. It is not a public endpoint or a permission engine. The Sudowork native
builder checks its scoped project token and persisted model authority before
invoking the worker. Cloud tenant grants, row/field projections and their
reauthorization must still be connected through the data owner's gateway.
Changing a graph view or adding YAML never grants database access.

The agent record-read path is implemented; standalone browser record-panel
transport and its browser acceptance are separate integration work. Portable
frozen exports retain their existing reader and are not revocable access control.

The shared SQLite connector percent-encodes file URIs, including `#` and spaces,
and always opens in read-only mode. Identifier quoting is shared across source
verification, uniqueness checks, loading and paging, including names with quotes.
