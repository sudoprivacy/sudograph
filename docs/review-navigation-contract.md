# Review views, source catalogue and authoring responsibility

This describes the current implementation, not a promise that every database
produces the four Northwind menu entries or identical business proposals.

## Why both navigation sections exist

The catalogue answers **where is this source object or field?** It enumerates
the delivered source schema. Its root opens the full source-object graph, a
source root opens that source, and object/field selection opens a bounded related
subgraph. Expansion, keys, real-record drilldown and canonical comment targets
reuse that same schema. A catalogue search is not a new model or an access grant.

Review views answer **which question are we reviewing together?** They preserve
a task-focused set of business definitions and their references. A rule can be
reused in several views by the same identity. A reviewer can start from a task,
trace a reference to its field and records, then comment on the business meaning.
Starting from an unfamiliar field, the reviewer can instead use the catalogue,
inspect records and identify the relevant business question. Neither route
requires copying a definition or source fact.

The current directory lists source objects/fields, not the added business rules
and meanings. It therefore cannot by itself replace business-review entry points.
There is some navigational overlap between Data projection and the full-source
catalogue root, especially for a single source. That is a presentation choice,
not two authoritative models or a requirement to keep four buttons forever.

## What a new source environment produces

| Entry | Trigger and owner | What a fresh project should expect |
| --- | --- | --- |
| Source catalogue | Deterministic source scan/compiler | The actual source objects/fields within the delivered scope; no Northwind names or fixed object count |
| Data projection | Shared reader when a source schema exists | Standard source presentation; the current initial kind filter is tables, with database-view/all filters available. The catalogue full-source action explicitly selects all kinds. |
| Projection and data review | A checked overlay contains `source_review` questions | Optional presentation over the same source schema, with unconfirmed source questions and verification plans. Raw scanning alone does not manufacture these questions. |
| Business review views | Explicit nonempty `views` declarations referencing checked business definitions | As many task views as the project declares. A pure phase-one scan has none of these. Northwind's two business views are authored pilot choices. |

LLMs or people can propose source-review questions and business views. Their
registration and rendering are deterministic; their usefulness and semantic
coverage are not inferred or proven by the menu code. The first declared business
view is currently the initial presentation when a business overlay is loaded.
That is implementation order, not an algorithm choosing the most important
business question.

Permission-aware delivery must filter the model server-side before selection,
counts and record access. The menu presents that result; it does not replace
authorization. The static Northwind share does not establish deployed Sudowork
principal-to-source integration.

## What the LLM decides and what the compiler derives

| Work | Current responsibility |
| --- | --- |
| Business objective, stakeholder, definition, proposed policy and unresolved choices | Business participant and LLM; evidence and confirmation remain explicit |
| Source field targets, metric grain/scope and definition dependencies | Author declares them using discovered identities; compiler validates references and required structure |
| View label and seed definition list | Author proposes them. The YAML view declaration is a label plus definition references, not a drawing specification. |
| Dependency closure, supporting notes, union of source targets and reference edges | Compiler derives them from the checked declarations |
| Canonical identities, version/registry checks and exact duplicate signatures | Shared infrastructure; this does not prove semantic equivalence of differently worded concepts |
| Shapes, colours, bilingual controls, field/record drilldown, layout and comment anchors | Shared renderer/compiler; an author does not design new HTML |
| Whether the chosen business model is correct, useful and complete | Human/LLM review and appropriate business evaluation; successful compilation is insufficient |

The compiler rejects unknown source IDs, duplicate references, unsupported roles,
missing purposes/grain/scope, invalid evidence and version/registry conflicts. It
requires unresolved proposals to remain unreviewed. It does not prove that a
natural-language purpose is sensible, a reporting policy is correct or every
business concern was discovered. These checks reduce mechanical authoring work;
business understanding still requires substantial LLM reasoning and human input.

That describes the current boundary, not the desired dependency on model skill.
The harness must not compensate by adding system prompts that tell authors how
to group views. Business interpretation is supplied by people or external model
providers; deterministic navigation must work without asking a model to design
the interface.

## Required deterministic default-view design

