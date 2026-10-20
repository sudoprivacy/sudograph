# Review navigation contract

The catalogue answers **where is the field, and what are its original values?**
It enumerates the delivered source schema. Its root opens the full source graph,
a source root opens that source, and object/field selection opens a bounded
related subgraph. Expansion, real-record drilldown and stable comment targets
reuse the same schema. Search grants no additional access.

Review views answer **what question are we checking together?** A reviewer can
start from a business subject, trace a reference to fields and records, then
comment to correct its meaning. They can also start from an unfamiliar field.
The directory lists source objects and fields; business views additionally show
definitions and rules absent from the database. Neither route copies facts.

## Deterministic defaults

The source compiler always supplies Data projection and the source catalogue.
An overlay with `source_review` issues additionally supplies Projection and
data review. These are source questions with a verification plan, not phase-two
business definitions. Raw scanning does not invent questions or business meaning.

In `compiler.business`, `views` is now optional. When absent or empty:

1. `compiler.review_views` selects each checked business meaning/metric as a
   subject. Required `purpose` records its stakeholder and decision.
2. Its subject selection includes typed business rules/issues linked to it by
   `applies_to`, then the compiler includes all declared dependencies. Shared
   subjects, rules and source targets retain their canonical identities.
3. Its Questions to confirm selection includes linked business issues whose
   compiler-owned state is `unreviewed`, plus their required subject dependencies.
   It appears only when such issues exist. This is an issue selector, not a
   claim that every other proposal is approved. Source questions stay in phase one.
4. Supporting evidence/implementation notes remain attached in details rather
   than appearing as business nodes. Targets and reference edges are derived.
5. Entry keys combine selector kind with the canonical subject signature. The
   signature already includes project namespace. Algorithm version is separate
   metadata, so layout changes do not churn entry or definition identities.
6. Canonical subject order determines the first business selection. An explicit
   business-overlay compilation establishes phase two; the first YAML key does
   not choose the initial task. With no business subject, the initial selection
   is source review if available, otherwise source projection.

The reader supplies the labels, colours, bilingual hints and guide. Authors do
not call an LLM or supply HTML to obtain these defaults. Checked definitions
without any `views` declarations render directly. The Northwind pilot uses this
path; its current two business entries are not a four-entry menu template for
every future database.

Optional custom `views` preserve the earlier label/seed contract. Their
dependencies are still checked and derived, but their custom grouping is an
explicit configuration choice. They default to source review/projection rather
than the first author-written key. A reviewer can select any permitted entry.

## Limits and enforcement

The compiler validates roles, source identities, metric grain/scope, purposes,
evidence quotes, cycles and version registry changes. Rules/issues must link to
business subjects; source questions cannot depend on phase-two content. The
current overlay has no authenticated per-definition approval endpoint: all
proposals compile as `unreviewed`, and authors cannot add `review_status` to
self-approve. Revision approval in GitLab is a different operation.

Business closures above 200 definitions are refused with their measured size
and recovery guidance; required dependencies are never silently omitted.
Custom smaller selections can narrow the task. This is an explicit canvas
capacity boundary, not completed automatic partitioning of an arbitrary dense
business domain. Source subgraphs separately provide bounded traversal and
component paging. Natural-language interpretation is still domain input;
algorithmic selection does not certify its truth or completeness.

Server authorization must precede delivery/selection/counts. Derived selectors
grant nothing. A document referring to an unavailable source identity is refused;
the compiler does not repair it by retrieving hidden objects. The public static
Northwind share does not establish deployed Sudowork principal-to-source wiring.

Acceptance covers view-free compilation, reordered/renamed author keys, shared
rules, unresolved issues, absent business content, full dependency closure,
capacity refusal, immutable source/record references and rejected self-approval.
The browser journey `tools.check_review_guide` checks the actual generated
navigation and guide; `tools.check_canvas_labels` checks hidden-frame text
geometry. Neither is a new LLM business-understanding evaluation.

## Browser surface and integration status

The primary review surface is a standalone browser window/tab for both Desktop
and WebUI, keeping the canvas outside a small ontology tab. A compact host panel
can still manage the session. Two transports need explicit names:

- Desktop can use the actual managed/personal Chromium window with CDP or an
  extension when agent control is needed. Plain local review needs no extension.
- A WebUI execution browser in the cloud appears in an authenticated independent
  viewer tab using the shared browser session/control path. This shares execution
  state, but transmits rendered images and input. It is not the same UX or latency
  as directly opening the review URL in the user's browser.

Direct local URL review remains useful and does not depend on the remote viewer.
However, it does not by itself satisfy acceptance of a shared execution browser.
The Sudograph integration adapter is still undeployed; its source registry,
scan bridge and native renderer can progress independently of release delivery.

At the 2026-10-20 11:20 CST checkpoint, browser feature
[SudoWork #1275](https://github.com/sudoprivacy/sudowork/pull/1275) and cloud worker
[Moss #413](https://github.com/sudoprivacy/moss/pull/413) were merged. Release
[SudoWork #1276](https://github.com/sudoprivacy/sudowork/pull/1276) remained open.
Its candidate receipt reports independent viewer, real model readback, Unicode
input, browser restart/login persistence, Stop/Return and touch-viewport checks.
Those candidate SPA tests used the then-production cloud worker; they do not
prove the accepted app/worker release is installed or deployed. Physical-phone
handoff remains open. Sudograph still needs text-selection, comments, clipboard
and canvas latency acceptance on the actual viewer.

See the [harness audit](harness-determinism-audit.md) for the code/input boundary
and [source integration contract](source-connection-and-scan-contract.md) for
remaining registered-source wiring. System prompts are not a substitute for any
of these contracts or acceptance checks.
