# Sales meaning pilot

This phase-two overlay references the [frozen phase-one baseline](../../northwind-phase-one/README.md).
It adds meanings and review questions without changing source SQL, source values,
field identities or the accepted phase-one file. Source SQL computations already
belong to phase one; an observation of those computations is cited here to help
review a proposed business meaning.

The [English preview](index.html) and [Chinese customer-review variant](review.html)
open locally in a browser. Both come from the same compiler and model. Their source and
definition checks run in CI; [preview.json](preview.json) records the file hashes
and review boundaries. Include [the upstream MIT licence](LICENSE.northwind.txt)
when distributing the standalone Northwind preview.

[publication.json](publication.json) records the actual ShareOne publication
state. The [original review share](https://s.shareone.vip/s/sudograph-northwind)
hosts the last approved revision through its pinned remote URL. A new local
candidate is not live until its own content review and publication checks pass;
consult publication.json for the actual state. Existing comment
threads and replies are preserved. Phase two continues the same
working model and review URL; the business overlay is a checked input to that
shared model, not a separate site. The public phase-one acceptance baseline
remains separate as historical evidence.

The pilot has nine definitions and two business views:

- Three supplied observations: the upstream README's business context, the source
  extended-price expression and the source category report's time/grain scope.
- Six model deductions or questions: reporting scope, product versus order-line
  prices, a proposed line-amount total, its rounding rule, a rounding-impact
  question, and freight/tax/currency treatment.
- The second view reuses definitions and their dependencies by identity. It creates no additional
  definitions or independent copies of their meanings.

**Green reuses the phase-one source colour. Orange marks business meanings to
review, whether supplied by a person or inferred by a model. Grey reuses the
phase-one object/field colour.** Source connectors are visible by default and use
a barrel shape. Supplied source observations reuse green but remain definition
nodes, with orange review outlines until reviewed. Details spell out the origin, so
colour is not the only distinction. All definitions remain **unreviewed**. Having
a source citation does not establish that an interpretation is correct; inferred
does not mean incorrect. Business approval is a separate decision.

Meanings, candidate metrics, rules and issues have checked categories. A rule
must name the business subject it applies to; a raw field alone is not its
purpose. Metric definitions require grain and scope. Rules use a hexagon and
issues an ellipse; category labels and the legend supplement shapes. Colour
still expresses provenance and confirmation, not an agent's subjective confidence.

Open a definition to inspect its statement, origin, version and evidence. Follow
a source field to the source reader and real paginated records. Switch views or
language without allocating new field or definition identities. The source
reader and archived phase-one baseline remain accessible.

The two-price interpretation now proposes a catalogue reference price and an
order-line price before its separate discount. The rounding interpretation
applies to the new proposed total of included order-line amounts, not a sum of
unit prices. Its metric defines line grain using OrderID and ProductID, and
leaves reporting period, date, returns, cancellations and currency unconfirmed.
The source's Order Subtotals SQL is cited as evidence of an existing order-level
sum; the proposed broader business total is still an interpretation. A separate
issue explains the conditional precision concern using an explicitly illustrative
0.335 + 0.335 example. These proposals are neither approved nor executed. Domain specialists
can use source evidence, pretrained knowledge, accumulated memory or specialised
models to propose concrete meanings; those inputs do not replace human review.

Canvas labels omit repeated origin/review text and version numbers. Definition
history remains in expandable details. Automatic layout compares both ELK flow
directions with the canvas rather than equating edge flow with graph shape. Source
objects keep compact field catalogues. Page-owned comment marks use the supported
host API so existing comments do not block node selection or text selection.
The details panel starts expanded and can be hidden, including on mobile.
Toggling only resizes the existing canvas and preserves graph, zoom and pan;
it does not rerun ELK or rebuild nodes. Local Chrome checks at desktop and phone
viewport sizes found no increase in scripted pan/zoom work. This is not a
real-phone hardware benchmark. Object anchors currently do not retain precise
text ranges; see the [ShareOne protocol request](../../../docs/shareone-object-text-anchor-fr-2026-10-12.md).

## Generate and check

From the repository root:

```sh
python -m compiler.business examples/northwind/business/pilot.yaml
python -m compiler.business examples/northwind/business/pilot.yaml --app business-review.html --lang zh
python -m compiler.business examples/northwind/business/pilot.yaml --app business-public.html --lang en
```

The compiler checks the phase-one manifest pin and its locked artifact before
loading the overlay. An authored definition must declare `origin: provided` with
`contributor: source` or `business_user`, or `origin: inferred` with
`contributor: model`, and reference existing source IDs. Attribution cannot be
omitted or contradicted. Business-user input requires a supplied document quote;
this pilot has no business-user statements yet. Nodes and their reference edges
carry the same attribution. These edges do not claim source foreign keys.
Supplied claims require a
quotation from a source SQL definition or a supplied document snapshot. The quote
must exist in that evidence; document text is checked against its SHA-256. This
checks reference integrity, not whether a quotation logically proves the claim.
The compiler does not authenticate an external document just from its URL.

IDs derive from the namespace, normalised canonical concept and source targets.
Display labels, language, YAML aliases and the selected view do not change them.
Duplicate concept/target definitions are refused; views carry references. A
change to the canonical concept or targets changes the meaning being identified.
Retargeting requires deliberate migration. The compiler cannot deduplicate every
pair of differently worded but semantically equivalent concepts.

The adjacent `pilot.registry.json` is the shared version registry. Changed
definition content requires a higher version; stale versions are rejected even
by the check-only command. In a service, the operator owns this registry and the
namespace and registers them outside agent-editable documents. CLI callers can
select a shared registry with `--registry`; selecting a new registry is not a
proof of an authorised migration. A multi-writer service transaction and a human
approval endpoint are not implemented in this pilot.

The native renderer rechecks the overlay contract, so another caller cannot
skip origin/identity checks by calling `app.render` directly. Authors cannot
declare themselves confirmed. Existing `mode: business` capability fixtures
remain separate; they are not silently promoted into this reviewed-model flow.

For a saved export:

```sh
python -m compiler.business examples/northwind/business/pilot.yaml --check-app examples/northwind/business/index.html --lang en
```

The example gate validates nested overlay YAML. The full export gate regenerates
the complete English and Chinese HTML, including reader code, styles, SDK settings
and any packed wrapper, and refuses differences beyond platform newlines:

```sh
python -m tools.check_generated
```

An unchanged embedded model cannot hide manual HTML edits. Every HTML in examples
must have a checked generation owner or locked baseline; renaming it cannot skip
the gate. CI and the local verifier share the same six gates. The source artifact
remains immutable.

## Current boundaries

This version records definitions and questions, including an unreviewed rounding
proposal. It introduces no executable sales formula, applied rounding policy,
tax assumption or invented workflow owner. Executable
metrics follow review of their intended meanings and must use the established
checked expression/compiler path. Confirmation history and permissions must be
implemented at the trusted service boundary, not inferred from a menu choice.

ShareOne content review approves exact candidate bytes and access scope; a prior
revision's approval cannot authorise this revision. Hosting approval does not
confirm any business definition. The
phase-one source model, views and complete records equal the frozen baseline;
all seven previous business identities are preserved and two are added. All nine
definitions remain unreviewed. Approved source write-back and a GitLab adapter
are not deployed; their [acceptance plan](../../../docs/source-writeback-acceptance.md)
does not claim an existing full-flow CI test.
