# A walkthrough of the three phases

The previous centered four-card guide explained concepts but did not navigate
the product. The manual walkthrough now uses pinned Driver.js 1.4.0, the same
library used by SudoAPI. It prepares the actual reader state, waits for the
target, and anchors a short instruction to that control or piece of content.
See the [interactive tour API](https://driverjs.com/docs/interactive-tours).

| Phase | Actual reader actions | User decision |
| --- | --- | --- |
| 1. Check source data | Open coverage, find an existing object, inspect a field, read a real keyed row and optional source question | Did we cover the right source, and does the observed field/value mean what we thought? |
| 2. Agree business meaning | Open a business subject, inspect its definition and unresolved issue, locate the comment action | What is the intended business meaning or correction? |
| 3. Use reviewed knowledge | Preview the existing context compiler's output and source question bank; show the workbench connection boundary | Is the agent receiving the right knowledge, and has its reading/understanding actually been tested? |

Examples are selected deterministically from delivered canonical identities,
preferring source fields referenced by the selected business subject. There are
no Northwind names, fabricated records, automatic comments or invented results.
A missing business overlay explains the next phase at the relevant navigation
surface instead of manufacturing definitions. Records are omitted from the tour
when they are unavailable. The walk remains usable with source-only projects.

This covers the reviewer's path from an already-generated graph. Connecting a
source and starting its scan belong to the host connection UX; the host adapter
must provide those steps for an eventual cross-application onboarding flow.

## Stage-three preview is not a simulated agent

`compiler.app` invokes the existing `compiler.context.Reader.pack()` and embeds
the derived blocks once, without repeating `text` and `appendSystemPrompt`.
The reader displays that result; JavaScript does not compile a second prompt.
The **Agent context** panel preserves unresolved review states and reports that
the static reader is not bound to a live workbench agent. There is no fake chat,
business answer or evaluation score. Record rows are not preloaded in context.

The [bound-session contract](review-session-events.md) defines the missing host
entry and durable notifications. This boundary must remain visible until that
integration is actually accepted.

## Controls, cleanup and performance

The default is manual start from **Quick tour**. Operators may disable it;
first-visit auto-start, browser preferences and the no-longer-needed dismissal
checkbox have been removed. An explicit `?guide=start` remains a replay action.
Phase buttons jump between the three chapters; Previous/Next and Escape/Close
are available. Exit restores the user's selection, navigation state and camera.

Only explicit walkthrough steps navigate or lay out a different view. Driver
handlers exist only while the walkthrough is active and are removed on exit.
There is no background polling, canvas-movement subscription or model call from
the inactive guide. Popovers and their targets are checked in the real browser
at desktop and phone viewport sizes. Physical-device and remote-viewer acceptance
remain separate. Missing targets produce a visible failure rather than silently
falling back to a centered card.
