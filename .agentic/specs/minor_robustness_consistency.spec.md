<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Spec: issue #38 minor robustness and consistency

Companion specification for the independent issue #38 behavior and source
consistency requirements.

- `REQ-FUNC-1179da33-b65d-4192-a875-353a38c37ab7`: incomplete whitespace
  realignment diagnostics.
- `REQ-FUNC-cf65391c-89ba-4787-8df3-33eb22337b74`: strict bare Roman numerals.
- `REQ-FUNC-c593854d-38a1-44f3-aff1-33ede63b8dde`: existing-file project target.
- `REQ-FUNC-9c9b7202-3dcd-4a19-a0bd-65a9278f8aa8`: warning/provenance
  separation.
- `REQ-NFR-5b12e005-3baf-4c44-b7de-7346fcf8f605`: source consistency.

## Behavior

### Whitespace realignment diagnostics

When a whitespace-only operator edit cannot locate any retained source-ledger
unit in the edited text, Cleanup keeps the operator edit but:

- logs one warning through the Text Cleanup component logger;
- appends `user_whitespace_realign_incomplete` to `cleanup.json.warnings`;
- does not duplicate that warning when it is already present.

### Bare Roman-numeral headings

All three transient chapter detectors use the same uppercase-only, non-empty
Roman-numeral grammar:

```regex
(?=[MDCLXVI]+$)M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})
```

Prefixed `Chapter`, `Capitolul`, `Scene`, and `Scena` headings retain their
existing case-insensitive behavior. Bare valid values such as `I`, `IV`, `XIV`,
and `MCMXCIV` are headings. Lowercase values and invalid Roman strings are not.

### Completed Cleanup output recovery

A reusable completed Cleanup checkpoint is returned directly only when
`clean_text.txt` exists and its SHA-256 matches `cleanup.json.output_hash`.
Missing or mismatched output is deterministically rerendered from the persisted
unit operations and boundary decisions without an LLM request.

### Existing-file project target

`create_project(name, parent_path)` rejects a target path that already exists as
a file before attempting directory iteration or creation.

```text
Exception: FileExistsError
Message: Project path already exists as a file: <resolved target path>
State: the existing file and its bytes are unchanged
```

### Cleanup warning projection

Cleanup paragraph `reason_codes` remain complete provenance. Runtime
`warning_flags`, and therefore downstream `cleanup_warning_flags`, contain only:

```text
deterministic_fallback
unknown_line_boundary
page_transition_repaired
```

The strict `chunks_text.json` field set is unchanged.

### Source consistency

- The Translation artifact comment says `Reset-only legacy names`.
- `validate_project_name` aligns its `@version` tag with the other tags.
- `_apply_ai_result` and `_can_reuse_analysis` have the required two blank
  lines between module-level definitions.
- `tests/test_logging_service.py` is UTF-8 without a BOM; no other content is
  changed for the encoding cleanup.

## Examples

| Input | Expected result |
| --- | --- |
| Internal whitespace change prevents exact source-unit lookup | edit persists; component warning and `user_whitespace_realign_incomplete` are recorded |
| Bare `XIV` | chapter heading |
| Bare `civil`, `mix`, `did`, or lowercase `i` | ordinary text |
| Completed checkpoint plus missing `clean_text.txt` | deterministic rerender, completed output, no LLM call |
| Project target is an existing file | friendly `FileExistsError`; file unchanged |
| Reasons `user_edited`, `llm_verified_override`, `unknown_line_boundary` | provenance keeps all three; warning flags contain only `unknown_line_boundary` |

## Acceptance

- [ ] Behavior items 1-5 have focused regression tests.
- [ ] Source consistency items 6-7 pass inspection, Ruff, and a BOM byte scan.
- [ ] Full pytest is not run; the owner performs the final application test.
