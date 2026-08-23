#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_import_service.py
@brief Focused tests for the AudioMancer source import service.
@details Verifies source-format acceptance, rejection, copy behavior, and
         collision-safe storage naming under one project workspace.
"""

# IMPORTS

import pytest

from audiomancer.services import import_service

# PUBLIC API


@pytest.mark.parametrize(
    ("suffix", "file_type"),
    [
        (".txt", "txt"),
        (".pdf", "pdf"),
        (".rtf", "rtf"),
        (".docx", "docx"),
        (".odt", "odt"),
        (".md", "md"),
        (".epub", "epub"),
    ],
)
def test_import_source_accepts_supported_formats(tmp_path, suffix: str, file_type: str) -> None:
    """
    @brief      Verify supported source suffixes are accepted and normalized.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  suffix Tested file suffix.
    @param[in]  file_type Expected normalized file-type token.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    source_path = tmp_path / f"input{suffix}"
    source_path.write_text("sample", encoding="utf-8")

    payload = import_service.import_source(project_root, source_path)

    assert payload["file_type"] == file_type
    assert payload["original_name"] == source_path.name
    assert (project_root / source_path.name).is_file()


def test_import_source_rejects_unsupported_doc_format(tmp_path) -> None:
    """
    @brief      Verify unsupported binary `.doc` files are rejected.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    source_path = tmp_path / "unsupported.doc"
    source_path.write_text("sample", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported source format"):
        import_service.import_source(project_root, source_path)


def test_import_source_copies_file_and_records_metadata(tmp_path) -> None:
    """
    @brief      Verify import copies the source into the project root and records metadata.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    source_path = tmp_path / "story.md"
    source_path.write_text("# Chapter 1", encoding="utf-8")

    payload = import_service.import_source(project_root, source_path)

    assert payload["stored_relative_path"] == "story.md"
    assert payload["size_bytes"] == len(b"# Chapter 1")
    assert payload["imported_at"]
    assert (project_root / "story.md").read_text(encoding="utf-8") == "# Chapter 1"


def test_import_source_avoids_name_collisions(tmp_path) -> None:
    """
    @brief      Verify repeated imports with the same file name avoid collisions.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "story.txt").write_text("existing", encoding="utf-8")
    source_path = tmp_path / "story.txt"
    source_path.write_text("new", encoding="utf-8")

    payload = import_service.import_source(project_root, source_path)

    assert payload["stored_relative_path"] == "story_1.txt"
    assert (project_root / "story_1.txt").read_text(encoding="utf-8") == "new"


@pytest.mark.parametrize(
    ("reserved_name", "safe_name"),
    [
        ("extracted_text.txt", "extracted_text_1.txt"),
        ("clean_text.txt", "clean_text_1.txt"),
        ("EXTRACTED_TEXT.TXT", "EXTRACTED_TEXT_1.TXT"),
    ],
)
def test_import_source_avoids_reserved_generated_artifact_names(
    tmp_path,
    reserved_name: str,
    safe_name: str,
) -> None:
    """
    @brief      Verify source storage never claims a generated-artifact path.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  reserved_name Supported source name reserved by one operation.
    @param[in]  safe_name Expected collision-safe stored file name.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    source_path = tmp_path / reserved_name
    source_path.write_text("source text", encoding="utf-8")

    payload = import_service.import_source(project_root, source_path)

    assert payload["stored_relative_path"] == safe_name
    assert (project_root / safe_name).read_text(encoding="utf-8") == "source text"
    assert not (project_root / reserved_name).exists()


