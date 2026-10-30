# Source field comment passages

Source field names can remain identical across interface languages while their
type captions change. A comment selecting only `ProductSales` previously included
the translated caption in its passage version. Changing the interface language
then made the unchanged name fail strict comment resolution.

The shared renderer now annotates an unchanged source column name as a nested
`field-name` passage with the language tag `und`. Its version still includes the
SHA-256 of the exact source name. Captions and translated labels retain their
language-specific versions. Selections spanning the name and caption continue to
use the outer label passage.

This does not weaken ShareOne's version, quote, position or context checks. A
changed source name remains unresolved. Existing comments and their recorded
selectors are preserved; this change does not reattach old comments.

## Regression coverage

- `tests/test_comment_passages.py` checks stable name versions, changed source
  names and language-specific outer label versions.
- `tests/test_comment_passages_browser.py` drives the generated Northwind renderer
  in Chromium, captures a real DOM range, switches both languages and restores the
  exact range after the renderer rebuilds. A changed name fails resolution. Its
  resolver fixture checks strict matching; ShareOne delivery is covered by the
  separate production acceptance below.
- `python -m tools.verify` passed all eight repository gates, including 451
  Python tests and generated-artifact checks, on 2026-10-31.

## Production acceptance, 2026-10-31

The actual production WebUI and its managed cloud Chrome/extension opened a
separate Northwind share generated through `compiler.business`. The original
public share and its 48 resolved threads were preserved.

Using the real viewer and authenticated ShareOne UI:

1. Selected the visible `ProductSales` source name and posted a comment with
   Chinese input.
2. Switched from English to Chinese. The exact word remained highlighted.
3. Clicked the comment to reveal the same source field and its expanded table.
4. Reloaded the browser page, reopened the comment and revealed the same field
   again in English.
5. Read the comment through the supported ShareOne skill. Its original quote and
   `und/field-name/` selector were identical before and after reload; there was no
   replacement anchor binding.
6. Deleted the test comment and verified zero remaining fixture comments. Stopped
   the owned browser, removed its test conversation, revoked its temporary key,
   logged out the test operator and closed the local viewer.

The original share was subsequently updated to the merged source revision
`6fad925f93b09f9c9b28fe673a32fd7d9ea6d732`. Its owner download matches the generated
Chinese artifact, and all 48 existing threads remained identical. A fresh
production viewer rendered the original page and retained the selected
`ProductSales` field when switching from Chinese to English. All owned runtime
resources were cleaned up.

The original-page follow-up displayed graph content in 5,777 ms. Earlier repeated
30-second failures remain recorded; this single successful sample does not
establish startup reliability. The temporary fixture's functional result and the
startup performance gate remain separate.

Both active Northwind artifacts were regenerated from the shared compiler and
renderer. Their embedded model content matches the published source revision
apart from presentation configuration. `publication.json` records the deployed
Chinese review artifact and retains the earlier publications. The English
artifact has not been deployed to the original share.
