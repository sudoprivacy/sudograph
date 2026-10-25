# Managed deployment and automatic publication contract

Scope clarification, 2026-10-24: this document specifies the implemented,
optional **GitLab model-publishing prototype**. Its approval checks remain
enforced when that path is selected. It is not the default interactive model
editing workflow: ordinary checked YAML/graph edits must update review/context
without a merge request or human release approval. The host adapter for that
loop remains to be connected. Production source writes require a separate
reviewed executable plan and executor; this prototype does not implement them.
See the [current architecture](../README.md#where-this-sits).

Status: private-project provisioning, operator-owned native CI, authenticated
GitLab approval events and independent managed publication are implemented.
The complete isolated Docker deployment passed
[13 end-to-end checks](trials/gitlab-managed-2026-10-13.md).
Customer Nexus SSO, browser OAuth, automatic ShareOne delivery and approved source
write-back are not connected by that acceptance. Existing-instance TLS/network
registration also requires acceptance in that customer's environment.

## Ownership

An installation of this optional delivery path includes a dedicated GitLab
workspace/project for the customer model, automatic CI, pinned compiler/renderer
workers, a review reader and a trusted publishing path. Its deployment owner provisions and
maintains these together. Requiring the customer, a business reviewer or a fresh
agent to discover a Python command is not an acceptable enforcement mechanism.

The GitLab project can live in a managed instance or the customer's authorised
self-managed instance. A dedicated project does not require a separate GitLab
server per customer. Network location, tenant separation and administration are
deployment choices; the enforced workflow must be the same in either location.

| Actor | Responsibility |
| --- | --- |
| Business reviewer | Inspect fields, records and definitions; comment and make authenticated review decisions. |
| Agent | Submit source-bound configuration or business-definition changes; receive compiler reasons and repair directions; revise proposals. |
| Sudograph deployment owner | Provision the project, runner, service identity, source registrations, branch protections, checks and publication boundary; manage upgrades. |
| CI worker | Run the pinned checks automatically for the submitted revision; return failures and reviewable artifacts. |
| Trusted publishing service | Authenticate the request, resolve allowed inputs, build and verify the exact deliverable, apply publication policy and retain the receipt. |

`python -m compiler.check_export` is a worker entry point and optional developer
diagnostic. Its existence is useful, but its invocation must be automatic inside
the managed workflow. The agent does not decide whether to run it.

## Version authority

Git stores checked model configuration, canonical business definitions and their
versions, review references, and proposed source migrations. The original source
systems remain authoritative for database/document facts. Generated HTML is a
derived, reproducible deliverable, never an independently editable model.

Views, comments and permissions reference the same canonical object/field and
business identities. An additional view must not allocate another copy of a
definition. Historical artifacts retain their source and compiler versions;
the frozen phase-one acceptance snapshot remains immutable.

## Enforced path

1. Deployment registers the GitLab project, allowed source connections, model
   location, compiler version, view policy and output destinations. These are
   operator-owned configuration, not writable model YAML or agent claims.
2. The agent submits model changes through the managed authoring interface and
   review branch. It has no authority to install a different publisher, edit its
   policy, supply another source path, or use its publication credentials.
3. Submission automatically triggers validation and compilation. The worker uses
   the installed, pinned compiler rather than executing arbitrary scripts from
   the model branch. Failed identities, bindings, expressions or references
   return actionable diagnostics; no successful deliverable is produced.
4. The registered GitLab project uses merge-request checks and a protected target
   branch. A successful required pipeline is a merge condition. Changing or
   skipping the branch's CI must not create a valid publication: the publisher
   enforces its own checks using operator-controlled code and policy.
5. The publisher authenticates and authorises the exact revision and destination.
   It compiles from the permitted checked inputs and registered sources using
   the pinned compiler, then verifies the resulting complete reader. If a worker
   artifact is reused, the publisher independently verifies its bytes against a
   trusted checked model; an embedded model or caller-supplied success flag is
   not sufficient. Source reads and view projection remain permission-scoped.
6. The publisher records the input revision, compiler version, source snapshot
   evidence, effective authorised view, complete artifact hash and applicable
   approval/review result. Only that verified deliverable can reach the registered
   reader/share. Source or policy changes after the build require revalidation;
   the receipt identifies a snapshot, not a claim that a live source never changes.

Publishing a clearly labelled, unconfirmed proposal for business review is a
normal part of phase two. Passing compiler checks does not turn that proposal
into an approved business definition. Acceptance and source write-back have
their own authenticated approval requirements. Source write-back additionally
uses the separate [approved migration contract](source-writeback-acceptance.md);
generating or publishing a graph never grants database write permission.

An unrelated direct upload to another hosting service is outside this boundary.
The managed reader must consume only releases accepted by its own publisher.
Static ShareOne content review is also separate from Sudograph model validation
and per-user data authorisation.

## Deployment acceptance

Accept the managed path only after a disposable, deployed workspace proves:

- A fresh agent submits a valid definition without knowing a verification command
  and receives an automatically compiled, verified review artifact.
- Invalid bindings, conflicting identities and unsupported expressions fail with
  a repair direction through that same interface.
- Hand-edited HTML, a false success flag, an omitted/skipped gate and a model-branch
  CI change cannot publish a managed release.
- A different input revision, source registration, artifact hash or destination
  cannot reuse a prior verification or approval receipt.
- Authorised draft publication preserves unreviewed status; business acceptance
  and source-write requests cannot be self-approved by the agent.
- History and an authorised rollback regenerate or select the verified historical
  artifact while preserving the original review share and stable identities.

Repository unit tests cannot substitute for this deployed end-to-end acceptance.
The acceptance installs actual GitLab CE and Runner images with separate
synthetic accounts and an unrelated SQLite source. It verifies the native commit,
CI, approval, hook, merge, reader and revocation paths. It never writes to the
registered source database. Unit protocol fakes remain boundary tests, not a
substitute for this deployment.

Installation and the managed `contract`, `submit`, `status` and authenticated
release interfaces are in [infra/gitlab](../infra/gitlab/README.md). Every caller
is checked against both its operator-registered model role and its current GitLab
project membership. CI cannot be supplied by a model branch. Git owns identity
history; the publisher's identity index is derived from committed definitions.

## GitLab references

GitLab documents [protected branch permissions](https://docs.gitlab.com/user/project/repository/branches/protected/),
[merge-request pipelines](https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/)
and the [successful-pipeline merge condition](https://docs.gitlab.com/user/project/merge_requests/auto_merge/).
The publisher requirements above are Sudograph's contract; they do not imply
that any GitLab tier automatically supplies a trusted Sudograph publisher.
