# REQ-FUNC-fb96f028 - Extract only visible EPUB HTML content

## Behavior

The EPUB parser case-folds tag and attribute names. Presence of `hidden`
suppresses an element regardless of its parsed value. `aria-hidden` suppresses
only when its value trims and case-folds to `true`; `aria-hidden="false"`
remains visible. `script`, `style`, and `nav` remain ignored.

Ignored-subtree tracking records only non-void opening tags. HTML void syntax
and XHTML self-closing tags do not unbalance the ignored state. A hidden void
element suppresses only itself. Normal nested elements keep an ignored subtree
active until its matching ignored root closes. No CSS or JavaScript behavior is
interpreted.

## Data / interface

No public API or ledger schema changes. The existing event builder receives
only visible blocks, so canonical text and source-ledger units remain aligned.

## Examples

`<div hidden>secret<br><img></div><p>visible</p>` produces only `visible`.
`<span aria-hidden=" TRUE ">secret</span><p>visible</p>` produces only
`visible`; `aria-hidden="false"` produces its text normally.

## Acceptance

Regression coverage exercises boolean hidden spelling, aria-hidden normalization,
nested ordinary elements, HTML and XHTML void elements, existing ignored tags,
and a public EPUB fixture with exact text and ledger units.
