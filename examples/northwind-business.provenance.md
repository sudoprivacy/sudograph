# Provenance of the legacy Northwind business fixture

`northwind-business.yaml` is an **unreviewed agent-authored capability fixture**,
explicitly in `mode: business`. It is not an approved Northwind business model and
is not part of phase-one source artifacts. Retaining it exercises formulas,
relationship aggregates and gaps without presenting its assumptions as facts.

The pinned upstream [src/create.sql](https://github.com/jpwhite3/northwind-SQLite3/blob/4f56e7f5906dfd23b25244c5bfe8fb5da6402efd/src/create.sql)
and the database's `sqlite_master` establish source computations. Matching
arithmetic does not prove that every historical agent proposal was copied from
these sources or that its business meaning is approved.

| Item | Source evidence | What the agent added or changed |
| --- | --- | --- |
| Unit price, quantity, discount, freight and dates | Declared columns in Order Details and Orders | Display aliases and interpretations remain authored labels |
| Line extended amount | Order Details Extended and Invoices use UnitPrice × Quantity × (1 − Discount), with `/100 * 100` in source SQL | The draft calls it a net amount and rounds each line half-up to two decimals; source SQL has no equivalent explicit rounding |
| Net sales total | Order Subtotals aggregates source extended amounts by OrderID | A total over every rounded line is a named business proposal, not the source's order-level view |
| Category net amount | Sales by Category groups by category and product and filters OrderDate to 1997; Category Sales for 1997 uses a shipped-date-filtered upstream view | The draft groups by category over all dates and sums rounded lines; grain, time scope and rounding differ |
| Mean/min/max line amount and discounted-line count | Raw rows permit these computations | The named questions and line grain are agent choices; mean line amount is not mean order value |
| Shipped/unshipped freight totals | Orders has nullable ShippedDate and a Freight column | The split and its business significance are proposed. Missing ShippedDate does not establish cancellation or a broken workflow |
| Missing-address or missing-customer business gaps | NULLs and missing source references can be observed | Calling them business issues, choosing affected metrics and defining resolution policies were agent choices |
| Warehouse supervisor owns the gaps | No source assignment establishes this | The fixture invented a workflow role and its owner; it is not an Employees record |
| Category total agrees with the all-line total | Both calculations use the draft's definitions | This is internal consistency, not independent business validation |

The draft also describes its amount as excluding freight and tax. Its formula
does not reference Freight, but SQL alone does not establish whether UnitPrice
includes tax, which currency applies, when revenue is recognised, or how returns
are treated. These require source documentation and business review.

There are three distinct authorities:

- Source structure, rows and stored SQL establish what this source contains and
  computes. Phase one preserves them even if a source view appears questionable.
- Compiler checks establish valid references, grain, arithmetic consistency and
  declared identity. They cannot approve a business meaning.
- Business reviewers and cited documents establish the intended definition.
  Until reviewed, an agent's interpretation remains a proposal.

## Proposed phase-two pilot, not an implementation

Start with one question: **What does sales amount mean in this business, and how
does it relate to the source's extended-price calculations?** Review source
fields and real rows before choosing recognition date, scope, rounding, freight,
tax or return treatment. Record unresolved points instead of conventional guesses.

Create a separate business view referencing the pinned phase-one source IDs.
Definitions need one canonical identity, provenance, review status and version;
view changes reuse that definition rather than allocate another one. Keep the
accepted phase-one artifact separately accessible.

The loop is reviewer comment → agent definition change → compiler diagnostics →
business-view comparison with source evidence and representative records →
reviewer confirmation. Then test a fresh agent using the same interfaces.
Server-authorised visibility should feed the same view definitions, with access
decided before returning data. The combined baseline/overlay reader and durable
business-definition lifecycle remain to be implemented after agreeing on the
pilot. This document does not promote the legacy draft into acceptance.
