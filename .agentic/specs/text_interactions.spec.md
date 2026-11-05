# Shared text interaction contract

Accepted in TASK-0e2636ed. No project data or persisted schema changes.

## Supported controls

Normal QLineEdit (including editable-combo line editors), QPlainTextEdit and
QTextEdit, plus their read-only forms, in pages and dialogs created before or
after installation. Events on a multiline viewport resolve to its owning editor.
Disabled controls remain inert. Non-normal echo modes retain native Qt behavior.

## Menu and shortcuts

| Command | Availability | Shortcut |
| --- | --- | --- |
| Undo / Redo | editable and corresponding native stack nonempty | native standard keys |
| Cut | editable with selection | Ctrl+X |
| Copy | selection | Ctrl+C |
| Paste | editable with clipboard text | Ctrl+V / native Paste keys |
| Delete | editable with selection | Delete |
| Select All | text nonempty | Ctrl+A |
| Find | normal enabled control | Ctrl+F |
| Find Next | accepted query present | F3 |
| Find Previous | accepted query present | Shift+F3 |

Editing callbacks recheck current enabled/read-only state before mutation.
Paste inserts plain text via the native editor API, preserving validators and
undo history. Native keyboard editing remains intact; Paste shares the menu's
plain-text path. Shared search shortcuts consume their event only for eligible
focused controls and do not activate a parent shortcut.

## Search

Find uses a localized input dialog prefilled from the current selection, or the
control's previous query. Accepted nonempty input becomes that control's runtime
query. Cancellation/empty input leaves the old query and selection intact.
Search is literal, case-insensitive, and wraps once. Next starts after selection;
Previous starts before selection. With no saved query, repeat shortcuts prompt
for Find. Search failure shows a localized notification and retains the cursor,
selection and text. Navigation changes no document text or project persistence.
Native Qt document search/selection offsets handle Unicode consistently.
A Find prompt does not recursively open another shared Find prompt.

## Ownership

One idempotently installed application event filter handles supported controls
and dynamic dialogs. Search state belongs to the editor's runtime properties;
the active locale is obtained when a menu or dialog is created. Page-local
Chunking and Characters search implementations are removed in favor of this
shared behavior. Clipboard and native edit stacks remain owned by Qt.