This is the intended next implementation, not a claim it is already in the
compiler. Today the view loop in `compiler.business` still requires seed lists.

1. Take checked canonical definitions, typed roles/categories, source targets,
   declared `applies_to` edges and trusted review state as input. Do not infer
   business links or groups from label wording, embeddings or a model call.
2. Derive the source projection and catalogue directly from source schema. A
   source-review selector includes existing `source_review` items and their
   targets. Source questions remain optional inputs; no invented questions are
   needed to make a source project usable.
3. Derive a business-subject entry for each checked meaning/metric with a declared
   business purpose. Include its dependency closure and rules/questions attached
   through declared links, with their source targets and parent objects. Shared
   rules/fields keep their canonical identity across entries. Structural
   grouping and bounded graph traversal use explicit limits and stable ordering.
4. Derive a pending-business-review selector from business role and trusted
   review state. Source-quality questions stay in source review. Do not ask an
   author to hand-maintain an `open-questions` definition list.
5. Derive stable entry IDs from project identity, projection kind and canonical
   subject identity. Record algorithm version separately; changing a layout or
   recompiling must not churn navigation/comment/permission identities. A
   breaking identity change requires an explicit migration.
6. Apply server authorization before selection/counts. Derived selectors narrow
   the existing scope and grant no new access. Custom named views may remain as
   optional explicit configuration over the same definitions and policy.
7. Make hand-authored `views` optional for default rendering. The default entry
   follows infrastructure/operator phase policy or an explicit reviewer choice,
   not the first element emitted by an LLM. Preserve source navigation when
   business content is absent, and use bounded views for large models.

Acceptance must compile checked definitions with **no `views` declarations and
no model calls**, then compare repeated output: the same entry identities,
membership, dependency closure and stable ordering. It must cover shared rules,
multiple subjects, no business content, source questions, pending/confirmed
state, permission-limited delivery and bounded large components. Editing a
definition or its review state must update the derived view without editing a
second membership list. Existing custom views require a compatibility path.

The current fresh-agent trial demonstrates that authors can use the existing
contract. It is not the enforcement mechanism for this deterministic design,
and new prompt templates are not an acceptable substitute for its code/tests.

The [fresh-context trial](trials/fresh-business-2026-10-14/README.md) produced
annual-sales performance and category-mix views rather than the working pilot's
annual-review and unresolved-decision grouping. It also proposed a different
rounding policy in the receipt recorded at that time. Both passed structural
checks; neither policy was approved by that trial.
This is concrete evidence of meaningful author discretion, not reproducibility
of one uniquely correct business partition. The trial is one isolated authoring
run, not a guarantee of all agents or production business understanding.

## Integration dependency boundary

Native independent review, source scanning/coverage, comments, model/compiler
iteration and the source-registry bridge do not depend on completing every
Desktop/WebUI browser mode. Native review opens the authorised URL locally;
remote BrowserPanel/viewer control is a separate acceptance path.

As of the 2026-10-20 source/session inspection, viewer polling improvements are
merged in [SudoWork #1273](https://github.com/sudoprivacy/sudowork/pull/1273).
The existing-personal-Chrome application delivery is still in
[SudoWork #1275](https://github.com/sudoprivacy/sudowork/pull/1275), and the updated
cloud worker in [Moss #413](https://github.com/sudoprivacy/moss/pull/413); both were
open when checked. Candidate Electron/model and public Unicode/return journeys
have evidence, but that does not prove the candidate release is deployed.
The 09:07 CST cloud login-after-restart attempt did not complete fixture
navigation. At 09:12 the upstream agent reported that a real restart retained
the login cookie without a duplicate submission; at 09:16 it reported the AI
back on the same signed-in page, awaiting the ordinary tool permission step.
The complete new journey was still being closed at that checkpoint. The earlier
fixture failure is not a diagnosed login-persistence defect. Physical-phone
browser interaction and the optional local extension relay retain separate
acceptance limits.

Proceed with native review and the first registered-source integration. Wait
only where a particular browser path actually requires the unpublished change.
The remaining Sudograph integration work is its own undeployed host adapter;
it can proceed without waiting for a universal browser solution.
