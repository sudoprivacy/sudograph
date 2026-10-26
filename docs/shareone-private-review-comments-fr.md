# FR: ShareOne comments on authenticated live review pages

## Reproduction and impact

The Sudowork Sudograph project entry **Open review** opens an authenticated
standalone browser at a loopback `/review/<opaque-binding>/` route. The shared
Sudograph renderer supplies stable object/field identities and implements the
ShareOne anchor contract. Structure comes from the committed model; record
pages are requested from the host under its current authorization.

There is no ShareOne shell on this route. Consequently `__SHAREONE__.anchors`
is absent, there is no comment composer, and selecting text cannot create a
thread. Previously the graph still advertised “select text to comment”. A
readable graph and a working ordinary chat are not acceptance of the requested
comment-to-agent workflow.

Read-only inspection of ShareOne at `f60a6a5` found the existing reusable anchor
bridge, comment sidebar, authenticated comment API, synchronization and durable
agent consumers. The frontend shell loads hosted content into its sandboxed
frame; no supported externally hosted live-review widget/delegation entry was
identified. Please confirm an existing supported API, or provide this extension.
This is a missing integration capability, not evidence that hosted ShareOne
comments or their `allow_comments` switch are defective.

## Requested ShareOne capability

Reuse the existing comment UI, thread store, stable anchor/text capture,
reattachment and durable consumers for an authorized native/private live page.
Expose a supported reusable shell/component or equivalent host integration;
do not require a second comment implementation in Sudograph or Sudowork.

- A normal integrated **Open review** entry enables comments by default.
  Report separate readiness for content, authenticated comment submission and
  event subscription. An injected queued anchor stub alone is not readiness.
  Configuration, authentication or service failures must be visible and
  retryable. A read-only preview may remain available with an explicit label.
- Register a review/comment space without requiring the private graph HTML,
  source records or database credentials to be uploaded to public storage.
  Preserve the host's live same-origin record routes and authorization. A
  ShareOne read token is not a source/export permission; a readable local URL
  must not become a public share.
- Define identity pairing/delegation explicitly. Keep provider secrets and
  owner API keys out of HTML, URLs, IPC replies, prompts and browser storage.
  The host binds its authenticated principal/project/conversation to the
  permitted ShareOne space, and checks access again on every operation. Do not
  infer account equivalence from a display name or grant all viewers the owner
  identity. Keep protected comments private to their authorized participants.
- Keep one canonical model and stable target IDs. Attach comments to the share,
  registered project, observed model revision, canonical targets and actual
  selected passage. Layout, language changes and switching views preserve
  target identity. Hidden, pending and missing remain distinct states.
- Document the origin/window handshake and CSP/CORS requirements for Desktop
  loopback and cloud-hosted review. Reject messages from other frames/origins,
  unrelated shares, stale bindings and revoked sessions. Do not introduce a
  wildcard credentialed proxy or let a page choose arbitrary upstream URLs.
- A comment can be saved while agent delivery is temporarily disconnected;
  display its delivery state and retain/retry the durable event. Never report
  delivery merely because a comment was stored or a process was spawned.

## Sudowork/Sudograph integration owned here

ShareOne should not implement a new agent runtime. The existing
[bound-session and event contract](review-session-events.md) remains the host's
responsibility:

1. Persist an authorized space/project/conversation/model binding. Multiple
   authorized conversations may subscribe; never guess the currently active one.
2. Receive human owner and visitor comments through ShareOne's durable consumer
   API, filter self-generated agent replies, and deduplicate event/destination
   pairs. ACK only after durable insertion into the host's existing inbox.
3. Wake an idle bound conversation or queue to its running agent through the
   existing mailbox. Do not start a second ACP process over an active session.
4. Recheck current access and read the thread/current model before editing.
   Pass all changes through the canonical compiler/writer. Publish graph and
   context together; notify/reload the same review to the accepted revision.
5. Reply to the actual thread with the result or an actionable failure. Resolving
   a comment does not approve a business definition or authorize source writes.

## Required joint acceptance

- From the actual authenticated **Open review** action, submit a real field or
  business-definition comment, reload and reopen the same stored thread.
- Deliver that human comment to the bound real LLM conversation, including
  delivery while it is busy. Verify one accepted turn after crash/retry and
  no loop on the agent's own reply. Pan/zoom must not wake the agent.
- Have that agent change a definition through checked tools. Observe the new
  revision on the same review with the original thread/anchor preserved and
  the raw database unchanged.
- Repeat after logout, revoked access, account switching and session expiry;
  unrelated accounts/projects/shares must not read or submit protected comments.
- Exercise exact selected text, folded fields, languages, refresh/reconnect,
  Desktop Chrome and the real WebUI standalone viewer. Measure interaction
  latency with the existing Northwind graph; a simulated SDK is not this test.

## Current status

This request documents the missing provider contract. No ShareOne implementation
or production deployment is claimed. The local renderer now distinguishes a
missing/queued bridge from a connected bridge and no longer advertises comments
on an unconnected page. Its browser check explicitly records that real comment
submission and comment-to-agent delivery remain unverified. Full review remains
blocked until the provider and durable host adapter pass the joint journey.
