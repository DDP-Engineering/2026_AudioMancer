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


# END OF FILE
