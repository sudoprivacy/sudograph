# FR: GitLab-backed ShareOne remote sources

## Need and current evidence

Sudograph's managed infrastructure keeps canonical model YAML and revision
history in GitLab. Trusted CI generates review HTML; ShareOne should display
that artifact while preserving the existing share URL and comment anchors.
ShareOne must not become another editable model authority.

Read-only inspection of ShareOne on 2026-10-23 found
`backend/services/remote_fetch_service.py::ALLOWED_REMOTE_DOMAINS` permits
GitHub raw/gist and ShareOne domains only. `validate_and_transform_remote_url`
therefore rejects both `https://gitlab.com/.../-/raw/<commit>/review.html` and
registered self-hosted GitLab origins. The general Git-backed versioning design
does not currently supply this fetch transport or private-project authentication.

## Requested contract

- Support public GitLab raw files and explicitly operator-registered self-hosted
  GitLab origins, with immutable commit references and exact artifact paths.
- Support private repositories using a server-side read-only credential reference
  scoped to the registered project/artifact. Never put tokens into remote URLs,
  generated HTML, comments, viewer responses or logs. Do not mirror private data
  into a public GitHub repository to make the fetch work.
- Check network reachability from the ShareOne fetcher. For GitLab inside a
  customer's network, use an explicitly deployed reachable connector/egress path;
  an origin allowlist alone does not create network access.
- Preserve SSRF/redirect checks, size and UTF-8 bounds, and verify source access
  before replacing the last valid cached artifact. Never forward credentials to
  a different origin. Report inaccessible/revoked sources explicitly.
- Preserve the same share ID and all comments when switching to a new accepted
  commit. Report the pinned source revision and fetch result. Refreshing a pinned
  commit must not silently switch to the branch head.
- Keep repository access and viewer access separate: authorise the resulting
  artifact for its viewers, including cached content after source revocation.
  A ShareOne password is not database row/field authorisation.

## Acceptance

Exercise public GitLab, an authorised private project, an unregistered origin,
credential revocation, an off-origin redirect, an oversized response and a failed
fetch. Confirm last-good handling, exact commit/digest, no credential disclosure,
stable URL/comments and artifact-level viewer permissions. The source is compiled
HTML, not `model.yaml`. Until this capability is delivered, the existing public
Northwind GitHub remote source remains accurately described as GitHub-backed;
GitLab hosting must not be claimed as integrated.

## Implementation and acceptance status (2026-10-26)

The implementation is in [ShareOne PR #320](https://github.com/sudoprivacy/shareone/pull/320),
with [Skill PR #53](https://github.com/sudoprivacy/shareone-skill/pull/53)
and [the API steering fixes in Skill PR #54](https://github.com/sudoprivacy/shareone-skill/pull/54).
The linked pull requests and [production deployment workflow](https://github.com/sudoprivacy/shareone/actions/workflows/main_shareone.yml)
record release status and live acceptance evidence. Application acceptance does
not establish that an actual customer private GitLab is connected.

The implementation pins complete GitLab commits, checks raw response revision,
path and SHA-256, scopes server credential references to project/artifact/publisher,
and defaults private artifacts to owner/collaborator viewing. Explicit public
export requires both an operator grant and an owner viewer-scope change. Cache
bytes are staged before source/digest/access facts are conditionally published.
GitLab remains the content version authority. Operator setup and permission
details are in [the ShareOne deployment contract](https://github.com/sudoprivacy/shareone/blob/main/docs/gitlab-remote-sources.md).

Local validation: 686 backend tests passed, with 17 environment-dependent skips;
the separate real PostgreSQL transaction suite passed all 9 cases, and all 25
standalone Skill API/steering checks passed. Unknown viewer scopes remain restricted;
access gates are rechecked when source or permission changes commit during fetch.
Six real-server/ai-dev-browser acceptance groups cover exact commit/digest,
stable URL/comments, the viewer matrix, source revocation, redirect/oversize
last-good retention and explicit export/revocation. The upstream GitLab transport
is a controlled fixture in that browser suite. A separate real public GitLab raw
API probe verified two different immutable commits and complete response hashes.

The API steering audit also covers credential origin confinement, safe redirect
handling, authoritative source errors, rejected misspelled or empty-scope mutations without
partial writes, unconfirmed publication responses, offline command help, and
runtime-derived creation/scope/error discovery. The service and Skill retain the
existing account identity when a GitLab credential or network route fails.

Remaining customer integration: provide the actual GitLab origin, project and
compiled HTML artifact path; register its read-only credential and permitted
ShareOne publisher; deploy/verify an internal-network connector if needed; then
repeat private-project acceptance from the production fetcher. Neither the
allowlist nor local fixtures prove customer-network reachability. Existing
Northwind remains GitHub-backed and must not be relabelled as a GitLab deployment.
