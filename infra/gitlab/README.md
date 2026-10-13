# Managed GitLab deployment

This directory belongs to Sudograph infrastructure. It installs a private model
project, an operator-owned CI project, a compiler runner and a publishing service.
Authors submit model inputs; they do not install CI or choose which checks run.

## Isolated acceptance profile

Install Python 3.12 dependencies and Docker with Compose. Use a new private
directory, outside the checkout. The stack owns only ports 8088 and 8788, the
`sudograph-gitlab` Compose project and its explicitly named volumes/network.
Do not start it if those resources already belong to another installation.

```bash
pip install -r requirements.txt
python -m tools.check_gitlab /private/sudograph-acceptance --report /private/acceptance.json
```

The command starts pinned GitLab CE and Runner images, builds the trusted worker,
scans an unrelated disposable SQLite fixture, and creates separate synthetic
author, reviewer and publisher accounts. It exercises actual native CI and review
events. It does not impersonate a customer or change Northwind.

`actors.json`, the root password, policy and runner configuration are credentials.
Keep the deployment directory private. Only `acceptance.json` is designed as a
public CI artifact; it records hashes and check outcomes, without credentials.
The GitHub integration workflow performs this deployment in an isolated runner
and removes only its own Compose resources afterwards.

To start the same completed local acceptance installation again:

```bash
python -m tools.gitlab_stack /private/sudograph-acceptance
```

This reuses its accounts, projects, baseline and persistent volumes. A partially
completed bootstrap stops for operator inspection; it does not silently replace
identities or adopt an unrelated project. GitLab startup can take several minutes.

## Existing customer GitLab

The deployment owner prepares a private JSON configuration with these fields:

```json
{
  "operator": {"url": "https://gitlab.example", "token": "OPERATOR_CREDENTIAL"},
  "pipeline_name": "customer-sudograph-pipeline",
  "model_name": "customer-sudograph-model",
  "publisher_id": 103,
  "publisher_token": "PUBLISHER_CREDENTIAL",
  "authors": [101],
  "reviewers": [102],
  "worker_gitlab_url": "https://gitlab.example",
  "allow_http": false,
  "image": "registry.example/sudograph:PINNED_DEPLOYMENT_VERSION",
  "language": "en",
  "webhook_url": "https://publisher.example/hooks/gitlab"
}
```

Run registration with the operator-checked phase-one model JSON:

```bash
python -m tools.provision_gitlab /private/config.json --baseline /private/source-model.json --output /private/registered
```

Provisioning authenticates the publisher and validates the baseline before
creating resources. It installs and verifies main-branch protection before the
initial commits and author memberships. It writes operator-owned `policy.json`, `baseline.json`,
`worker.json` and `runner.toml`. Install those in the same private publisher state
and read-only trusted-input mounts used by Compose. The generated runner's network
and volume names belong to this Docker deployment profile; adapt them as operator
configuration when running an existing runner elsewhere. Push the trusted worker
image to the registered private registry and pin its deployed version.

Use HTTPS for an existing installation. Plain HTTP, local webhook requests and
Rails bootstrap accounts are specific to isolated acceptance. The existing-instance
registration path is implemented, but each customer's TLS, network, identities
and runner installation require their own deployment acceptance.

## Agent and reviewer interface

The publisher exposes JSON `POST /v1` with a caller's authenticated GitLab token
in the `Authorization: Bearer ...` header. Never put credentials in a URL or YAML.

| Operation | Inputs | Result |
| --- | --- | --- |
| `contract` | `operation` only | Registered source schema/pin, namespace, current model, canonical identity versions and phase-specific authoring requirements. |
| `submit` | `operation`, complete `model` YAML text, `intent` | Automatically created Git commit and merge request; compiler errors include a repair direction. |
| `status` | `operation`, numeric `proposal` | Exact revision, pipeline state, SHA-bound review evidence and any release receipt. |

The model repository accepts `model.yaml` only. Business models use the existing
checked `sudograph-business-overlay/v4` language. Phase one accepts a source
request referencing its registered baseline; authored meanings belong in phase
two. A checked overlay can also contain phase-one `source_review` questions:
`category: issue`, existing source `targets`, and a nonempty `verification` plan,
without business dependencies. They appear over the same source projection,
separate from business meanings and policies. The contract guides agents to
propose stakeholder decisions and business definitions in phase two instead of
relabeling data-quality observations. Compiler and renderer enforce the typed
references; people review whether the prose captures the intended business.
The source URI, compiler, CI, policy and output destination are never model
inputs. Business identities are derived once per canonical concept in a fixed
namespace; current Git history enforces monotonic content versions.

GitLab runs the external pipeline automatically. Its artifact is a review draft,
with definitions still marked unreviewed. A registered independent reviewer
approves the exact SHA in GitLab. An authenticated GitLab hook records that SHA;
the publisher then checks native review and CI again, independently compiles and
verifies the complete HTML, and requests a SHA-checked fast-forward merge.
Fast-forward merging prevents a concurrently changed target from incorporating
an unchecked combination of model inputs.

GitLab CE's optional approvals alone are not a mandatory review gate. Only the
service identity can perform managed merges; Sudograph requires the authenticated
SHA-bound event as well as current native approval and reviewer membership.
It does not trust an author's
success flag, an approval count for another revision or a model-branch CI script.
Removing approval before the publisher's final check blocks the release. That
check is the publication decision point; later revocation does not erase history
or undo an already accepted publication.

Only accepted releases can be read from `GET /releases/<source-sha>.html`, with
the same caller authentication. Every read verifies the artifact hash against
its persisted receipt. A completed merge with a lost HTTP response can recover
only the exact durably prepared model/context/artifact. History is Git-owned;
the local identity index is derived from that history.

An approved content rollback is a new proposal preserving canonical IDs and
advancing the definition version. Merely reverting to an older version number
fails. Existing verified historical releases remain addressable by their SHA.

## Boundaries

This is a model review/publication deployment, not permission to modify the source
database. Nexus/Gateway remain the data and operation authorities. The isolated
profile uses explicit GitLab account allowlists for model authority; it does not
claim that customer Nexus SSO or browser OAuth has been connected. A registered
baseline must already be scoped to the project's authorised source visibility.

The publisher does not automatically upload to ShareOne. ShareOne content review,
hosting authentication and private GitLab remote-source support are separate
integrations. The existing Northwind static review share remains outside this
isolated GitLab fixture.

See [managed deployment](../../docs/managed-deployment.md) for acceptance status
and [source write-back](../../docs/source-writeback-acceptance.md) for the separate
migration contract.
