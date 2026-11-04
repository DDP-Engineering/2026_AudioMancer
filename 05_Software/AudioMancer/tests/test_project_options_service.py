#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_project_options_service.py
@brief Project creation, option impact and rollback regression tests.
@details Exercises real workspace files, preserved edits and injected I/O failures.
"""

# IMPORTS

import json
import os
from pathlib import Path
import subprocess

import pytest

from audiomancer import config
from audiomancer.services import import_service, project_options_service, project_workspace_service

# HELPERS


def _tree(root: Path) -> dict[str, bytes]:
    """@brief Snapshot all project bytes to detect unintended mutation."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _processed_project(tmp_path, mode="narrator_and_characters"):
    """@brief Seed every reset boundary with recognizable project-owned bytes."""
    root, manifest = project_workspace_service.create_project("OptionsBook", tmp_path)
    source = tmp_path / "story.txt"
    source.write_text("The whole original book.", encoding="utf-8")
    manifest["source_document"] = import_service.import_source(root, source)
    manifest["current_stage"] = "audio_assembly_ready"
    manifest["voice_assignment_mode"] = mode
    manifest["narrator_profile_name"] = "Chosen narrator"
    manifest["narrator_language"] = "en"
    manifest["selected_voice_language"] = "en"
    for summary in manifest["operations"].values():
        summary["status"] = "completed"
    project_workspace_service.save_manifest(manifest, root)
    files = (
        config.EXTRACTED_TEXT_FILE_NAME,
        config.SOURCE_LEDGER_FILE_NAME,
        config.EXTRACTION_METADATA_FILE_NAME,
        config.CLEANED_TEXT_FILE_NAME,
        config.CLEANUP_DOCUMENT_FILE_NAME,
        config.CHUNK_ARTIFACT_FILE_NAME,
        config.TRANSLATED_CHUNKS_FILE_NAME,
        config.CHARACTERS_DOCUMENT_FILE_NAME,
        config.NARRATOR_VOICE_FILE_NAME,
        config.BOOK_ANALYSIS_DOCUMENT_FILE_NAME,
        config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME,
        config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME,
        config.AUDIO_BLOCKS_VOICE_CLONE_PROFILES_FILE_NAME,
        config.AUDIO_ASSEMBLY_REPORT_FILE_NAME,
        config.AUDIO_ASSEMBLY_STATE_FILE_NAME,
        "audio_narator_selected.wav",
        "audio_character_alice.wav",
        "personal_notes.txt",
        "audio_blocks/block.wav",
        "audiobook/book.wav",
        "log_ai_speech_blocks_1.log",
        "log_ai_book_analysis_1.log",
    )
    for name in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((name + " original bytes").encode())
    targets = [
        {
            "target_id": "narrator",
            "target_kind": "narrator",
            "sample_audio_path": "audio_narator_selected.wav",
            "sample_metadata": {"kind": "keep"},
        },
        {
            "target_id": "character_alice",
            "target_kind": "character",
            "prompt_text": "Edited prompt",
            "preview_text": "Edited preview",
            "sample_audio_path": "audio_character_alice.wav",
            "sample_metadata": {"kind": "clear"},
        },
    ]
    (root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).write_text(json.dumps(targets), encoding="utf-8")
    return root, manifest


# PUBLIC API


