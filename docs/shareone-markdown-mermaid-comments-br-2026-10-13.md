# ShareOne BR/FR: stable Mermaid region comments and readable diagrams

Reproduction page: <https://s.shareone.vip/md/sudograph-architecture-review>.
It is an ordinary remote-bound Markdown page with comments enabled. The diagram
source is public, and all 15 nodes and 22 edges render successfully. No test
comments were posted and no existing comment was changed during reproduction.

## BR: unchanged nodes receive new element identities on reload

1. Open the reproduction page and locate the flowchart's `PUBLISHER` node.
2. Build its element-point anchor using the shipped `element-identity.ts`
   implementation. It selects the node's unique SVG `id`.
3. Reload the same page without changing its Markdown or Mermaid source.
4. Resolve the original anchor against the newly rendered document.

Observed selector before reload:

```text
#shareone-mermaid-1791879918296-1-0-flowchart-PUBLISHER-10
```

Observed selector after reload:

```text
#shareone-mermaid-1791880171238-1-0-flowchart-PUBLISHER-10
```

The readable node label is identical, but the original selector matches zero
elements and `findElementByAnchor` returns null. This is a reproducible anchor
resolution failure before saving any comment. The broader persisted-comment
symptom follows from using that selector; it was not tested by creating comments
in the user's discussion.

The Markdown renderer currently allocates each Mermaid render ID using
`Date.now()` and `mermaidRenderSequence` in
`frontend/src/pages/share-shell/main.tsx`. Mermaid propagates that prefix into
node IDs. `stableSelector` in
`frontend/src/lib/comments/element-identity.ts` prefers a unique `id`, and
`findElementByAnchor` deliberately refuses a structural fallback when that ID
is missing. The refusal is appropriate; the renderer has supplied a temporary
identity as though it were durable.

Expected: refreshing an unchanged Markdown diagram preserves the identities of
its nodes and the ability to locate their existing comments. Use a stable
diagram identity plus the source node identifier, independent of render time,
theme and node ordering. Multiple diagrams need distinct durable namespaces.
Do not compensate by guessing from identical labels or silently rebinding old
comments.

Regression checks should cover reload, light/dark re-rendering, insertion of an
unrelated node and two diagrams containing a node with the same source name.
A genuinely removed source node must remain unresolved. Test this in the
Markdown viewer with comments enabled, not only the pure anchor helper.

## FR: inspect a wide Markdown diagram at a readable scale

The same diagram is fitted into the article width. Its labels become too small
to inspect, and the native Markdown viewer offers no diagram expand, pan or
zoom controls. Its SVG is complete; missing content is not the problem.

Provide an expanded diagram view, fit and 100% controls, wheel zoom and drag
pan. Keep the original diagram source, all labels and comment identities.
Scale from the SVG's original viewBox, and report changed comment coordinates
without rerendering the graph or rescanning all document text on every gesture.
The expanded view should work with the comment sidebar open and on mobile.

Until the BR is fixed, reviewers can select text in the generated node and
relationship inventories below the diagram. The inventories are generated from
the same README source and contain the complete labels and relationship
annotations. Their text comments do not depend on Mermaid's temporary SVG IDs.
