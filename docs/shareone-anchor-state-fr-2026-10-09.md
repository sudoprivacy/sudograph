# FR: distinguish hidden, pending and unresolved comment anchors

Dynamic graph readers need an honest anchor status and a stable way to return to
the target. Request from the owner review of
https://s.shareone.vip/s/sudograph-northwind, thread
`f6d595fb-30e0-40e5-940d-fe67e8b18937` and reply
`8c7df5d8-c1c5-45c2-ac9a-df415894f213`.

## Observed cases

The owner sometimes sees “Anchor unavailable” after switching presentations or
changing the inspected node. This thread's stored `highlighter_data` is a legacy
text anchor for “辖区”; it does not contain a stable source-object identity. A
separate field comment on Products.ProductName uses `app_declared` and its
compiler-owned ID. These cases need different explanations.

The current SDK already accepts `visible`, `hidden` and `missing`, and emits
`unreported` for IDs whose location/existence the page has not reported yet.
`use-comment-annotations` maps missing and unreported to the same `unavailable`
availability; `CommentThread` distinguishes hidden from unavailable only.
This is a feature request for more precise status and a transition path for text
anchors, not a claim that every unresolved text target is known to exist.

## Proposed behaviour

| Evidence | User wording | Action |
|---|---|---|
| Page confirms the identity and supplies a rectangle | Target available | Locate/highlight |
| Page confirms the identity, with `state: hidden` | Known target, outside the current view | Reveal through the page's callback |
| Page has not reported yet | Waiting for the page to locate the target | Retry after page state settles |
| Page explicitly reports every ID missing | Target no longer exists in this version | Preserve quote/context and expose history |
| Legacy text matching fails, without an identity | Text target could not be located; content may have changed | Retry, or offer a confirmed relink |

Do not label an unresolved quote “known but hidden” without identity evidence.
Do not reattach a legacy quote to an arbitrary node with the same display name.
Retain partial status when only some identities in a region remain available.

For new text selections on named objects, support a page-supplied stable identity
through a documented optional DOM/SDK affordance, retaining quote/context for
reading. SudoGraph now calls `anchors.select` for both source objects and fields;
an ordinary inspection click does not create a comment. Existing text comments
must retain their semantics until an explicit, confirmed migration is available.

## Acceptance

- Folding, switching presentation, paging, relayout and language changes preserve
  an app-declared comment's identity and offer reveal when the target is known.
- An unanswered ID is not reported as deleted, and a deleted ID is not reported
  as temporarily hidden.
- A legacy quote appearing in several places is not silently linked to the wrong
  source object.
- Source-object selection can create a stable comment as source-field selection
  already can; cancelling the composer creates no comment.
- Repeated pan/zoom does not rebuild the document text index or add polling on
  every pointer frame. Reuse the existing page reports and deduplicated state.

The blank-canvas inspector issue is fixed in SudoGraph's shared reader and is
separate from this ShareOne request.
