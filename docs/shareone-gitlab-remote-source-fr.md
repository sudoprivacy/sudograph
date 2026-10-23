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