def test_import_source_replaces_previous_project_source_file(tmp_path) -> None:
    """
    @brief      Verify replacing a pre-start source deletes the previous project copy.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    old_project_source = project_root / "old_story.txt"
    old_project_source.write_text("old", encoding="utf-8")
    source_path = tmp_path / "new_story.txt"
    source_path.write_text("new", encoding="utf-8")

    payload = import_service.import_source(
        project_root,
        source_path,
        {"stored_relative_path": "old_story.txt"},
    )

    assert payload["stored_relative_path"] == "new_story.txt"
    assert old_project_source.exists() is False
    assert (project_root / "new_story.txt").read_text(encoding="utf-8") == "new"


def test_import_source_copy_failure_preserves_complete_previous_project_state(
    monkeypatch,
    tmp_path,
) -> None:
    """
    @brief      Verify a failed replacement copy leaves every prior project file unchanged.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    old_project_source = project_root / "old_story.txt"
    old_project_source.write_text("old source", encoding="utf-8")
    (project_root / "project.json").write_text('{"current_stage":"cleanup_ready"}\n', encoding="utf-8")
    (project_root / "extracted_text.txt").write_text("old extracted", encoding="utf-8")
    (project_root / "clean_text.txt").write_text("old cleaned", encoding="utf-8")
    (project_root / "chunks_text.json").write_text('{"old":true}\n', encoding="utf-8")
    source_path = tmp_path / "new_story.txt"
    source_path.write_text("new source", encoding="utf-8")
    previous_state = {
        path.relative_to(project_root).as_posix(): path.read_bytes()
        for path in project_root.rglob("*")
        if path.is_file()
    }

    def _fail_after_partial_copy(_source_path, destination_path) -> None:
        destination_path.write_text("partial new source", encoding="utf-8")
        raise OSError("simulated copy failure")

    monkeypatch.setattr(import_service.shutil, "copy2", _fail_after_partial_copy)

    with pytest.raises(OSError, match="simulated copy failure"):
        import_service.import_source(
            project_root,
            source_path,
            {"stored_relative_path": "old_story.txt"},
        )

    current_state = {
        path.relative_to(project_root).as_posix(): path.read_bytes()
        for path in project_root.rglob("*")
        if path.is_file()
    }
    assert current_state == previous_state


def test_import_source_rejects_previous_source_traversal_path(tmp_path) -> None:
    """
    @brief      Verify replacement cleanup rejects previous source paths outside the project.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    outside_source = tmp_path / "outside.txt"
    outside_source.write_text("outside", encoding="utf-8")
    source_path = tmp_path / "new_story.txt"
    source_path.write_text("new", encoding="utf-8")

    with pytest.raises(ValueError, match="Project-relative path"):
        import_service.import_source(
            project_root,
            source_path,
            {"stored_relative_path": "../outside.txt"},
        )

    assert outside_source.read_text(encoding="utf-8") == "outside"
    assert not (project_root / "new_story.txt").exists()


def test_import_source_reselects_existing_project_copy_without_mutation(tmp_path) -> None:
    """
    @brief      Verify selecting the registered project source is an exact no-op.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    stored_source = project_root / "story.txt"
    stored_source.write_text("stored source", encoding="utf-8")
    previous_source = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-08-07T12:00:00+00:00",
        "size_bytes": stored_source.stat().st_size,
    }
    before = {
        path.relative_to(project_root).as_posix(): path.read_bytes()
        for path in project_root.rglob("*")
        if path.is_file()
    }

    result = import_service.import_source(project_root, project_root / "." / "story.txt", previous_source)

    after = {
        path.relative_to(project_root).as_posix(): path.read_bytes()
        for path in project_root.rglob("*")
        if path.is_file()
    }
    assert result == previous_source
    assert after == before


def test_import_source_replaces_with_different_external_file_of_same_name(tmp_path) -> None:
    """
    @brief      Verify a different same-named file remains a real replacement.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    stored_source = project_root / "story.txt"
    stored_source.write_text("stored source", encoding="utf-8")
    external_source = tmp_path / "external" / "story.txt"
    external_source.parent.mkdir()
    external_source.write_text("replacement source", encoding="utf-8")

    result = import_service.import_source(
        project_root,
        external_source,
        {"stored_relative_path": "story.txt"},
    )

    assert result["stored_relative_path"] == "story_1.txt"
    assert not stored_source.exists()
    assert (project_root / "story_1.txt").read_text(encoding="utf-8") == "replacement source"


# END OF FILE
