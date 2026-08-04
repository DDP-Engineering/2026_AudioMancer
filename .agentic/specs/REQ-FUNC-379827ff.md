# REQ-FUNC-379827ff - Honor EPUB content document encodings

## Behavior

Each non-navigation spine member is decoded independently. A byte-order mark
has first priority, followed by an XML encoding declaration and then an HTML
`meta charset` or Content-Type charset declaration. A declaration is resolved
through the standard-library codec registry and decoded strictly. The legacy
text selection contract is used only when no usable signature or declaration
exists.

Unknown declared codecs and strict decode failures raise `ValueError` naming
the spine item identifier and file name. A failed content member is never
silently skipped. Existing spine order, navigation filtering, progress,
cancellation, and visible-text parsing remain unchanged.

## Data / interface

No public signature or ledger schema changes. If every decoded content member
uses the same codec, `source.encoding` stores that codec label. If content
members differ, it stores `mixed(<sorted-comma-separated-codec-labels>)`, for
example `mixed(cp1252,utf-8)`. Sorting makes the representation deterministic
while preserving spine order only for extracted text.

Codec aliases are normalized through `codecs.lookup(...).name` before the
uniform/mixed value is built. BOM-aware labels retain BOM removal semantics.

## Examples

- UTF-16 XHTML with a matching BOM and XML declaration extracts exact text.
- cp1252 or ISO-8859-1 XHTML with a matching declaration extracts accents.
- One UTF-8 and one cp1252 chapter report `mixed(cp1252,utf-8)`.
- `encoding="not-a-codec"` raises an error naming its chapter item and file.

## Acceptance

Tests patch actual EPUB ZIP members after EbookLib writes the container so the
fixture bytes genuinely use the declared non-UTF-8 encoding. They assert exact
spine-ordered visible text, navigation exclusion, ledger encoding, and
item-specific failure text.