@pytest.mark.parametrize("mode", ["same_narrator", "narrator_and_characters"])
def test_mode_change_resets_only_dependent_results(tmp_path, mode):
    """@brief Both narration directions preserve text, narrator and edited voice prompts."""
    root, _manifest = _processed_project(tmp_path, mode)
    before = _tree(root)
    requested = "same_narrator" if mode == "narrator_and_characters" else "narrator_and_characters"
    plan = project_options_service.plan_project_options_change(root, "en", requested)
    assert plan.requires_confirmation
    assert set(plan.affected_operations) == {"character_voices", "speech_blocks", "audio_blocks", "audio_assembly"}
    assert _tree(root) == before  # Planning itself is read-only.

    saved = project_options_service.apply_project_options_change(plan)

    assert saved["voice_assignment_mode"] == requested
    assert saved["current_stage"] == "narrator_definition_ready"
    assert saved["narrator_profile_name"] == "Chosen narrator"
    assert not (root / "audio_character_alice.wav").exists()
    assert not (root / config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME).exists()
    assert not (root / "audio_blocks/block.wav").exists()
    assert not (root / "audiobook/book.wav").exists()
    targets = json.loads((root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).read_text())
    assert targets[0]["sample_metadata"] == {"kind": "keep"}
    assert targets[1]["sample_audio_path"] is None
    assert targets[1]["sample_metadata"] is None
    assert targets[1]["prompt_text"] == "Edited prompt"
    assert targets[1]["preview_text"] == "Edited preview"
    for name in (
        config.TRANSLATED_CHUNKS_FILE_NAME,
        config.CHARACTERS_DOCUMENT_FILE_NAME,
        config.NARRATOR_VOICE_FILE_NAME,
        config.BOOK_ANALYSIS_DOCUMENT_FILE_NAME,
        config.CHUNK_ARTIFACT_FILE_NAME,
        "audio_narator_selected.wav",
        "personal_notes.txt",
    ):
        assert (root / name).read_bytes() == before[name]
    assert all(saved["operations"][kind]["status"] == "not_started" for kind in plan.reset_operations)


def test_language_change_resets_translation_and_analysis_but_keeps_text(tmp_path):
    """@brief A new language resets its derived data and persists matching voice language."""
    root, _ = _processed_project(tmp_path)
    before = _tree(root)
    plan = project_options_service.plan_project_options_change(root, "ro", "narrator_and_characters")
    assert plan.requires_confirmation
    assert "book_analysis" in plan.affected_operations
    saved = project_options_service.apply_project_options_change(plan)
    assert saved["target_language"] == saved["selected_voice_language"] == "ro"
    assert saved["current_stage"] == "text_chunking_ready"
    assert saved["narrator_profile_name"] is None
    for name in (
        config.TRANSLATED_CHUNKS_FILE_NAME,
        config.BOOK_ANALYSIS_DOCUMENT_FILE_NAME,
        config.CHARACTERS_DOCUMENT_FILE_NAME,
        config.NARRATOR_VOICE_FILE_NAME,
        config.CHARACTER_VOICES_TARGETS_FILE_NAME,
        "audio_narator_selected.wav",
        "audio_character_alice.wav",
        "log_ai_book_analysis_1.log",
    ):
        assert not (root / name).exists(), name
    for name in (
        "story.txt",
        config.EXTRACTED_TEXT_FILE_NAME,
        config.CLEANED_TEXT_FILE_NAME,
        config.CHUNK_ARTIFACT_FILE_NAME,
        "personal_notes.txt",
    ):
        assert (root / name).read_bytes() == before[name]


def test_empty_language_autosave_and_same_value_are_non_destructive(tmp_path):
    """@brief Empty projects save directly and same-value changes do not write."""
    root, _ = project_workspace_service.create_project("EmptyOptions", tmp_path)
    plan = project_options_service.plan_project_options_change(root, "fr", "narrator_and_characters")
    assert not plan.requires_confirmation
    saved = project_options_service.apply_project_options_change(plan)
    assert saved["target_language"] == saved["selected_voice_language"] == "fr"
    assert saved["current_stage"] == "project_created"
    before = _tree(root)
    plan = project_options_service.plan_project_options_change(root, "fr", "narrator_and_characters")
    assert not plan.changed
    project_options_service.apply_project_options_change(plan)
    assert _tree(root) == before


@pytest.mark.parametrize("language", ["en", "ro"])
def test_option_write_failure_restores_all_project_bytes(monkeypatch, tmp_path, language):
    """@brief Failed final publication rolls back staged audio, metadata and the manifest."""
    root, _ = _processed_project(tmp_path)
    before = _tree(root)
    plan = project_options_service.plan_project_options_change(root, language, "same_narrator")

    def fail_save(*args, **kwargs):
        """@brief Fail save."""
        raise PermissionError("Injected manifest publication failure")

    monkeypatch.setattr(project_workspace_service, "save_manifest", fail_save)
    with pytest.raises(PermissionError):
        project_options_service.apply_project_options_change(plan)
    assert _tree(root) == before


