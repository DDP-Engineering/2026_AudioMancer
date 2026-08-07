<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# Unicode character identity key

## Behavior

REQ-FUNC-e3015445 and REQ-FUNC-f5fc5dd8 use one dependency-free identity key.
The key is only for comparison; add and edit persist the operator's stripped
display spelling unchanged.  Candidate grouping preserves the first candidate's
canonical display text and its existing first-match grouping behavior.

## Identity-key normalization matrix

| Input content | Identity-key treatment |
| --- | --- |
| Canonically composed or decomposed text | Normalize with NFKD before comparison. |
| Letters and numbers from any script | Retain each character after Unicode case folding. |
| Latin diacritics and combining marks | Remove after decomposition, so `René` equals `Rene`. |
| Punctuation, whitespace, symbols, emoji, and underscores | Remove. |
| Only removed content | Produce an empty key; manual input is invalid and candidates cannot group by it. |

Therefore `René` equals `Rene`, while `Renée` differs from `Rene` and
`José` differs from `Jos`.  Canonically equivalent spellings compare equal.
Non-Latin letters remain their Unicode code points; this design does not
transliterate or match visually confusable characters.

## Data / interface

The existing `_normalize_identity(value: str) -> str` remains the authoritative
private helper.  Manual validation compares its key with persisted canonical
names and aliases, excluding the edited profile ID.  Candidate grouping and
merged-group diagnostic keys call the same helper and discard empty keys.
No persisted schema, character ID, filename, canonical-name, alias, evidence,
confidence, demographic, or ordering format changes.

## Acceptance

- Manual add and edit accept meaningful Unicode names and reject equal keys.
- Candidate canonical names and aliases merge only when they share a non-empty
  identity key.
- Existing ASCII behavior and first-match grouping order remain unchanged.
