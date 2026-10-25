# Canonical model review transport

`compiler.review.ReviewGateway` connects the native renderer to the transactional
model store. It reuses `compiler.gateway.Authority`, including the existing file
capability and Nexus adapters. Source registration, actor selection and model
writes are absent from the review API. A review is a generated presentation of
the same committed model that supplies agent context; it is not another model
authority.

## Registration and authorization

An operator can configure the loopback server with canonical stores instead of
legacy `views`:

```json
{
  "policy": "private-policy.json",
  "workspaces": {"support": "models/support.db"}
}
```

Run `python -m compiler.serve deployment.json --port 8765`. The existing policy
format grants `read` and, separately, `export` on each named resource. Policies
are re-read for every operation, including discovery, HTML and record paging.
An authorized resource currently covers its complete registered model and
source scope. Do not register an unrestricted store for a caller who should
only see selected rows or fields. The existing scoped source Gateway has a
different projection contract; its catalogue adapter is still required before
claiming customer row/field authorization here.

The default HTTP credential resolver accepts a bearer header. An embedding host
can pass `handler(gateway, credential_resolver=host_session_resolver)` to reuse
its existing authenticated session. The authority still checks the returned
credential on every request. There is no new login system, no identity selected
by the browser, no root-token fallback and no credential in a URL or model.
The browser sends requests to the same origin with its host session; a remote
viewer must preserve that execution browser/session. The stock command alone
does not provide a desktop login or the Moss/WebUI identity adapter.

## HTTP and renderer contract

`GET /review/<percent-encoded-resource>` returns the shared renderer's HTML after
authorization. It contains the committed structure, context version and a
same-origin `/v1` transport descriptor. With the normal live-source profile it
contains no record pages or private DSN. Source fields retain the existing
stable identities and the same record buttons, paging and binary download UI.
If an explicitly frozen store embeds record bytes, both graph and HTML delivery
additionally require `export`. A graph read cannot bypass the bulk-export grant.

`POST /v1` takes `view`, `operation` and optional `params`:

| Operation | Result | Permission |
| --- | --- | --- |
| `head` | Current model revision and context digest | `read` |
| `graph` | Committed native model | `read` |
| `context` | Deterministic packet from that revision | `read` |
| `page` | Bounded, version-bound source records | `read` |
| `export` | Committed portable HTML without a live transport binding | `export` |

The existing `{"operation":"contract"}` discovery request lists only authorized
resources. Page parameters are `revision`, `context_digest`, source-object `id`,
optional `offset` and `limit` (1–100). The renderer requests 50 rows at a time.
The gateway delegates to the same `Workspace.context_read` and source reader as
the agent. A page returns its requested revision and digest; the renderer refuses
a response for another model, object or offset. Exact reads of retained historical
revisions remain possible after a model edit, with current authorization and
source-schema validation. Live page observations remain distinct from catalogue
counts and from a source snapshot: different pages can observe source changes.

There is no record-page cache in this HTTP path. Responses use `no-store`.
Revocation prevents subsequent reads; it cannot erase previously received bytes.
The export grant does not implicitly include live-page access. Failed reads clear
the previous page and show a localized error. Late responses cannot overwrite
a different selected panel. Reload loads the latest successful model revision;
automatic host-driven refresh and safe active-agent context updates are separate
integration work.

## Acceptance

The unit suite exercises real HTTP, resource isolation, export separation,
revocation, exact page parameters, source drift and checked edit/reload behavior.
It also covers JSON normalization before baseline pinning: integer-keyed compiler
maps must not change the pin after storage. This fixes new registrations; existing
history is not silently rewritten. Read-only scanner paths explicitly close
their SQLite connections instead of waiting for garbage collection.

Install `playwright==1.61.0` and `python -m playwright install chromium`, then run:

```sh
python -m tools.accept_review --receipt review-acceptance/receipt.json
```

`tools.verify` and CI run this same real Chromium journey on synthetic,
unrelated SQLite data: zero
preloaded rows, first/next/last pages, binary and NULL values, live source changes,
keyless-view labeling, a checked model edit followed by reload, anonymous denial
and revocation. It retains screenshots and a receipt. An optional
`--ai-dev-browser-port <unused-port>` additionally reads and screenshots the same
owned browser through ai-dev-browser. This proves the native review transport,
not production login, ShareOne comment delivery, cloud routing or row/field
authorization.

## Authenticated native-host adapter

`compiler.review_host` is a private stdin worker for a host which has already
authorized a request. Deployment-owned arguments select its store, actor and
registered resource. Input can only request the read operations above, or HTML
with a checked same-origin endpoint. It cannot select a store, actor, resource,
source connection or permission. Export is denied unless the trusted invocation
explicitly supplies `--allow-export`; the desktop adapter does not supply it.
This worker is not a public endpoint or a builder tool.

Sudowork's `SudographReviewHost` provides a loopback route within the current OS
profile. It binds an ephemeral review session to the persisted project and Studio
conversation and rechecks ownership on every read, including after a compiler
read finishes. The model comes from the existing host registry, not another
catalogue. Each launch has a random URL reference and a separate 30-minute,
path-scoped HttpOnly cookie. The reference does not authorize access. Credentials
are not part of URLs, generated HTML, model context, IPC replies or MCP tools.
The trusted browser host must install the cookie through its existing controlled
browser before navigation. Host/Origin checks and bounded JSON requests apply;
there is no anonymous fallback. This is OS-profile authorization, not cloud tenant
or row/field policy enforcement.

The HTTP/worker adapter and real Chromium cookie/paging journey are implemented.
The production browser-host credential handoff and UI launch entry remain
unconnected. The acceptance fixture installs the cookie; it does not establish
Desktop/WebUI launch, login, browser-control leases or ShareOne comments.

Run the same native reader acceptance through the real TypeScript HTTP host:

```sh
python -m tools.accept_review --sudowork ../sudowork --receipt host-review/receipt.json
```

This reuses the existing browser journey for paging, NULL/blob values, live source
updates, checked edit/reload, anonymous denial and revocation. The receipt states
the launch limitation explicitly. `tools.accept_workspace_adapter` additionally
accepts the host route against the private compiler worker without a browser.
