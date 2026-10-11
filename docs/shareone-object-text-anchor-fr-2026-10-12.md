# FR: preserve selected text within a stable object anchor

SudoGraph uses the supported anchors SDK with page-owned, nonblocking marks.
Stable object identity correctly survives folding, layout changes and language
switches. A text selection also supplies its actual selected phrase as the
anchor label. These facts do not give ShareOne a recoverable range within the
object.

## Current boundary

In frontend/src/lib/comments/app-anchors.ts, anchors.select persists the object
IDs, label and optional context. AppDeclaredAnchor in anchor-kind.ts contains no
quote/position selector within that object. The app reveal callback receives
IDs only. The host can return to the object but cannot tell the reader which
occurrence of the phrase was selected. Host-owned marks cover the object; page
marks alone cannot reconstruct the original text range.

Earlier SudoGraph exports incorrectly supplied the entire node title instead
of the selected phrase. That capture bug is fixed in the shared reader. The
original phrase of those older comments was never stored and must not be
invented, silently replaced or inferred from today's title.

## Reproduction

1. Use any SDK-backed dynamic reader with stable ID ticket/42.
2. Select a short phrase inside its detail text; submit a comment.
3. Select another object, change layout or language, and reopen the comment.
4. The object can be revealed, but the original passage cannot be reliably
   highlighted within it. Repeated phrases have no disambiguating selector.

## Requested protocol

- Retain stable object identity and add an optional object-scoped text selector:
  exact quote, prefix/suffix, selected offsets and a content/language version.
- Pass that selector to a reveal-text callback, or provide a documented SDK
  event the reader can handle without downloading comments on every gesture.
- Distinguish object availability from quote availability. A changed passage
  can be unresolved while its object remains visible.
- Preserve the captured quote and context in the sidebar. For older whole-object
  anchors, explain that no recoverable selected passage was captured.
- Page-owned marks must stay nonblocking. Do not introduce document rescans,
  mutation-feedback loops or synchronous network calls during pan/zoom.

## Acceptance

An unchanged passage is highlighted at its original occurrence after a reveal;
duplicate phrases are not guessed. Changed or translated passages retain the
original capture and report unresolved text honestly. Old object comments remain
readable and attached to their object. Pan/zoom performance is unchanged.

This is a ShareOne protocol/UI request. No ShareOne source was modified.