@pytest.mark.parametrize("preexisting", [False, True])
def test_source_ready_creation_failure_keeps_destination(monkeypatch, tmp_path, preexisting):
    """@brief A failed source copy leaves no partial project and retains an old empty folder."""
    destination = tmp_path / "ImportFailure"
    if preexisting:
        destination.mkdir()

    def fail_copy(*args, **kwargs):
        """@brief Fail copy."""
        raise PermissionError("Injected source copy failure")

    monkeypatch.setattr(import_service, "import_source", fail_copy)
    with pytest.raises(PermissionError):
        project_options_service.create_project_with_source("ImportFailure", tmp_path, tmp_path / "book.txt")
    assert destination.exists() is preexisting
    assert list(tmp_path.iterdir()) == ([destination] if preexisting else [])


def test_stale_plan_is_rejected_without_deletion(tmp_path):
    """@brief A manifest changed after confirmation planning invalidates that plan."""
    root, manifest = _processed_project(tmp_path)
    plan = project_options_service.plan_project_options_change(root, "en", "same_narrator")
    manifest["notes"] = "A newer edit"
    project_workspace_service.save_manifest(manifest, root)
    before = _tree(root)
    with pytest.raises(ValueError, match="changed"):
        project_options_service.apply_project_options_change(plan)
    assert _tree(root) == before


@pytest.mark.parametrize("relative_path", ["../outside.wav", "C:/outside.wav"])
def test_reset_rejects_unsafe_character_sample_paths(tmp_path, relative_path):
    """@brief Untrusted target metadata cannot redirect a reset outside the workspace."""
    root, _ = _processed_project(tmp_path)
    targets_path = root / config.CHARACTER_VOICES_TARGETS_FILE_NAME
    targets = json.loads(targets_path.read_text())
    targets[1]["sample_audio_path"] = relative_path
    targets_path.write_text(json.dumps(targets), encoding="utf-8")
    before = _tree(root)
    with pytest.raises(ValueError):
        project_options_service.plan_project_options_change(root, "en", "same_narrator")
    assert _tree(root) == before


def test_reset_rejects_symlinked_audio_folder(tmp_path):
    """@brief A redirected generated-audio directory is rejected without touching its target."""
    root, _ = _processed_project(tmp_path)
    (root / "audio_blocks/block.wav").unlink()
    (root / "audio_blocks").rmdir()
    external = tmp_path / "external_audio"
    external.mkdir()
    (external / "keep.wav").write_bytes(b"outside export")
    try:
        (root / "audio_blocks").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symbolic links requires Windows Developer Mode or privilege")
    with pytest.raises(ValueError, match="redirected|outside"):
        project_options_service.plan_project_options_change(root, "en", "same_narrator")
    assert (external / "keep.wav").read_bytes() == b"outside export"


def test_partial_staging_failure_restores_previously_moved_files(monkeypatch, tmp_path):
    """@brief An error after the first moved artifact restores that original too."""
    root, _ = _processed_project(tmp_path)
    plan = project_options_service.plan_project_options_change(root, "en", "same_narrator")
    before = _tree(root)
    original_replace = Path.replace
    count = 0

    def fail_second_move(path, destination):
        """@brief Fail second move."""
        nonlocal count
        count += 1
        if count == 2:
            raise PermissionError("Injected staging failure")
        return original_replace(path, destination)

    monkeypatch.setattr(Path, "replace", fail_second_move)
    with pytest.raises(PermissionError):
        project_options_service.apply_project_options_change(plan)
    assert _tree(root) == before


