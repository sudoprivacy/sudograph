# Bound review sessions and durable events

This is an integration contract, not a claim of a deployed Sudograph adapter.
It reuses existing Sudowork conversation/workspace and browser-session binding,
ShareOne durable event delivery, and Sudocode's mailbox transport.

## One explicit binding

When the agent opens a review, the host records the authorised tenant/project,
conversation, model revision, share and execution-browser session. Extend the
existing host registry; do not create another editable model or ask a prompt to
remember which conversation a browser belongs to. A link carries an opaque
binding reference, not credentials or authorization.

The host resolves that reference and validates current ownership/scope before
opening a conversation, delivering an event or loading agent context. There is
no fallback to the latest active agent, a guessed local session path or a model
chosen from page text. Multiple bound reviewers/conversations require explicit
fan-out configuration. Static unbound examples show that state honestly.

## Human workflow and browser arbitration

The business workflow requires no extra Return to AI / Return to human buttons.
An agent can request review through a structured host transition; a user can
continue through the bound conversation, a comment or an accepted model change.
The host routes those events without a workflow prompt.

The shared browser still needs server-enforced mutual exclusion, operation
epochs and a barrier for in-flight input. Reducing handoff buttons does not
permit concurrent AI/human writes or treating an idle timer as human consent.
Human review gestures must not be replayed into another tab or source revision.
Chat/comment intent can resume the bound agent under allowed capabilities;
it does not automatically grant browser input while a human is interacting.
The upstream browser currently exposes explicit takeover/return controls. A
low-friction review mode needs its own accepted lifecycle over that protocol.

## Reuse the notification and inbox layers

ShareOne already offers durable agent consumers, not only email/Feishu delivery.
Its supported receiver contract provides event references, leases, renewal,
ACK/release and at-least-once redelivery. Use its command receiver to enqueue a
typed external-review event in the existing host/session inbox. Reuse the
Sudocode mailbox delivery primitive behind `send`, not an LLM deciding to call
`send` and not a forged peer-agent identity.

The current skill defaults to visitor-only delivery. Business owners' comments
must also arrive. Until a selective human-actor option exists, use all-actor
delivery and filter owner/visitor events in the trusted receiver; agent replies
advance the cursor without waking the agent again.

1. Validate event tenant/share and resolve the registered binding.
2. Deduplicate by event ID and durably enqueue references to the parent thread,
   model revision and canonical targets. Keep credentials and full record pages
   out of the event.
3. ACK only after durable host acceptance. Crash/retry must not duplicate a turn,
   a publication or a comment reply. Use stable idempotency keys for side effects.
4. Wake an idle session or queue for the active host session. Do not launch a
   second `scode acp` process over the same active conversation.
5. Read the current thread and current revision before editing. Enforce access
   again after revocation and reject stale revisions.

Comment events and accepted semantic model revisions are different sources.
The managed model publisher is authoritative for model/revision changes; the
bridge should extend/reuse the notification framework rather than parse DOM
text to infer a business edit. Panning, zooming, dragging layout or opening
fields must not wake the agent. Comment resolution is not business approval.

## Browser acceptance to share with its owner

- Open the large review surface from a bound task and recover that same binding
  after refresh/reconnect on Desktop and WebUI.
- In a real authenticated WebUI viewer, select an exact phrase, comment on its
  canonical object and reopen the same thread after zoom, expansion and language
  changes. A local native-page check does not establish this.
- Verify local/remote clipboard behavior, Unicode/IME composition and selection
  gestures. An image viewer cannot assume native DOM clipboard behavior.
- Provide the requested review workflow without mandatory business handoff
  buttons, while preserving the server lease and rejecting stale queued input.
- Measure pan/zoom and comment feedback latency with the actual graph and frame
  transport. Existing source-reading/model-roundtrip tests are not that test.
- Keep view-only review available without installing an extension when no local
  browser control is requested. Report unsupported device/transport combinations.

These are concrete integration acceptance gaps/requirements, not proof that each
upstream feature is defective. The adapter and semantic-change notification path
remain implementation work. Do not start background consumers merely by reading
this design; deployment must supply the explicit scope and bound inbox.
