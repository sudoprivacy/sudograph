# Sales meaning pilot

This phase-two overlay references the [frozen phase-one baseline](../../northwind-phase-one/README.md).
It adds meanings and review questions without changing source SQL, source values,
field identities or the accepted phase-one file. Source SQL computations already
belong to phase one; an observation of those computations is cited here to help
review a proposed business meaning.

The [English preview](index.html) opens locally in a browser. Its source and
definition checks run in CI; [preview.json](preview.json) records the file hashes
and review boundaries. Include [the upstream MIT licence](LICENSE.northwind.txt)
when distributing the standalone Northwind preview.

The pilot has seven definitions and two business views:

- Three supplied observations: the upstream README's business context, the source
  extended-price expression and the source category report's time/grain scope.
- Four model deductions or questions: reporting scope, product versus order-line
  prices, rounding, and freight/tax/currency treatment.
- The second view reuses the four questions by identity. It creates no additional
  definitions or independent copies of their meanings.

**Green means supplied evidence. Purple means model deduction. Grey means a source
object or field.** The legend and each definition also spell out the origin, so
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
loading the overlay. An authored definition must declare `origin: provided` or
`origin: inferred` and reference existing source IDs. Supplied claims require a
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
English HTML against the same source snapshot and canonical definitions. This
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
