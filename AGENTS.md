# Repository conventions

- Write public documentation, explanatory code comments and commit messages in
  English. Public example pages start in English. Internal customer review may
  start in Chinese; preserve the shared language switch and locale catalogues.
- Preserve source values, domain identifiers and original machine evidence in
  their actual language. Do not translate an identity or rewrite recorded facts
  merely to remove non-English characters.
- Never edit a frozen acceptance artifact in place for presentation changes.
  Generate a separate, traceable presentation through the shared compiler and
  renderer. Use `--lang en --pack-html` for a complete public source export when
  hosting limits require a smaller file; packaging must not remove any records.
- Keep phase-one source projections separate from business definitions. A source
  SQL formula establishes what the source computes, not an approved business
  meaning. Agent proposals need explicit provenance and human confirmation.
- Source SQL calculations and their result rows remain phase-one facts. Phase
  two adds interpretations or new definitions in a separate business overlay.
  Use `compiler.business` for the overlay; declare provided/inferred origins,
  cite supplied evidence, reuse canonical definitions and increment versions
  through the shared registry. Do not treat source attribution as approval.
- Record the publication mechanism actually used. A file in GitHub does not mean
  its ShareOne share is bound to remote-url. Do not copy internal review comments
  into public examples; keep public examples on a separate share.
- Run `python -m tools.verify` for implementation changes. It is the same gate
  list used by CI. Stage only the files belonging to the task and preserve user
  changes in the workspace.

## Approval results

If a tool or automatic approval review rejects an action, tell the user promptly
which action was rejected, the exact returned reason and what remains unfinished.
If the reason is only "blocked by policy", state that no more specific reason was
provided. Preserve the rejection and use supported human review when available.
Do not retry the rejected outcome through another tool, an indirect command or a
safety-policy change. Continue independent authorised work while review is pending.
