# Approved source write-back acceptance plan

Status: planned, not deployed. Source connectors and the current Northwind
projection remain read-only. `compiler.apply` changes ontology proposals; it is
not an approved source-database migration executor. Actor labels supplied by an
agent are not authenticated human approval.

Field comments may motivate a source correction, but SQLite's missing declared
type on a calculated view field does not itself prove a source defect. A business
definition can be added without changing the source. Source SQL, result rows and
proposed business meaning keep their separate provenance.

## Acceptance exercise

Use a disposable SQLite database, never the pinned upstream source. The same
production write path must serve the exercise and CI; a test-only SQL script
would prove SQLite transactions, not enforcement of the approval architecture.

1. Produce a versioned migration proposal containing the intended source object,
   before/after schema or values, exact SQL, preconditions, validation and a
   rollback migration. Hash the entire proposal, including rollback instructions.
2. Create a GitLab merge request, or use the source owner's equivalent review
   system. Bind authenticated approval to the exact immutable proposal digest,
   source, target environment and revision. LLM-authored approval flags cannot
   satisfy this gate. A changed proposal invalidates previous approval.
3. Refuse execution before approval, on a stale source precondition, when the
   approved digest differs, or when the target environment is unauthorised.
   Refusals leave source data unchanged and record a reviewable reason.
4. Execute the approved migration transactionally through the trusted executor.
   Run validation and retain the receipt. Re-discover the database through the
   existing read-only compiler path and compare its new projection and source IDs.
5. Propose and approve rollback separately; approval of the forward change does
   not silently approve any later rollback. Apply it through the same executor,
   validate and re-project. Compare logical schema/rows with the original;
   SQLite file bytes can differ after a logically equivalent migration.
6. Run the full flow in CI with a disposable database and a test approval
   authority at the trusted adapter boundary. Include denied, tampered, stale,
   successful and approved-rollback cases. Separately integrate-test the live
   GitLab authentication/review adapter; a test authority does not prove that
   production adapter works.

## Missing capability

The repository refers to GitLab as an intended review authority but does not
currently include a GitLab migration/approval adapter, trusted source executor,
approval receipt store or this full-flow test. Local inspection found no `glab`
command or running GitLab service in Windows or the listed Docker containers;
this does not establish that no remote GitLab instance exists. Installing a
local GitLab server alone would not close the execution and approval boundary.

Implement this capability at the service boundary before calling the exercise
accepted. Keep the acceptance baseline immutable, and refresh the continuing
review model only after an approved source change.
