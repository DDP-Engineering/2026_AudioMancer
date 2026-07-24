# AudioMancer Character Discovery Service

## Scope

Character Discovery identifies speaking characters, synthesizes voice-ready
profiles, supports resume and manual maintenance, and exposes a stable
projection to Character Voices, Speech Blocks, UI state, and export.

The implementation is centered in:

- `src/audiomancer/services/character_discovery_service.py`
- `src/audiomancer/services/character_discovery_state_service.py`
- `src/audiomancer/ui/controllers/characters_ui_controller.py`

## Authoritative persistence

The operation owns one authoritative project artifact: `characters.json`.
AI transaction logs remain separate diagnostic files and are not referenced by
the document.

An absent file means the operation has not started. The persisted statuses are
`running`, `cancelled`, `failed`, and `completed`.

The strict root contract is:

```json
{
  "status": "running",
  "source": {
    "kind": "original",
    "language": "en",
    "fingerprint": "..."
  },
  "instructions": "",
  "token_usage": {
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "usage_available": false
  },
  "checkpoint": null,
  "failure": null,
  "characters": []
}
```

No profile ID, model name, temperature, context setting, output limit, budget
metadata, schema marker, operation name, or log path is stored. Resume always
uses the currently selected profile configuration. Token usage remains
cumulative.

The loader rejects malformed JSON, non-object roots, missing or extra fields,
and incompatible nested records. Reset is the only supported way to discard an
incompatible result.

## Source selection

Original chunks define canonical order and identifiers. Character Discovery
uses translated text only when every canonical chunk has a matching non-empty,
approved translation. Otherwise the entire operation uses original text.

The selected text drives:

- dialogue detection;
- names and aliases;
- evidence excerpts;
- Characters-page evidence previews.

`source.fingerprint` covers source kind, language, and each ordered chunk's ID,
sequence index, and selected text. Translation approval, edit, deapproval, and
reset actions recalculate the effective source. Character Discovery and its
downstream operations are invalidated only when source kind or fingerprint
changes.

## Checkpoints and atomic commits

Discovery checkpoint:

```json
{
  "phase": "discovery",
  "next_chunk_index": 4,
  "candidates": []
}
```

Synthesis checkpoint:

```json
{
  "phase": "synthesis",
  "next_candidate_index": 2,
  "candidates": []
}
```

Every successful discovery window updates status, checkpoint, token usage, and
characters in one atomic document write. After discovery, the checkpoint
candidate list is replaced with the stable merged candidate list.

Synthesis is sequential and intentionally performs one AI request per
character. Each candidate is compacted to fit the current profile's input
budget. After a successful synthesis request, the character is appended to
`characters` and `next_candidate_index` advances in the same atomic write.

Cancellation and failure retain the last committed checkpoint. A failed
synthesis request does not advance the index, so resume retries only that
character. On completion, `checkpoint` and `failure` are null.

## Character contract

Each persisted character has:

```json
{
  "character_id": "alice",
  "canonical_name": "Alice",
  "aliases": ["Al"],
  "traits": {
    "gender": {"value": "female", "confidence": "high"},
    "age": {"value": "adult", "confidence": "medium"}
  },
  "voice": {
    "definition_prompt": "...",
    "preview_text": "..."
  },
  "discovery_confidence": "high",
  "provenance": {
    "origin": "ai",
    "edited": false
  },
  "evidence": []
}
```

`load_character_document()` returns the strict document.
`load_character_profiles()` projects nested characters into the established
flat consumer shape.

Manual CRUD changes the same authoritative document:

- add creates `origin=manual`, `edited=false`;
- edit preserves origin and sets `edited=true`;
- delete removes only the selected character.

A completed document remains completed when all characters are deleted.
Only Reset removes `characters.json`.

## Manifest, UI, and downstream integration

`project.json.operations.character_discovery` is a reconstructible cache.
Status, phase progress, counts, and AI/manual/edited summaries derive from
`characters.json`.

The Characters page obtains evidence preview text from the currently resolved
source. Character Voices, Speech Blocks, and export continue to consume the
flat profile projection, so their domain behavior is unchanged.

Reset deletes Character Discovery and downstream runtime artifacts while
preserving Narrator Definition.

## Validation

Focused validation covers:

- strict root and nested contracts;
- absent, malformed, array, missing-field, and extra-field documents;
- original and fully approved translated source selection;
- source fingerprint invalidation;
- discovery and synthesis resume without repeating committed work;
- current-profile use on resume;
- one-request-per-character synthesis and budget compaction;
- atomic success, cancel, and failure persistence;
- manual add/edit/delete provenance;
- UI, manifest, Character Voices, Speech Blocks, and export projections;
- reset behavior.
