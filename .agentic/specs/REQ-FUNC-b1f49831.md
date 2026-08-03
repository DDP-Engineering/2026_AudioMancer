<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# REQ-FUNC-b1f49831 — Transaction-safe source replacement

## Behavior

For an unlocked project that already has a registered source, source replacement proceeds in this order:

1. Validate the selected source and the previous manifest path without mutating the project.
2. Choose a unique project-root destination whose case-insensitive file name is neither present on disk nor reserved for a generated workflow artifact.
3. Copy the selected source into the project successfully, cleaning up any incomplete destination if the copy fails.
4. Delete the previous stored source only after the new copy is complete.
5. Reset Extraction and all downstream generated artifacts through `text_extraction_service.reset_extraction_and_downstream`.
6. Reset every compact operation summary and set `current_stage` to `source_selected` through `text_cleanup_state_service.build_manifest_after_extraction_reset`.
7. Register the new source record and save the manifest without changing `target_language`, `selected_voice_language`, or `voice_assignment_mode`.

The reset must use the centralized operation-runtime ownership lists. Source-import code must not duplicate downstream artifact deletion lists. Initial import into a project with no previous source retains its existing option-selection behavior.

## Data and interfaces

`import_service.import_source(project_root, source_path, previous_source_document)` retains its manifest-ready dictionary return shape: `original_name`, `stored_relative_path`, `file_type`, `imported_at`, and `size_bytes`.

Reserved names are derived from the centralized root-level operation artifact registry. Comparison is case-insensitive so behavior is consistent on Windows and conservative on case-sensitive filesystems. A reserved name is treated like an existing-file collision and receives the normal numeric suffix, for example `extracted_text.txt` becomes `extracted_text_1.txt` when that candidate is otherwise free.

## Failure behavior

If source copying raises, the previous stored source remains present, no extraction or downstream reset runs, and `project.json` remains byte-for-byte unchanged with its existing operation summaries. Any partially copied new destination is removed when possible before the exception propagates to the caller.

## Acceptance

- Replacing a processed project's source removes every stale Extraction-and-downstream artifact, resets every compact operation summary to its default, and saves `current_stage = "source_selected"`.
- The saved manifest points to the new source, the new stored file survives reset, and the three unlocked option fields retain their prior values.
- An injected `shutil.copy2` failure leaves the complete prior project state unchanged.
- Supported source files named `extracted_text.txt` or `clean_text.txt` are stored under safe non-reserved names.
