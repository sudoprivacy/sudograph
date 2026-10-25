# Host source registration

`compiler.registration` is the private host boundary for creating a canonical
model from a complete, read-only SQLite projection. The embedding host must
authorize the source and choose the model store, namespace, actor, locale and
operation identity. Agents receive the registered model tools, not this intake
or permission to select database paths.

The native Sudowork client calls this boundary directly. The deployment command
`python -m tools.model_workspace` uses the same implementation; ordinary users
do not need to discover or run that command.

## One observation, one checked publication

Source discovery, schema/identity checks, SQL dependency analysis and projection
compilation borrow the same read-only SQLite connection and transaction. This
prevents a concurrent source write from mixing discovery from one observation
with counts or checks from another. It copies no database. Nested observations
and a second source inside the observation are refused.

Only a successful complete scan creates a model. Compiler failures, unsupported
source constructs and unresolved source SQL dependencies cannot publish a
partial projection as complete. The canonical model and its private registration
receipt are prepared together, then published with an atomic no-replace link on
the model directory's volume. A per-target SQLite mutex serializes creation;
it contains no second model, connection catalogue or job queue. An existing
model is never overwritten by registration.

The receipt records three distinct axes:

| Axis | Meaning |
| --- | --- |
| `connection` | SQLite was reachable for the recorded source observation. This is not a promise that a later read will succeed. |
| `scan` | The supported source inventory was exhausted and structure passed checks, with object/field counts and an observation ID, timestamps and schema version. |
| `records` | The host chose live delivery or a snapshot. Complete structure does not imply that every record was exported. |

The default uses live record delivery and embeds zero rows. Version-bound reads
use the existing bounded source reader. Its drift checks still apply: a read
does not silently turn the registered baseline into the current database schema.
The operator's explicit `--snapshot-records` option retains frozen record export.
The native host forces live delivery instead of accepting a caller's coverage
claim or record-export flag.

## Durable retry and refusal

The model stores the receipt and initial revision. The operation ID and checked
settings, including host actor and registered source identity, produce a request
digest. Retrying that request after a lost response returns the original receipt
and current model contract without scanning again. A different request receives
`REGISTRATION_CONFLICT`; it cannot adopt an unrelated existing store or replace
its source. If publication never occurred, a retry performs a fresh scan.

Representative failures remain typed across the host subprocess boundary:

- `REGISTRATION_BUSY`: creation of this model is in progress; retry the same
  operation. Other model registrations use separate locks.
- `SOURCE_UNAVAILABLE` / `SOURCE_BUSY`: restore source access or wait for the
  source, then retry the same operation.
- `SCAN_INCOMPLETE`: the source was connected but projection checks or dependency
  analysis failed. Repair or extend the provider before claiming coverage.
- `SOURCE_PROVIDER_UNSUPPORTED`: the provider cannot yet meet complete-scan
  registration. A successful legacy connection probe is insufficient.

The worker accepts one JSON request on stdin; source paths are not shell
arguments. Its store and actor come from host arguments. Connection details stay
in private host storage and are absent from model YAML and agent context.

## Scope of this slice

Complete registration currently supports SQLite only. The source scanner's
existing path-based identity remains unchanged. Identical copies at different
paths remain distinct; logical registered-source handles and checked relocation
or rename mappings are still required for the full connector design.

The native host binds the project authority only after checking a complete
compiler receipt. It does not create an empty RDF snapshot or fall back to RDF
on failure. This is a host service API, not yet the connection-form/IPC adapter.
Cloud tenant authorization, scoped source handles, durable scan progress,
PostgreSQL/MySQL complete providers and automatic rescan remain separate work.
The deployment must provide a filesystem supporting atomic same-volume hard
links; a publication failure leaves no successful registration receipt.
