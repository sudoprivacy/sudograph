# Fresh-context business author, 2026-10-14

A new agent received the actual managed authoring contract, a registered
Northwind phase-one schema with original SQL, a short public ERP description and
a request to propose a small sales-management model for understanding performance
over time. It inherited no conversation and saw no prior business definitions,
working diagram, review comments or earlier trial. The author could inspect the
generic contract/compiler and submit YAML; it could not edit the operator inputs,
renderer or repository. This was instruction-scoped conversation isolation, not
an adversarial operating-system sandbox.

The author produced [model.yaml](model.yaml), accepted by `managed.compile_model`,
the canonical registry, shared renderer and complete-export checker. It contains
12 business definitions, two exact source-SQL observations and one implementation
note. Two business views reuse the annual-sales definition by identity. The full
source schema, source views and records remain unchanged. [receipt.json](receipt.json)
records inputs, hashes, identity reuse and limits.

The business proposal includes annual discounted order sales, distinct order
count, average order value and category share, with time attribution, common order
eligibility and recorded-price policies. Its purpose is to help sales management
choose whether to investigate order frequency, order value or assortment. Source
SQL supplies evidence; it does not approve accounting revenue. No new figures were
executed. These are business modelling proposals rather than a collection of
data-quality questions.

The draft passed without compiler refusals or authoring repairs. The first local
invocation failed before validation because the default Python outside the
repository lacked SQLGlot. The existing repository `.venv` interpreter ran the
unchanged adapter successfully; no dependency was installed. The GitLab transport
was a synthetic protocol fixture, so this is local authoring acceptance, not a
new deployment or authenticated-service acceptance.

The fresh author proposes retaining precision through aggregation and rounding
displayed totals. The working pilot retains a different, unconfirmed per-line
settlement-rounding proposal. This difference must be reviewed as a business
choice; a successful compilation cannot choose the correct settlement policy.
Likewise, currency, lifecycle, historical categories and reporting completeness
remain subject to business confirmation. One successful trial does not establish
that every clean agent will understand the business correctly.

The trial uses a separate operator namespace. Its definitions were not added to
the working Northwind model, its registry or its review share. Before adopting any
idea, reconcile it with the existing canonical definitions and increment their
versions; do not copy this trial's identities into production as duplicates.

The supplied schema comes from the [frozen source baseline](../../../examples/northwind-phase-one/README.md)
and the pinned [Northwind upstream](https://github.com/jpwhite3/northwind-SQLite3/tree/4f56e7f5906dfd23b25244c5bfe8fb5da6402efd).
No private discussion text or credentials are included.

To replay the compiler boundary in an environment with the repository dependencies,
load the locked baseline through `tools.check_baselines.check` and `bundle`, then
pass the YAML to `managed.compile_model` with the receipt's operator namespace.
The `registered-source-baseline` pin is a managed-service contract, not a filesystem
path for `compiler.business` CLI. Rendering that result through `app.render` and
`app.check_export` verifies the complete reader; it does not confirm business truth.
