# FR: audited reattachment of legacy comments without a captured text range

Status update (2026-10-13): ShareOne PR #306 implements the audited reattachment
UI/API and is deployed. Production thread metadata exposes `viewer_can_reattach`
and `anchor_binding`, and the binding-history endpoint is available. No existing
review thread was migrated automatically: the commenter must explicitly select
and confirm the replacement. The reproduction and request below are historical.

Date: 2026-10-12. Scope: ShareOne's generic comment UI/API, not a Northwind
special case. This is a feature request for legacy-comment repair, not a request
to infer text that was never recorded. ShareOne source was inspected read-only.

## Already implemented

The object-scoped text-selector SDK and SudoGraph reader integration now capture
the exact phrase, prefix/suffix, UTF-16 offsets and language/content revision.
Production protocol verification recovered a new selection and refused a changed
revision. This supersedes the protocol gap in the
[earlier text-anchor FR](shareone-object-text-anchor-fr-2026-10-12.md).

The inspected ShareOne tree at
`96b331ae79a236aecf80dbdfcea179302ddeb0e5` already:

- Stores optional `AppDeclaredAnchor.text` and does not infer it from `label`.
- Distinguishes the object's availability from the selected passage's availability.
- Shows an explicit notice when an object comment has no captured text range.
- Preserves the original comment and replies when text recovery fails.

Do not reimplement these completed parts. The remaining gap is a supported,
auditable way for a person to attach an existing thread to a newly selected target.

## Missing capability and reproduction

1. Create a comment through an older SDK-backed dynamic page that stores stable
   object IDs, a label and optional context, but no object-local text selector.
2. Upgrade to a reader that supports exact passage capture and recovery.
3. Open the old comment. Its object can still be found, but the original selection
   cannot be recovered: the label might be a whole object title, not the phrase
   the person selected.
4. Attempt to select the intended phrase again and attach the existing thread to
   it. No supported reattachment action was found in the inspected UI/API.

`backend/schemas.py::CommentUpdate` accepts only `content`.
`backend/routers/comments.py::update_comment` edits content and refuses editing a
top-level comment that already has replies. `CommentThread.tsx` and
`CommentAnchorNotice.tsx` provide reveal/retry/history actions, but no reattachment
flow. Ordinary content editing is therefore not a suitable migration mechanism.

## Requested behaviour

Add a **Reattach target** action for an authenticated commenter or another actor
explicitly authorised by the server's thread-management policy:

1. Explain that this creates a new binding; it does not restore an unrecorded
   historical selection. Retain the original quote, context and anchor evidence.
2. Ask the person to select the intended current passage/object. Show a preview
   of the proposed target, selected phrase and current content revision before
   confirmation. Cancel leaves the thread unchanged.
3. Use the same SDK capture contract as new comments. A supported dynamic page
   supplies the stable identity and object-local selector; an unsupported page
   explains its limitation. Do not synthesize an identity or selector from a label.
4. Save an append-only binding revision with the previous binding, replacement,
   acting user, time and reason. Keep the same comment ID, original author,
   creation time, discussion and replies. Retain the original capture separately
   from the effective current binding; the UI must make that distinction clear.
5. Authorise the mutation on the server and reject a stale binding revision.
   Retargeting to another object must be an explicit, visible choice. A binding
   never grants access to data the viewer is not authorised to inspect.
6. Notify other open readers through the existing comment update stream. Resolve
   the replacement only after confirmation; do not introduce rescans, repeated
   network calls or layout work during pan/zoom/drag.

Reattachment must not automatically resolve, dismiss or reopen the business
feedback. Anchor availability and whether the feedback has been addressed are
independent. Comment content editing restrictions need not be weakened just to
support a thread that already has replies.

## Recovery limits

A saved original quote plus its original source/version and sufficient matching
evidence may support an explicit, verified migration proposal. Repeated phrases,
changed versions and ambiguous targets must remain unresolved.

If the selected phrase was never stored, software cannot reconstruct it from
the title, comment time or current Git branch. Historical source inspection can
help a person choose a new binding, but cannot prove an unrecorded selection.
Do not silently backfill legacy selectors or reinterpret a genuine object-only
comment as a text comment. Preserve the old evidence and offer reattachment only
when the person wants it.

## Acceptance

- A legacy object-only thread with replies can be reattached to a newly selected
  phrase without losing its identity, replies or historical capture.
- The sidebar shows the replacement and audit history; the exact phrase can be
  revealed through the supported callback on the matching content revision.
- Cancel, unauthorised mutation, concurrent replacement, unsupported capture,
  duplicate phrases and changed revisions fail honestly without changing history.
- Refreshing or opening a second reader presents the same effective binding.
- Genuine object-only comments remain valid without an invented selected passage.
- Retargeting leaves feedback status unchanged and adds no per-gesture text scans,
  graph layout or synchronous network requests.

No private review comments are reproduced here and no ShareOne code was changed.
