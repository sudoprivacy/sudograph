# Northwind phase-one baseline

[Public example](https://s.shareone.vip/s/sudograph-northwind-phase-one-baseline)
uses a separate share with comments disabled. It currently serves the original
Chinese-default baseline. An English presentation is available in this repository;
ShareOne's automatic review rejected the packed remote-url update, so that
deployment awaits human review. Internal customer review keeps its Chinese
default and the shared language switch.
Historical review comments are not copied into public artifacts or shares.

The [frozen native HTML](2026-10-10/index.html) is direct compiler/shared-renderer
output. Download it and open it in a browser. Its original Chinese default and
byte hashes remain historical evidence. The public English presentation is
generated separately as [public/index.html](public/index.html) from the same
frozen bundle, with all source identities,
fields and records intact. See [publication.json](publication.json) for the
deployed presentation and the publication mechanism actually used.

The [public manifest](public/baseline.json) pins its own renderer revision,
English default, packaging and file hashes while retaining the original source
extraction timestamp. The public presentation was compared to every typed value
in the pinned source database, including binary payloads.

The packed file is below ShareOne's remote fetch size limit, but its encoded HTML
was rejected as a potential script risk. Size acceptance and content approval
are separate requirements. The original share was left unchanged and verified
byte-for-byte after the rejection. No alternative publication path was attempted.

This is an **internal phase-one review baseline**. Structure and data completeness
have been checked; business meaning still requires human review. It does not
claim a production permission deployment or a completed fresh-agent trial on the
current version.

## Source and coverage

The source is [jpwhite3/northwind-SQLite3](https://github.com/jpwhite3/northwind-SQLite3)
at [`4f56e7f5906dfd23b25244c5bfe8fb5da6402efd`](https://github.com/jpwhite3/northwind-SQLite3/tree/4f56e7f5906dfd23b25244c5bfe8fb5da6402efd).
Upstream supplies a populated `dist/northwind.db`. This demo uses that file
unchanged and read-only; it did not perform another CSV import or `make populate`.
The local database was compared byte-for-byte with the pinned upstream Git blob.

Database SHA-256: `2f4f5c68dfcd33ba27373eae48c7a4869800c68095ee0f9f0da494f83382a877`.
The upstream MIT licence is included as [LICENSE.northwind.txt](2026-10-10/LICENSE.northwind.txt).

| Scope | Count | Meaning |
| --- | ---: | --- |
| Source tables | 13 | All business source tables, including empty tables |
| Source views | 17 | Source SQL definitions and every result row, including empty views |
| Source fields | 204 | Includes binary fields |
| Base-table records | 625,890 | Tables only |
| Table and view result rows | 1,909,973 | Views repeat underlying facts; this is not a count of independent facts |
| Field values | 23,841,939 | Every value compared, preserving types, NULL, duplicates and float bits |
| Non-null binary values | 17 | Bytes, lengths and hashes compared |

Complete coverage means the business tables, views, fields and records in this
pinned SQLite file. SQLite's internal `sqlite_sequence` and indexes are not
separate business graph nodes. It does not mean every generator, illustration or
alternative database implementation in the upstream repository has been modelled.
Calculations already present in source view SQL remain source facts; phase one
does not author new revenue definitions.

The archived `generation.yaml` retains the old `raw.exclude` explanations. These
describe the authored business-type binding inventory, not filters on the full
source snapshot. Full coverage is established by `source_schema` and the raw-data
audit; views, duplicate keyless rows and binary bytes are all preserved. Do not
confuse the historical binding inventory with complete source delivery.

## Frozen evidence

[baseline.json](2026-10-10/baseline.json) pins the renderer revision, upstream
revision, database digest, generation options, file digests and coverage counts.
[validation.json](2026-10-10/validation.json) records checks, results and acceptance
boundaries. `generation.yaml` copies the input originally located at
`examples/northwind.yaml`; its relative DSN resolves from that original location,
not from the archive directory.

The source extraction timestamp remains `2026-10-08T10:29:34.263342+00:00` in
`projection.generated_at`. The freeze timestamp is separate. The shared renderer
was updated after extraction; freezing or translating a presentation does not
claim another database scan.

A clean agent independently completed the 2026-10-07 projection workflow. Its
artifact was later regenerated through the shared compiler and renderer to
include complete source fields and records. **This establishes the older workflow
and reuse of shared capabilities; it is not a new end-to-end trial of the current
version.** The preliminary three-question blind test scored 3/3, used instruction
isolation rather than an OS sandbox, and did not establish business correctness.

Table and field inspectors provide real paginated records. A few complete rows
directly on the canvas have not shipped. Server permission acceptance passed in
an isolated environment; the public static sample is not a production user-
authenticated gateway.

## Checks and reproduction

Install dependencies and, from the repository root, check every frozen example:

```sh
python -m tools.check_baselines
```

CI runs the same check: locked file sizes/digests, native source contracts and
coverage declarations. CI does not download Northwind. **File-digest checks do
not replace comparison against the source database.** With the pinned database
available, rerun the complete read-only audit:

```sh
python -m tools.check_baselines examples/northwind-phase-one/2026-10-10/baseline.json --source ../northwind-SQLite3/dist/northwind.db
python -m tools.check_baselines examples/northwind-phase-one/public/baseline.json --source ../northwind-SQLite3/dist/northwind.db
```

The checker has no Northwind table/column exceptions. Tests use unrelated
temporary databases and demonstrate rejection of omitted objects, incorrect
values, missing segments, false coverage and changed frozen files.

To rescan the same source:

1. Fetch the pinned [dist/northwind.db](https://raw.githubusercontent.com/jpwhite3/northwind-SQLite3/4f56e7f5906dfd23b25244c5bfe8fb5da6402efd/dist/northwind.db)
   and verify the SHA-256 above.
2. For historical generation, use sudograph revision
   `89668f844e41ccadeab45e9b797baf41277cce58`, preserve its original sibling
   directory layout and run:

   ```sh
   python -m compiler.cli examples/northwind.yaml --mode source_projection --records --app northwind.html --lang zh
   ```

3. A fresh agent should discover source structure through the generic entry point.
   For a public English export on the current version:

   ```sh
   python -m compiler.project sqlite:////absolute/path/northwind.db projection.yaml --name "Northwind source projection" --app projection.html --records --lang en --pack-html
   ```

A new scan has a new timestamp. Source ID namespaces currently derive from the
canonical physical database path; relocation requires an explicit source
migration. IDs and HTML digests are not promised identical across machines.
Display aliases and languages may differ. Compare source facts, coverage and
interaction quality instead of pixel identity.

For exact replay of historical HTML, use its pinned renderer, decode the JSON
following `const BUNDLE = `, call `compiler.app.render(bundle, language="zh")`
and write UTF-8 with CRLF line endings. This reproduces the frozen bytes with
SHA-256 `9d0e4d6d9607fe1e2207a441fcd04a29d08daf1ea18aa068cc0f9c3ba57db121`.
Do not hand-patch a frozen graph; improvements produce a new presentation or
acceptance baseline through shared infrastructure.

`--pack-html` losslessly compresses the entire native HTML. The browser unpacks
the same document locally using the gzip capability already required for record
pages. It fetches no source data, removes no records and computes no business
figures. The baseline checker reads plain and packed exports. Smaller delivery
bytes do not change dataset coverage.

Phase two adds separately reviewed business definitions and views referencing
the same source identities. Keep this phase-one snapshot as the review baseline.
The [legacy business fixture's provenance](../northwind/business/provenance.md)
distinguishes upstream calculations from agent-authored assumptions; it is not
an accepted phase-two model.
