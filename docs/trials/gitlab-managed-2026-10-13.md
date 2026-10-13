# Managed GitLab deployment acceptance, 2026-10-13

The [real deployment run](https://github.com/sudoprivacy/sudograph/actions/runs/38345783169)
passed all 13 acceptance checks at Sudograph revision
[`9e5420b`](https://github.com/sudoprivacy/sudograph/commit/9e5420bf0f657faa3b6289dfbd0e8102a353148a).
The machine-readable [receipt](gitlab-managed-2026-10-13.json) contains source,
model, compiler and artifact hashes, native proposal/pipeline IDs and the three
verified releases. All actors and source records are synthetic acceptance data.
No credentials or private Northwind review comments are included.

The workflow started real GitLab CE 19.3.5 and Runner 19.3.0 images pinned by
registry digest, the operator-owned compiler image and the publishing service.
It scanned a disposable SQLite database containing tickets and a native total
view. Authors submitted YAML through the managed API; they never ran a verification
command or supplied compiler code.

The accepted path proves:

- Caller authentication and automatic native CI; source-reference failures and
  caller approval/HTML inputs are refused through the managed interface.
- Native branch protection rejects author pushes and merges.
- An authenticated reviewer event bound to the exact SHA triggers independent
  compilation, complete-reader verification, guarded merge and publication.
- Two business views share one canonical definition and unchanged source facts.
- A new commit cannot reuse the old approval, even with a successful pipeline.
- Reviewed content rollback preserves identities and advances the content version;
  the earlier verified reader remains addressable with identical bytes.
- Changed stored HTML is refused on read; HTML committed to a proposal fails the
  actual trusted CI job.
- Removing project membership immediately blocks contract and artifact reads.
- The original SQLite file hash is unchanged by the complete workflow.

This is a deployed technical acceptance of model review/publication. It does not
establish business truth, customer identity-provider integration, source write-back
or automatic ShareOne hosting. A GitLab approval never silently changes a business
definition's unconfirmed status. Those boundaries also appear in the README diagram.

Initial integration runs exposed an incorrect host-side monitoring probe, an
outdated internal account-creation path and a verifier comparing the pre-YAML
representation. The deployment now probes the public Rails sign-in endpoint,
uses the supported Users API and verifies the exact submitted YAML representation.
The checks were retained; no retry converts a failed check into success.

A later clean deployment exposed a first-push race: GitLab's default-branch
protection worker could recreate its default rule between an unprotect request
and a replacement request, producing HTTP 409. Provisioning now installs and
reads back the required protection on each empty repository before its first
commit or any author membership. It never removes that initial protection.
The ordering and rejection of permissive rules have regression coverage; a
real local GitLab CE probe also verified initial commits by a non-admin project
owner with the protection already installed.