def test_voice_plan_write_failure_restores_all_originals(monkeypatch, tmp_path):
    """@brief Failure while rewriting sample metadata preserves voice edits and every result."""
    root, _ = _processed_project(tmp_path)
    plan = project_options_service.plan_project_options_change(root, "en", "same_narrator")
    before = _tree(root)

    def fail_targets(*args, **kwargs):
        """@brief Fail targets."""
        raise PermissionError("Injected target metadata write failure")

    monkeypatch.setattr(project_options_service, "write_json_atomic", fail_targets)
    with pytest.raises(PermissionError):
        project_options_service.apply_project_options_change(plan)
    assert _tree(root) == before


def test_initial_import_manifest_failure_removes_new_copy(monkeypatch, tmp_path):
    """@brief A failed first import into a legacy empty project retains its original bytes."""
    root, _ = project_workspace_service.create_project("LegacyEmpty", tmp_path)
    source = tmp_path / "book.txt"
    source.write_text("Original book", encoding="utf-8")
    before = _tree(root)

    def fail_manifest(*args, **kwargs):
        """@brief Inject a persistence failure after the source copy."""
        raise PermissionError("Manifest is read-only")

    monkeypatch.setattr(project_workspace_service, "save_manifest", fail_manifest)
    with pytest.raises(PermissionError):
        project_options_service.import_initial_source(root, source, "ro", "same_narrator")
    assert _tree(root) == before


@pytest.mark.skipif(os.name != "nt", reason="Windows junction containment case")
def test_reset_rejects_windows_junction_audio_folder(tmp_path):
    """@brief Junction redirection is rejected without requiring symbolic-link privilege."""
    root, _ = _processed_project(tmp_path)
    (root / "audio_blocks/block.wav").unlink()
    (root / "audio_blocks").rmdir()
    external = tmp_path / "external_junction_target"
    external.mkdir()
    (external / "keep.wav").write_bytes(b"outside export")
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(root / "audio_blocks"), str(external)], check=True, capture_output=True
    )
    with pytest.raises(ValueError, match="redirected|outside"):
        project_options_service.plan_project_options_change(root, "en", "same_narrator")
    assert (external / "keep.wav").read_bytes() == b"outside export"


def test_mode_only_change_preserves_legacy_voice_language(tmp_path):
    """@brief Narration changes retain an unlocked project's independently selected voice language."""
    root, manifest = _processed_project(tmp_path)
    manifest["target_language"] = "ro"
    manifest["selected_voice_language"] = "en"
    project_workspace_service.save_manifest(manifest, root)
    plan = project_options_service.plan_project_options_change(root, "ro", "same_narrator")
    assert not plan.language_changed
    saved = project_options_service.apply_project_options_change(plan)
    assert saved["target_language"] == "ro"
    assert saved["selected_voice_language"] == "en"
    assert saved["narrator_language"] == "en"
    assert saved["project_options_locked"] is False


def test_failed_recovery_preserves_original_paths_in_backup(monkeypatch, tmp_path):
    """@brief Recovery originals keep project-relative names if restoration also fails."""
    root, _ = _processed_project(tmp_path)
    before = _tree(root)
    plan = project_options_service.plan_project_options_change(root, "en", "same_narrator")
    original_replace = Path.replace

    def fail_publication(*args):
        """@brief Inject the original publication error."""
        raise PermissionError("Publication failed")

    def fail_restoration(path, destination):
        """@brief Leave backup files in place when restoration is denied."""
        if any(part.startswith(".audiomancer-options-") for part in path.parts):
            raise PermissionError("Restoration failed")
        return original_replace(path, destination)

    monkeypatch.setattr(project_workspace_service, "save_manifest", fail_publication)
    monkeypatch.setattr(Path, "replace", fail_restoration)
    with pytest.raises(OSError, match="recovery originals retained"):
        project_options_service.apply_project_options_change(plan)
    backups = list(root.glob(".audiomancer-options-*"))
    assert len(backups) == 1
    for relative_path in (
        config.PROJECT_MANIFEST_FILE_NAME,
        config.CHARACTER_VOICES_TARGETS_FILE_NAME,
        "audio_character_alice.wav",
        "audio_blocks/block.wav",
        "audiobook/book.wav",
    ):
        assert (backups[0] / relative_path).read_bytes() == before[relative_path]


# END OF FILE
