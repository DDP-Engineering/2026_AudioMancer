<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# REQ-FUNC-f878c579 - Characters page recovery from invalid discovery documents

## Behavior

`load_character_document` and `load_character_profiles` remain strict.  A
malformed JSON document, invalid root contract, invalid status, checkpoint,
token usage, or nested character continues to raise `CharacterDocumentError`
to direct callers.  Only `build_character_discovery_state` catches that exact
exception around its authoritative-document reads.

The catch path returns a complete payload accepted by
`CharactersPage.set_character_state`: empty profiles and character count;
resolved available AI-profile selection; the valid source-chunk map; no edit or
dirty state; `can_reset` true; and `can_start`, `can_add`, `can_edit`,
`can_save`, and `can_delete` false.  Its non-completed status is `failed` and
its sole operator note comes from a localized recovery key.  The note does not
include document contents, JSON fragments, credentials, or traceback data.

## Data / interface

Page-state construction performs no document writes, normalization, deletion,
or repair.  Existing `handle_reset_discovery_requested` remains the recovery
action: it deletes the Character Discovery artifact through
`reset_character_discovery`, rebuilds the manifest with the established
downstream reset policy while preserving the protected narrator operation, and
refreshes the normal no-document page state.

## Examples

With valid chunks and an invalid `characters.json`, state contains
`profiles=[]`, `can_reset=True`, and `can_start=False`; clicking Reset then
removes the invalid artifact and produces the ordinary ready/not-started state.
Opening the page alone leaves the invalid file byte-for-byte unchanged.

## Acceptance

- Strict direct reads reject malformed, invalid-root, and invalid-nested data.
- English and Romanian recovery notes render from equivalent placeholder sets.
- A MainWindow Characters refresh and the rendered Reset button remain usable.
- Valid missing, running, cancelled, failed, and completed states are unchanged.
