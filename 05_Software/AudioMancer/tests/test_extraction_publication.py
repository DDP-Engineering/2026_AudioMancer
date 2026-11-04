#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_extraction_publication.py
@brief Exact-content regression tests for document extraction.
@details Verifies recoverable publication, preserved previous results and downstream invalidation.
"""

# IMPORTS

from pathlib import Path

import pytest

from audiomancer import config
from audiomancer.services import project_workspace_service, text_extraction_service

# PUBLIC API


def _project(tmp_path):
    """@brief Build a completed extraction with downstream text and persisted source identity."""
    root, manifest = project_workspace_service.create_project("Transactional extraction", tmp_path)
    source = root / "story.txt"
    source.write_text("Original story.", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": source.name,
        "stored_relative_path": source.name,
        "file_type": "txt",
        "imported_at": "2026-11-04T12:00:00+00:00",
        "size_bytes": source.stat().st_size,
    }
    project_workspace_service.save_manifest(manifest, root)
    text_extraction_service.extract_text(root, manifest)
    (root / config.CLEANED_TEXT_FILE_NAME).write_text("Existing approved cleanup", encoding="utf-8")
    (root / "operator-note.txt").write_text("Keep this", encoding="utf-8")
    return root, manifest, source


def _files(root):
    """@brief Compare durable project bytes while excluding transaction temporary folders."""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and not any(part.startswith(".extraction-") for part in p.relative_to(root).parts)
    }


@pytest.mark.parametrize("failure", ["parse", "ledger", "metadata"])
def test_failed_rerun_preserves_previous_extraction_and_downstream(tmp_path, monkeypatch, failure):
    """@brief Failed parsing or publication leaves the previous usable project byte-identical."""
    root, manifest, source = _project(tmp_path)
    source.write_text("Replacement story.", encoding="utf-8")
    before = _files(root)
    if failure == "parse":
        source.write_bytes(b"")
        before = _files(root)
    else:
        original = text_extraction_service.write_json_atomic

        def reject_target(path, payload):
            """@brief Inject an IO failure at one staged output artifact."""
            target = config.SOURCE_LEDGER_FILE_NAME if failure == "ledger" else config.EXTRACTION_METADATA_FILE_NAME
            if Path(path).name == target:
                raise PermissionError("Injected write failure")
            return original(path, payload)

        monkeypatch.setattr(text_extraction_service, "write_json_atomic", reject_target)
        if failure == "ledger":
            from audiomancer.services import source_ledger_service

            monkeypatch.setattr(source_ledger_service, "write_json_atomic", reject_target)
    with pytest.raises((OSError, ValueError)):
        text_extraction_service.extract_text(root, manifest)
    assert _files(root) == before


def test_cancelled_rerun_preserves_previous_extraction(tmp_path):
    """@brief Cancellation at a progress boundary never invalidates previous approved text."""
    root, manifest, _source = _project(tmp_path)
    before = _files(root)
    with pytest.raises(text_extraction_service.OperationCancelledError):
        text_extraction_service.extract_text(root, manifest, cancel_requested=lambda: True)
    assert _files(root) == before


def test_successful_rerun_invalidates_downstream_after_validation(tmp_path):
    """@brief Previous results remain readable until valid replacement text is published."""
    root, manifest, source = _project(tmp_path)
    source.write_text("Replacement story.", encoding="utf-8")
    seen = []

    def inspect_progress(_current, _total, percent, _message):
        """@brief Verify the live extraction stays valid throughout prepublication progress."""
        seen.append(percent)
        if percent < 100:
            assert (root / config.EXTRACTED_TEXT_FILE_NAME).read_text(encoding="utf-8") == "Original story.\n"
            assert (root / config.CLEANED_TEXT_FILE_NAME).is_file()

    text_extraction_service.extract_text(root, manifest, progress_callback=inspect_progress)
    assert (root / config.EXTRACTED_TEXT_FILE_NAME).read_text(encoding="utf-8") == "Replacement story.\n"
    assert not (root / config.CLEANED_TEXT_FILE_NAME).exists()
    assert (root / "operator-note.txt").read_text(encoding="utf-8") == "Keep this"
    assert seen[-1] == 100 and seen == sorted(seen)


@pytest.mark.parametrize("failure", ["staging", "publication", "manifest"])
def test_commit_failure_restores_every_original(tmp_path, monkeypatch, failure):
    """@brief Restore manifest, extraction, samples and generated audio after partially applied IO."""
    from audiomancer.services import extraction_publication_service

    root, manifest, _source = _project(tmp_path)
    audio = root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME / "sample.wav"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"existing audio")
    before = _files(root)
    original_replace = Path.replace
    injected = []

    def fail_once(path, target):
        """@brief Deny a selected rename exactly once, allowing normal recovery afterwards."""
        is_staging = ".extraction-backup-" in str(target) and path.name == config.SOURCE_LEDGER_FILE_NAME
        is_publish = ".extraction-new-" in str(path) and Path(target).parent == root
        matches = (
            is_staging
            if failure == "staging"
            else is_publish and (failure != "manifest" or path.name == config.PROJECT_MANIFEST_FILE_NAME)
        )
        if matches and not injected:
            injected.append(True)
            raise PermissionError("Injected rename failure")
        return original_replace(path, target)

    monkeypatch.setattr(extraction_publication_service.Path, "replace", fail_once)
    with pytest.raises(PermissionError):
        text_extraction_service.extract_text(root, manifest)
    assert injected
    assert _files(root) == before
    assert not list(root.glob(".extraction-*"))


def test_cancel_immediately_before_publication_preserves_results(tmp_path):
    """@brief A cancellation during canonical validation is checked before any live mutation."""
    root, manifest, _source = _project(tmp_path)
    before = _files(root)
    progress = []
    with pytest.raises(text_extraction_service.OperationCancelledError):
        text_extraction_service.extract_text(
            root,
            manifest,
            progress_callback=lambda _current, _total, percent, _message: progress.append(percent),
            cancel_requested=lambda: 95 in progress,
        )
    assert _files(root) == before


def test_denied_recovery_retains_named_originals(tmp_path, monkeypatch):
    """@brief If the filesystem also denies restoration, original files retain their relative names."""
    root, manifest, _source = _project(tmp_path)
    original_text = (root / config.EXTRACTED_TEXT_FILE_NAME).read_bytes()
    original_replace = Path.replace

    def deny_publication_and_recovery(path, target):
        """@brief Fail after a partial publication and deny restoring one original."""
        if (
            ".extraction-new-" in str(path)
            and Path(target).parent == root
            and path.name == config.SOURCE_LEDGER_FILE_NAME
        ):
            raise PermissionError("Cannot publish ledger")
        if ".extraction-backup-" in str(path) and path.name == config.EXTRACTED_TEXT_FILE_NAME:
            raise PermissionError("Cannot restore original")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", deny_publication_and_recovery)
    with pytest.raises(OSError, match="originals retained"):
        text_extraction_service.extract_text(root, manifest)
    backups = list(root.glob(".extraction-backup-*"))
    assert len(backups) == 1
    assert (backups[0] / config.EXTRACTED_TEXT_FILE_NAME).read_bytes() == original_text

# END OF FILE
