#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_cleanup_refinement.py
@brief Regression coverage for isolated, recoverable Cleanup processing.
@details Exercises page semantics, operator edits, cancellation and IO recovery
         using synthetic local projects without provider calls.
"""

# IMPORTS

import os
from pathlib import Path
import subprocess
import sys

import pytest

from audiomancer import config
from audiomancer.cleanup import analysis as analysis
from audiomancer.cleanup import render as render
from audiomancer.services import project_workspace_service, text_cleanup_service
from audiomancer.services.operation_runtime_service import OperationCancelledError
from cleanup_test_support import build_ledger, build_project, make_profile


def _render(texts, **kwargs):
    """@brief Render a synthetic ledger through the production deterministic path."""
    text, ledger = build_ledger(texts, **kwargs)
    result = analysis.analyze_cleanup(text, ledger)
    output, metadata = render.render_cleanup(text, ledger, result["unit_operations"], result["boundaries"])
    return output, metadata, result


@pytest.mark.parametrize("role", ["heading", "verse", "preformatted"])
def test_page_boundary_honors_roles(role):
    """@brief Page heuristics cannot collapse a protected structural boundary."""
    output, _, _ = _render(
        ["An unfinished thought", "Chapter 2" if role == "heading" else "Another line"],
        source_format="pdf",
        kinds=["body" if role == "heading" else role, role],
        boundaries=[("\n\n\f\n\n", "page")],
        locators=[{"page_index": 0}, {"page_index": 1}],
    )
    assert output == (
        "An unfinished thought\n\nChapter 2\n" if role == "heading" else "An unfinished thought\nAnother line\n"
    )


@pytest.mark.parametrize(
    ("hyphen", "expected"), [("-", "inter-national story.\n"), ("\u00ad", "international story.\n")]
)
def test_page_boundary_repairs_hyphenation(hyphen, expected):
    """@brief Hyphenation retains its typed choices across physical pages."""
    output, _, result = _render(
        ["inter" + hyphen, "national story."],
        source_format="pdf",
        boundaries=[("\n\n\f\n\n", "page")],
        locators=[{"page_index": 0}, {"page_index": 1}],
    )
    assert output == expected
    if hyphen == "-":
        assert "dehyphenate" in result["questions"][0]["choices"]


def test_inferred_verse_uses_recorded_indentation():
    """@brief Unequal recorded indentation prevents inferred verse roles."""
    _, _, result = _render(
        ["Intro.", "Short words float", "This prose is indented", "A thought continues", "End."],
        boundaries=[
            ("\n\n", "blank_paragraph"),
            ("\n", "physical_line"),
            ("\n", "physical_line"),
            ("\n\n", "blank_paragraph"),
        ],
        locators=[{}, {"leading_spaces": 0}, {"leading_spaces": 8}, {"leading_spaces": 1}, {}],
    )
    assert not any(op.get("role") == "verse" for op in result["unit_operations"])


def _completed_project(tmp_path):
    """@brief Seed a completed Cleanup plus a downstream result for preservation tests."""
    text, ledger = build_ledger(
        ["Chapter 1", "A body paragraph.", "A verse line"],
        kinds=["heading", "paragraph", "verse"],
        origins=["native"] * 3,
        boundaries=[("\n\n", "native_paragraph")] * 2,
    )
    root, manifest = build_project(tmp_path, "CleanupRecovery", text, ledger)
    text_cleanup_service.clean_text(root, manifest)
    (root / config.CHUNK_ARTIFACT_FILE_NAME).write_bytes(b"previous chunks")
    snapshot = {p: p.read_bytes() for p in root.iterdir() if p.is_file()}
    return root, project_workspace_service.load_manifest(root), snapshot


@pytest.mark.parametrize("percent", [94, 98])
def test_cancelled_rerun_preserves_completed_project(tmp_path, percent):
    """@brief Cancellation during rendering/persistence leaves the old result usable."""
    root, manifest, snapshot = _completed_project(tmp_path)
    progress = []
    with pytest.raises(OperationCancelledError):
        text_cleanup_service.clean_text(
            root,
            manifest,
            force=True,
            progress_callback=lambda _a, _b, value, _message: progress.append(value),
            cancel_requested=lambda: percent in progress,
        )
    assert 100 not in progress
    assert all(path.read_bytes() == content for path, content in snapshot.items())
    assert text_cleanup_service.load_cleanup_document(root)["status"] == "completed"
    text_cleanup_service.clean_text(root, manifest)
    assert not (root / config.CHUNK_ARTIFACT_FILE_NAME).exists()
    assert not (root / "cleanup_pending.json").exists()


@pytest.mark.parametrize("target_name", ["clean_text.txt", "cleanup.json", "project_manifest.json"])
def test_publication_rename_failure_restores_originals(tmp_path, monkeypatch, target_name):
    """@brief Failure during replacement restores old text, metadata and downstream files."""
    root, _, snapshot = _completed_project(tmp_path)
    target_name = config.PROJECT_MANIFEST_FILE_NAME if target_name == "project_manifest.json" else target_name
    original_replace = Path.replace
    failed = False

    def fail_once(path, target):
        """@brief Inject one staged-file failure while allowing rollback renames."""
        nonlocal failed
        if not failed and ".cleanup-stage-" in str(path) and Path(target) == root / target_name:
            failed = True
            raise OSError("injected replacement failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_once)
    with pytest.raises(OSError, match="injected replacement failure"):
        text_cleanup_service.save_user_cleaned_text(root, "An edited body.\n")
    assert failed
    assert all(path.read_bytes() == content for path, content in snapshot.items())


def test_lexical_edit_preserves_only_exact_unique_paragraphs(tmp_path):
    """@brief Correcting prose preserves an unchanged heading and verse provenance."""
    root, _, _ = _completed_project(tmp_path)
    document = text_cleanup_service.save_user_cleaned_text(root, "Chapter 1\n\nA corrected body.\n\nA verse line\n")
    assert document["structure_source"] == "user_edited"
    assert [p["role"] for p in document["paragraphs"]] == ["heading", "body", "verse"]
    assert [p["provenance_available"] for p in document["paragraphs"]] == [True, False, True]


def test_cleanup_core_imports_without_application_services():
    """@brief The processing package runs in a fresh process with IO/provider imports blocked."""
    script = """
