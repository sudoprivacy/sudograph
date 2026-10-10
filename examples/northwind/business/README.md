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
state. The original review share is unchanged while formal review of this new
candidate is pending. The approved public phase-one baseline remains separate.

The pilot has seven definitions and two business views:

- Three supplied observations: the upstream README's business context, the source
  extended-price expression and the source category report's time/grain scope.
- Four model deductions or questions: reporting scope, product versus order-line
  prices, rounding, and freight/tax/currency treatment.
- The second view reuses the four questions by identity. It creates no additional
  definitions or independent copies of their meanings.

**Green reuses the phase-one source colour. Orange marks model questions. Grey
reuses the phase-one object/field colour.** All definitions have orange review
outlines until reviewed. The legend and each definition also spell out the origin, so
colour is not the only distinction. All definitions remain **unreviewed**. Having
a source citation does not establish that an interpretation is correct; inferred
does not mean incorrect. Business approval is a separate decision.

Open a definition to inspect its statement, origin, version and evidence. Follow
a source field to the source reader and real paginated records. Switch views or
language without allocating new field or definition identities. The source
reader and archived phase-one baseline remain accessible.

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

The example gate validates nested overlay YAML and, when present, checks the saved
English HTML and Chinese review variant against the same source snapshot and canonical definitions. This
reuses the existing five-gate CI workflow. The source artifact remains immutable.

## Current boundaries

This version records definitions and questions. It introduces no sales formula,
tax assumption, new rounding policy or invented workflow owner. Executable
metrics follow review of their intended meanings and must use the established
checked expression/compiler path. Confirmation history and permissions must be
implemented at the trusted service boundary, not inferred from a menu choice.

The public remote-url publication is separately awaiting ShareOne's supported
resolution of the size/moderation blockers. Local browser checks establish that
origins, citations, language switching, reused identities and record drilldown
work; they do not establish deployment or business acceptance.
