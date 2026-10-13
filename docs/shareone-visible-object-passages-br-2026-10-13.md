# Visible object passages remain pending until explicit reveal

## Reproduction and evidence

On the private working review at
https://s.shareone.vip/s/sudograph-northwind, select part of a visible node label
and post a comment. Leave the document and view unchanged. The object has a
stable `app_declared` identity and a captured `text` selector with exact text,
context, offsets and a content version.

The object marker remains visible, but the selected passage is not painted as
a standing highlight. The sidebar reports that the selected passage has not
been located yet. Owners also see a `Reattach target` action, which can suggest
a lost target even though it is an available action rather than a failed match.

In an ai-dev-browser check against the unchanged live revision on 2026-10-13,
all ten recent object-passage comments matched their existing label text and
content versions through the public SDK `resolveText` method. Explicit
`app-anchor-reveal` requests restored each passage and returned `resolved`.
Before reveal, reports contained `state: visible` and `text: pending`.
No test comments were submitted. Private discussion text is not reproduced here.

The current SDK's `aResync` forwards only unique object IDs to `on('resync')`.
It retains the grouped passage selectors internally but does not ask the page
to restore visible passages. `revealAppAnchors` is the path that calls
`on('reveal-text')`; it also invokes navigation/reveal. Sudograph cannot use
the ID-only resync callback to reconstruct a captured selector it has not received.

## Requested generic behaviour

- Offer a supported passage-resync callback containing comment IDs, object IDs
  and exact selectors. Restore visible passages without switching the view,
  changing selection, opening details or moving the camera.
- Keep hidden passages pending/hidden. Restore them when their readable surface
  becomes visible; reject changed revisions or ambiguous matches honestly.
- Distinguish pending recovery from failed recovery. Present `Reattach target`
  as an optional repair action, not evidence that a freshly created target failed.
- Allow activating a specific passage's comment ID under page-owned marks.
  Object-only `activate(id)` cannot distinguish several passages on one object.
- Respect the host's hide-marks controls for page-owned marks/passages as well
  as host overlays; keep the text and object channels explicit.

Do not restore passages by scanning the complete source snapshot. Recovery should
run on changed visible text surfaces or new selectors, never on every pan/zoom.
Use native ranges/CSS highlights without input-catching text overlays.

## Separate intermittent report

The reviewer also reported that posting a comment sometimes does not focus its
new sidebar thread. This was not reproduced in the read-only browser check; no
fake comments were posted. Please test the authenticated submit-success path,
including a scrolled sidebar, an active older thread, polling/resync during
submission, and several comments on the same object. Preserve the new comment
ID through refresh and scroll after its thread is mounted.

Read-only inspection of `frontend/src/components/comments/CommentSidebar.tsx`
found a useful check point: its auto-scroll effect sets
`handledAutoScrollIdRef.current` before the delayed callback checks that the
comment element and scroller exist. A missing element exits without a retry,
while the same ID is already considered handled. The callback also scrolls to
`scrollHeight` instead of the target card position. Test a filtered/unmounted
thread or a view/filter change within that delay. This is a source-level lead,
not a claim that the intermittent production report was reproduced.

## Scope

Sudograph's comment-marker button now uses the existing supported `activate(id)`
method. This improves object-thread access without blocking node clicks.
The standing passage and precise comment-ID requests above require a ShareOne
SDK/shell change. No ShareOne source was modified for this report. Existing
reattachment support is present; old uncaptured text must still be rebound
explicitly by its author, never guessed or silently migrated.

## Deployment follow-up, 2026-10-14

ShareOne Skill v1.11.0 now documents `resync-text`, `marks`, `resyncText()` and
`activateComment(commentId)`. The local ShareOne `app-anchors.ts` also implements
these interfaces. Sudograph implements the documented page callbacks in its
shared renderer; local browser checks verify exact native ranges, cached batches,
request-scoped cancellation, hidden-detail handling and independent mark visibility.
Twenty camera updates caused zero readable-text scans and no graph rebuild.

The published Sudograph revision is
[`f8af300`](https://github.com/sudoprivacy/sudograph/commit/f8af300ec1f4c4dc54cd28874d95aa8124afe020).
Its source-review presentations and whole-file publication are verified. However,
the anonymous production iframe SDK still exposes only `configure`, `select`,
`report`, `reportText`, `resolveText`, `activate` and `on`. Both
`typeof window.__SHAREONE__.anchors.resyncText` and `activateComment` return
`undefined`. Its `on` implementation also lacks the new marks/passive callbacks.
The shell asset is `/assets/share-shell-DXITiRSp.js`. Reopening the share with
Chrome network caching disabled produces the same result.

Please check that the frontend shell and generated iframe SDK from the new
implementation are deployed together, and verify the public share host rather
than only source tests or updated skill documentation. Keep this issue open
until existing unchanged passages restore passively, mark switches affect both
channels, and native passage clicks activate the exact existing thread.
No test comments were submitted and no private comment text is included here.
