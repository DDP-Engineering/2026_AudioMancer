# REQ-FUNC-c7960ee8 - Select legacy text encodings deterministically

## Behavior

Text-source decoding uses this priority: a supported byte-order mark, a valid
format declaration such as RTF `ansicpg`, strict UTF-8, then evidence scoring
across every successfully decoded cp1250, cp1251, and cp1252 candidate. The
score rewards coherent Latin or Cyrillic script, code-page-specific letters
and punctuation, and ordinary printable text while penalizing mixed scripts,
control characters, symbols in words, and implausibly all-accented Latin text.
A fixed tie-break makes the result repeatable; codec iteration never decides a
non-tied result.

Latin-1 is outside candidate scoring and is the guaranteed terminal fallback
only when UTF-8 and all three Windows-code-page decoders reject the bytes.
ASCII is reported as UTF-8 because it is valid strict UTF-8.

## Data / interface

The existing adapter `encoding: str | None` value records the selected Python
codec label and flows unchanged into `source_ledger.json` at
`source.encoding`. No public signature or ledger schema changes.

RTF `\\ansicpgNNNN` is resolved with the standard-library codec registry. An
unknown declared code page is an invalid source rather than permission to
guess another encoding.

## Examples

- UTF-8 BOM bytes decode as `utf-8-sig` without a leading U+FEFF.
- Russian `Привет, мир!` bytes encoded as cp1251 decode to those exact code
  points and report `cp1251`, not a cp1250 or Latin-script rendering.
- Polish cp1250 and Western cp1252 prose select their respective codecs.
- Bytes containing values rejected by all three Windows codecs decode through
  the explicit `latin-1` terminal policy and report `latin-1`.

## Acceptance

Public Extraction-path regressions prove exact canonical text and ledger
encoding for every named case; a focused helper test is allowed only for the
otherwise artificial all-Windows-codecs-reject terminal fallback.
