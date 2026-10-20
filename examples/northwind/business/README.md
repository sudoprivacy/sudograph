# Annual order-sales pilot

This phase-two overlay references the [frozen phase-one baseline](../../northwind-phase-one/README.md).
It adds meanings and review questions without changing source SQL, source values,
field identities or the accepted phase-one file. Source SQL computations already
belong to phase one. The live model also allows phase-one data questions without
turning them into business definitions. The source graph and records stay unchanged.

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

The pilot keeps nine canonical identities and two source presentations. Its
business subject and unresolved-question selections now come from the shared
algorithm, with no authored `views` list in `pilot.yaml`:

- Four business nodes: an annual order-sales metric, a historical transaction
  pricing policy, an inclusion/currency question and a category-reporting question.
  Sales management compares annual order sales; finance helps review what the
  amounts include. These are model proposals, not authenticated user instructions.
- **Data projection** shows source objects, fields, stored SQL and relationships.
- **Projection and data review** reuses that graph with three orange source questions:
  whether the extended-price expression rounds, how the source report's timestamps
  limit coverage, and whether source precision affects recombined totals. Each
  carries a verification plan; none claims an observed source defect.
- Two supporting details remain attached to the business metric: the supplied
  upstream context and a proposed settlement rounding rule. This proposed business
  policy differs from checking what the source expression already computes.
- The second view reuses definitions and their dependencies by identity. It creates no additional
  definitions or independent copies of their meanings.

Subject selection includes attached typed business rules/questions and their
dependency closure. The question selection keeps unresolved issues and their
required subject context. Evidence and implementation notes remain in details.
Canonical ordering chooses the initial business subject; YAML entry order does
not. Optional custom selections are still supported for other projects. See the
[navigation contract](../../../docs/review-navigation-contract.md).

The shared **Quick tour** is optional and starts manually by default. Operators
can select first-visit or disabled mode in the checked reader policy. It explains
review questions, source fields, real records and comments without moving the
canvas, editing the model or adding pan/zoom listeners.

**Green reuses the phase-one source colour. Orange marks unconfirmed source
questions or business proposals, in their respective views. Grey reuses the
phase-one object/field colour.** Source connectors are visible by default and use
a barrel shape. All unreviewed business nodes use orange, including a proposal
based on supplied information. Source evidence appears in details, outside the
business canvas. Source questions appear only in the source-review view, never
in a business view. Details spell out the origin. All business definitions remain
**unreviewed**. Having
a source citation does not establish that an interpretation is correct; inferred
does not mean incorrect. Business approval is a separate decision.

Meanings, candidate metrics, rules and issues have checked categories. A rule
must name the business subject it applies to; a raw field alone is not its
purpose. Metric definitions require grain and scope. Rules use a hexagon and
issues an ellipse; the legend draws the same actual shapes as the selected view.
There is no separate orange-outline legend with a competing meaning. Colour
does not express an agent's subjective confidence.

Open a definition to inspect its statement, origin, version and evidence. Follow
a source field to the source reader and real paginated records. Switch views or
language without allocating new field or definition identities. The source
reader and archived phase-one baseline remain accessible.

The metric proposes one result per calendar year using Orders.OrderDate and
historical order-line prices. Its line grain remains OrderID and ProductID.
It measures ordered sales, not cash collected or recognised accounting revenue.
Tax, freight, currency, returns and cancellations remain unconfirmed.
The source's Order Subtotals SQL is cited as evidence of an existing order-level
sum; the proposed broader business total is still an interpretation. A separate
source-review question explains the conditional precision concern using an explicitly illustrative
0.335 + 0.335 example. Its verification plan calls for checking real source amounts;
the example is not evidence of a defect. These proposals are neither approved nor executed. Domain specialists
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
real-phone hardware benchmark. New object comments retain precise text ranges
and content versions; exact recovery works on an unchanged readable surface.
The reader now implements ShareOne's passive `resync-text` callback. Visible
unchanged passages recover without a navigation gesture; hidden detail surfaces
stay pending. Cached batches and camera movement do not scan text. Cancellation
clears only its own Range. Text and object mark switches are independent, and a
click on a unique native passage activates its exact comment thread. The earlier
[ShareOne SDK follow-up](../../../docs/shareone-visible-object-passages-br-2026-10-13.md)
records the original gap; publication acceptance checks the deployed SDK as well.
At the 2026-10-14 production check the injected ShareOne SDK still lacks
`resyncText` and `activateComment`, including with browser caching disabled.
The page adaptation and local native-Range checks are complete; passive recovery,
independent mark controls and exact-thread activation are not yet a production
acceptance. Explicit recovery and object activation retain their existing path.
The small comment button activates the existing object thread through the SDK;
it does not obstruct label selection or normal node clicks.

## Generate and check

From the repository root:

```sh
python -m compiler.business examples/northwind/business/pilot.yaml
python -m compiler.business examples/northwind/business/pilot.yaml --app business-review.html --lang zh
python -m compiler.business examples/northwind/business/pilot.yaml --app business-public.html --lang en
```

The v4 contract requires `role: business`, `source_review`, `source_evidence` or
`implementation_note`. A business meaning/metric must declare
`purpose: {stakeholder: ..., decision: ...}`. Business rules/questions must name
the business subject they serve. Source questions require `category: issue`, source
`targets` and a nonempty `verification` plan. They cannot depend on a business
definition or appear in a business view; an overlay can contain only source
questions with `views: {}`. The pure projection does not show these annotations.
Both source presentations share record drilldown; the former records-and-links
menu is retained internally only for existing record anchors.
Evidence/notes require `applies_to` references
and cannot appear in a view's `definitions`. They retain their identities,
versions and comment references in evidence details. The managed write contract
returns these requirements and phase-specific authoring guidance, and the parser, renderer and trusted publisher
enforce them. Old format versions cannot bypass this gate. Structural validation
cannot prove that a proposal expresses the correct business; people still review it.

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

This version records annual-sales definitions and phase-one source questions,
including an unreviewed rounding policy in business evidence details. It introduces no executable sales formula, applied rounding policy,
tax assumption or invented workflow owner. Executable
metrics follow review of their intended meanings and must use the established
checked expression/compiler path. Confirmation history and permissions must be
implemented at the trusted service boundary, not inferred from a menu choice.

ShareOne content review approves exact candidate bytes and access scope; a prior
revision's approval cannot authorise this revision. Hosting approval does not
confirm any business definition. The
phase-one source model, views and complete records equal the frozen baseline;
all nine previous identities are preserved without allocating replacements.
Managed GitLab deployment has a
[real acceptance](../../../docs/trials/gitlab-managed-2026-10-13.md).
Customer Nexus SSO, business confirmation history and approved source write-back
remain separate work. The [write-back plan](../../../docs/source-writeback-acceptance.md)
does not claim that source writes have been deployed.
