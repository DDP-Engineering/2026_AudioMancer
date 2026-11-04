# REQ-FUNC-b1f49831 - Source import copy-first boundary

## Behavior

The low-level `import_service.import_source(project_root, source_path, previous_source_document)` API validates the supported file and previous project-relative source path before mutation, selects a collision-safe destination, copies through an atomic temporary file, and then removes the previous project copy. It returns original_name, stored_relative_path, file_type, imported_at and size_bytes. The caller owns manifest publication.

Reserved names come from the centralized operation artifact registry and are compared case-insensitively. A supported source named extracted_text.txt receives the first available non-reserved numeric suffix. Selecting the existing stored source returns its existing metadata without copying or deleting.

## Failure behavior

A source-copy failure cleans its incomplete destination and propagates while preserving the previous source, manifest, operation summaries and generated artifacts. If removing the previous source fails, the newly copied destination is removed before the error propagates.

## User interface boundary

Home fixes a registered book and imports only the first source of an existing source-less project. New Project publishes its initial book and manifest together through project_options_service. The low-level replacement API remains available to callers responsible for their own manifest and dependent data lifecycle.

## Acceptance

Importer tests prove collision-safe names, stored-source idempotence, copy-first replacement, and byte-for-byte preservation after an injected copy failure. Home tests prove that attempts to replace a registered book leave project files unchanged.