import sys
class Block:
    def find_spec(self, fullname, *args):
        if fullname.startswith(('audiomancer.services', 'audiomancer.config', 'PySide6')):
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
from audiomancer.cleanup import analysis, render
from audiomancer.extraction.document import CanonicalDocumentBuilder
from audiomancer.extraction.models import SourceEvent
b = CanonicalDocumentBuilder(source_format='txt', source_sha256='test', structure_quality='text_only')
b.add(SourceEvent('A complete paragraph.'))
text, ledger = b.build()
plan = analysis.analyze_cleanup(text, ledger)
output, _ = render.render_cleanup(text, ledger, plan['unit_operations'], plan['boundaries'])
assert output == 'A complete paragraph.\\n'
"""
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).parents[1] / "src"))
    result = subprocess.run([sys.executable, "-B", "-c", script], capture_output=True, text=True, env=env, check=False)
    assert result.returncode == 0, result.stderr


def test_paragraph_metadata_traverses_source_records_linearly():
    """@brief Thousands of paragraphs require a bounded number of source-record visits."""

    class Observed(list):
        """@brief Count traversal work without a machine-dependent timing assertion."""

        visits = 0

        def __iter__(self):
            for item in super().__iter__():
                self.visits += 1
                yield item

        def __getitem__(self, index):
            self.visits += 1
            return super().__getitem__(index)

    count = 2000
    spans = Observed(
        [
            {"unit_id": str(i), "start": i * 3, "end": i * 3 + 1, "role": "body", "source_page": None}
            for i in range(count)
        ]
    )
    boundaries = Observed(
        [
            {
                "output_start": i * 3 + 1,
                "output_end": i * 3 + 3,
                "page_transition": False,
                "final": {"confidence": "strong", "reason_codes": [], "choice": "set_paragraph_break"},
            }
            for i in range(count)
        ]
    )
    records = render._paragraph_records("x\n\n" * count, spans, boundaries)
    assert len(records) == count
    assert records[-1]["output_start"] == (count - 1) * 3
    assert spans.visits + boundaries.visits < count * 30


@pytest.mark.parametrize(
    "edited",
    [
        "Chapter 1\n\nChapter 1\n\nA verse line\n",
        "chapter 1\n\nChanged prose.\n\nA verse line\n",
    ],
)
def test_lexical_edit_leaves_duplicate_and_case_changed_matches_unresolved(tmp_path, edited):
    """@brief Exact uniqueness excludes duplicate and case-only lexical replacements."""
    root, _, _ = _completed_project(tmp_path)
    document = text_cleanup_service.save_user_cleaned_text(root, edited)
    assert [p["role"] for p in document["paragraphs"]] == ["body", "body", "verse"]
    assert [p["provenance_available"] for p in document["paragraphs"]] == [False, False, True]
    assert "user_exact_paragraph_match" not in document["paragraphs"][0]["reason_codes"]


def test_cancel_during_rendering_and_finalizing_resume_preserves_outputs(tmp_path, monkeypatch):
    """@brief Cancellation from inside the renderer and on resume cannot publish a replacement."""
    root, manifest, snapshot = _completed_project(tmp_path)
    original = render._paragraph_records
    cancelled = False

    def cancel_inside(*args, **kwargs):
        """@brief Request cancellation at the paragraph projection boundary."""
        nonlocal cancelled
        cancelled = True
        return original(*args, **kwargs)

    monkeypatch.setattr(render, "_paragraph_records", cancel_inside)
    with pytest.raises(OperationCancelledError):
        text_cleanup_service.clean_text(root, manifest, force=True, cancel_requested=lambda: cancelled)
    with pytest.raises(OperationCancelledError):
        text_cleanup_service.clean_text(root, manifest, cancel_requested=lambda: True)
    assert all(path.read_bytes() == content for path, content in snapshot.items())


@pytest.mark.parametrize("hyphen", ["-", "\u00ad"])
def test_page_artifact_bridge_uses_retained_text_and_hyphen_choices(hyphen):
    """@brief Footer removal preserves hyphenation and supplies retained right context to AI."""
    texts, boundaries, layouts, locators = [], [], [], []
    for page in range(4):
        if texts:
            boundaries.append(("\n\n\f\n\n", "page"))
        texts.extend(["inter" + hyphen, str(page + 1), "national story."])
        boundaries.extend([("\n", "visual_line"), ("\n", "visual_line")])
        layouts.extend([None, {"bbox": [20, 780, 30, 792], "relative_vertical_position": 0.98}, None])
        locators.extend([{"page_index": page}] * 3)
    output, metadata, result = _render(
        texts, source_format="pdf", boundaries=boundaries, layouts=layouts, locators=locators
    )
    assert output == ("inter-national story.\n\n" if hyphen == "-" else "international story.\n\n") * 3 + (
        "inter-national story.\n" if hyphen == "-" else "international story.\n"
    )
    assert metadata["quality_report"]["artifact_removal_count"] == 4
    if hyphen == "-":
        hyphen_questions = [q for q in result["questions"] if q["question_type"] == "hyphenation"]
        assert len(hyphen_questions) == 4
        assert all(q["right_text"] == "national story." for q in hyphen_questions)


def test_cancelled_ai_rerun_resumes_paid_answers_without_replacing_previous_result(tmp_path, monkeypatch):
    """@brief Replacement checkpoints preserve completed responses and the old published project."""
    from audiomancer.services import cleanup_ai_adjudication_service

    text, ledger = build_ledger(["One wrapped line", "continues here."])
    root, manifest = build_project(tmp_path, "AIReplacement", text, ledger)
    text_cleanup_service.clean_text(root, manifest)
    (root / config.CHUNK_ARTIFACT_FILE_NAME).write_bytes(b"old chunks")
    snapshot = {p: p.read_bytes() for p in root.iterdir() if p.is_file()}
    calls = []
    cancelled = False

    def answer(_profile, _batch, questions, **_kwargs):
        """@brief Return a completed primary response and request cancellation."""
        nonlocal cancelled
        calls.append(1)
        cancelled = True
        return [{"question_id": q["question_id"], "choice": q["prior_choice"]} for q in questions], {}

    monkeypatch.setattr(cleanup_ai_adjudication_service, "_ask", answer)
    profile = make_profile()
    with pytest.raises(OperationCancelledError):
        text_cleanup_service.clean_text(root, manifest, profile, force=True, cancel_requested=lambda: cancelled)
    assert all(path.read_bytes() == content for path, content in snapshot.items())
    cancelled = False
    text_cleanup_service.clean_text(root, manifest, profile, cancel_requested=lambda: cancelled)
    assert len(calls) == 1
    assert not (root / config.CHUNK_ARTIFACT_FILE_NAME).exists()
    assert not (root / config.CLEANUP_PENDING_FILE_NAME).exists()


@pytest.mark.parametrize("role", ["verse", "preformatted", "list_item"])
@pytest.mark.parametrize("entering", [False, True])
@pytest.mark.parametrize("bridge", [False, True])
def test_entering_and_leaving_structural_roles_preserves_paragraphs(role, entering, bridge):
    """@brief Structural block transitions remain separate with or without removed footers."""
    left_role, right_role = ("body", role) if entering else (role, "body")
    if not bridge:
        output, _, _ = _render(
            ["An unfinished block", "A distinct block."],
            kinds=[left_role, right_role],
            boundaries=[("\n\n\f\n\n", "page")],
            locators=[{"page_index": 0}, {"page_index": 1}],
        )
        assert output == "An unfinished block\n\nA distinct block.\n"
    else:
        output = _render_bridge(left_role, right_role, "visual_line")
        assert output == "An unfinished block\n\nA distinct block.\n\n" * 3 + (
            "An unfinished block\n\nA distinct block.\n"
        )


def _render_bridge(left_role, right_role, kind):
    """@brief Build four footer-bearing pages with one authoritative boundary per chain."""
    texts, kinds, boundaries, layouts, locators = [], [], [], [], []
    for page in range(4):
        if texts:
            boundaries.append(("\n\n\f\n\n", "page"))
        texts.extend(["An unfinished block", str(page + 1), "A distinct block."])
        kinds.extend([left_role, "unknown", right_role])
        boundaries.extend([("\n", "visual_line"), ("\n\n" if "paragraph" in kind else "\n", kind)])
        layouts.extend([None, {"bbox": [20, 780, 30, 792], "relative_vertical_position": 0.98}, None])
        locators.extend([{"page_index": page}] * 3)
    output, _, _ = _render(
        texts, kinds=kinds, boundaries=boundaries, layouts=layouts, locators=locators, source_format="pdf"
    )
    return output


@pytest.mark.parametrize("kind", ["native_paragraph", "blank_paragraph", "native_line_break"])
def test_artifact_bridge_preserves_authoritative_source_boundary(kind):
    """@brief A discarded footer cannot erase native/blank paragraphs or explicit line breaks."""
    output = _render_bridge("body", "body", kind)
    separator = "\n" if kind == "native_line_break" else "\n\n"
    pair = "An unfinished block" + separator + "A distinct block."
    assert output == (pair + "\n\n") * 3 + pair + "\n"


# END OF FILE
