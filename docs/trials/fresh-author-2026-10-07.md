# Fresh-agent phase-one projection trial

This records the 2026-10-07 workflow, not a fresh trial of the current version.
The current public artifact and coverage baseline are documented in
[the phase-one example](../../examples/northwind-phase-one/README.md).

The independent author started with a new conversation and received the SQLite
file and generic README/compiler/app/schema interfaces. It did not receive the
previous YAML, published graph, discussions or business definitions. Inputs and
conversation were isolated; operating-system access was not sandboxed. This
trial establishes this source and handover, not a success rate for all databases.

The author discovered `compiler.project` and generated complete bound-record
HTML through native `compiler.cli`, without changing compiler/app/schema or
post-processing HTML. The source remained read-only with an unchanged SHA-256.
Final HTML matched the shared renderer's output for the same bundle.

| Comparison | Existing phase-one graph | Independent author |
| --- | ---: | ---: |
| Source tables | 13 | 13 |
| Non-binary bound source fields | 86 | 86 |
| Declared primary keys | 13 | 13 |
| Declared foreign keys | 13 | 13 |
| Authored graph types | 14 | 13 |

The type difference comes from the existing model's two projections of `Orders`,
labelled Sales order and Shipment; the author kept one Orders type. Both cover
the same source table, field, primary-key and foreign-key sets. Names, object
aliases and layout can differ; pixel identity is not evidence of accuracy.

The author compared 625,890 rows, 3,276,955 scalar values and 272 NULLs against
the source. All matched. At that version, 17 views without declared row identity
and two BLOB fields were explicitly excluded from business bindings and retained
in the inventory. Inventory accounted for is not the same as every view/binary
payload delivered. The later full-source reader preserves these too; see the
current baseline for its separate 30-object/204-field evidence.

The native graph supported a Chinese default, an English switch, complete paging
and relationship browsing. Ten browser behaviours were checked. The root agent
also used ai-dev-browser for real clicks on both deliveries: nine Employees,
twelve Orders per page, next-page navigation, record-field expansion and locale
switching passed.

The first handover exposed generic defects: untranslated coverage exceptions and
relationship labels, missing complete columns/keys, truncation of old HTML on
render failure, empty-table ranges of 1–0, and hash-dependent output ordering.
These were fixed in shared infrastructure before regeneration, without supplying
the old graph or business answers. Further non-Northwind tests cover missing-
source exit codes, independent output directories and POSIX absolute DSNs.

Every `source_projection` load now rejects inline copied records, unbound roles,
business formulas/gaps and unsupported source relationships. Earlier net-sales,
category-aggregate and workflow-owner proposals remain in the separate
`examples/northwind-business.yaml` capability fixture. They are unreviewed agent
drafts. Phase-one HTML is read-only; it writes nothing back and does not claim
live updates or cross-connection transactional consistency.

Detailed machine evidence is in `fresh-author-2026-10-07.json`. Original author
reports, comparison scripts, YAML, HTML and screenshots were retained locally.
The database was not committed; a later phase-one freeze added native HTML.

A second independent recheck used the then-final generic code without the first
author's YAML, graph or discussions. Its first native compilation succeeded and
independently checked 13 tables, 86 scalar fields, 13 foreign keys and all bound
source values/identities. Both presentation directories had 91 items. Infra was
not changed during the recheck and no domain answers were supplied. The author
corrected terminal encoding and false alarms in its comparison script. It had no
browser tool; the root agent supplied real-click acceptance. Later raw-value
escaping fixes were regenerated through the shared template without YAML changes
or graph-specific patches.
