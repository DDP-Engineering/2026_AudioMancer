#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_chunking_refinement.py
@brief Regression tests for isolated, source-aligned Chunking.
@details Exercises structural materialization, bounded planning and recoverable publication.
"""

# IMPORTS

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from audiomancer import config
from audiomancer.services import (
    ai_chunking_service as ai,
)
from audiomancer.services import (
    chunking_document_service as documents,
)
from audiomancer.services import (
    chunking_edit_service as edits,
)
from audiomancer.services import (
    deterministic_chunking_service as deterministic,
)
from audiomancer.services import (
    operation_runtime_service as runtime,
)
from audiomancer.services import (
    project_workspace_service as workspace,
)
from audiomancer.services import (
    text_chunking_state_service as state,
)
from audiomancer.ui.controllers import text_chunking_ui_controller as controller
from chunking_test_support import write_cleanup_input

# HELPERS


def _records(*roles):
    """@brief Build mixed-role source records with distinct paragraph numbers."""
    return [
        {
            "text": f"Paragraph text {i}.",
            "role": role,
            "boundary_confidence": "strong",
            "warning_flags": [],
            "paragraph_number": i,
        }
        for i, role in enumerate(roles, 1)
    ]


def _ready(tmp_path, monkeypatch, text="First paragraph.\n\nSecond paragraph."):
    """@brief Create an isolated ready project and local fake-provider prompts."""
    root, manifest = workspace.create_project("Chunking", tmp_path)
    (root / "story.txt").write_text(text, encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-11-05T12:00:00+00:00",
        "size_bytes": len(text),
    }
    write_cleanup_input(root, text)
    workspace.save_manifest(manifest, root)
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "text_chunking_system.txt").write_text("{strategy}", encoding="utf-8")
    (prompts / "text_chunking_user.txt").write_text("{strategy}\n{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompts)
    return root, manifest


def _profile():
    """@brief Return a synthetic profile whose transport is always replaced."""
    return {
        "id": "fake",
        "model_name": "fake",
        "base_url": "http://localhost",
        "backend_kind": "lmstudio",
        "context_window": 4096,
        "output_reserve_tokens": 512,
        "temperature": 0.2,
    }


# TESTS


def test_every_ai_range_respects_structural_roles():
    """@brief A valid model range cannot merge a heading or different structural roles."""
    records = _records("heading", "body", "body", "verse", "page_artifact", "body")
    chunks = []
    ai._append_chunks_from_ranges(chunks, records, [{"start_index": 0, "end_index": 5}])
    assert [c["cleanup_role"] for c in chunks] == ["heading", "body", "verse", "page_artifact", "body"]
    assert [(c["source_paragraph_start"], c["source_paragraph_end"]) for c in chunks] == [
        (1, 1),
        (2, 3),
        (4, 4),
        (5, 5),
        (6, 6),
    ]


def test_group_confidence_is_the_weakest_and_unknown_is_honest():
    """@brief Confidence and warnings describe the whole group, including uncertain records."""
    records = _records("body", "body")
    records[1].update(boundary_confidence="low", warning_flags=["unknown_line_boundary"])
    chunk = ai._build_chunk_from_range(records, 0, 1, 1)
    assert chunk["cleanup_boundary_confidence"] == "low"
    assert chunk["cleanup_warning_flags"] == ["unknown_line_boundary"]
    records[1]["boundary_confidence"] = None
    assert ai._build_chunk_from_range(records, 0, 1, 1)["cleanup_boundary_confidence"] is None


def test_page_artifact_is_a_supported_retained_chunk():
    """@brief Artifact-only Cleanup records remain inspectable instead of failing publication."""
    chunk = deterministic._build_chunk_payload(1, {"text": "123", "role": "page_artifact"})
    assert (
        documents.build_document(status="completed", mode="deterministic", source_text="123", chunks=[chunk])["chunks"][
            0
        ]["text"]
        == "123"
    )


def test_inserted_prose_does_not_inherit_a_heading_role():
    """@brief Inserting after a heading starts with conservative manual metadata."""
    chunk = state._build_inserted_chunk_payload({"sequence_index": 1, "cleanup_role": "heading"}, "chunk-0002")
    assert chunk["cleanup_role"] == "body"
    assert chunk["source_paragraph_start"] is None


def test_oversized_paragraph_bypasses_provider_and_remaining_text_continues(tmp_path, monkeypatch):
    """@brief Never send a paragraph larger than its available text budget to AI."""
    large = "Very long source " * 400
    root, manifest = _ready(tmp_path, monkeypatch, large + "\n\nShort source.")
    monkeypatch.setattr(
        ai, "_build_budget_metadata", lambda *a, **k: {"text_budget_tokens": 30, "strategy_paragraph_cap": 1}
    )
    prompts = []

    def respond(profile, system, user, **kwargs):
        """@brief Capture only synthetic provider requests."""
        prompts.append(user)
        return {"payload": {"chunks": []}}

    monkeypatch.setattr(ai.llm_provider_service, "chat_json", respond)
    ai.chunk_text(root, manifest, _profile(), "paragraph")
    assert len(prompts) == 1
    assert large.strip() not in prompts[0]
    document = documents.load_chunking_document(root)
    assert document["chunks"][0]["text"] == large.strip()
    assert any("budget" in warning.lower() for warning in document["warnings"])


def test_window_runtime_estimates_paragraphs_once(tmp_path, monkeypatch):
    """@brief Replanning from each prefix must not repeatedly estimate the entire suffix."""
    root, manifest = _ready(tmp_path, monkeypatch, "\n\n".join(f"Source {i}." for i in range(40)))
    monkeypatch.setattr(
        ai, "_build_budget_metadata", lambda *a, **k: {"text_budget_tokens": 100, "strategy_paragraph_cap": 1}
    )
    monkeypatch.setattr(ai.llm_provider_service, "chat_json", lambda *a, **k: {"payload": {"chunks": []}})
    original = ai._estimate_text_tokens
    calls = []

    def estimate(text):
        """@brief Count paragraph-unit estimates at the runtime seam."""
        calls.append(text)
        return original(text)

    monkeypatch.setattr(ai, "_estimate_text_tokens", estimate)
    ai.chunk_text(root, manifest, _profile(), "paragraph")
    assert len(calls) == 40


def test_cancelled_replacement_keeps_published_chunks_and_downstream(tmp_path, monkeypatch):
    """@brief Completed chunks and translation survive a cancelled regeneration."""
    root, manifest = _ready(tmp_path, monkeypatch)
    deterministic.chunk_text(root, manifest)
    path = root / config.CHUNK_ARTIFACT_FILE_NAME
    before = path.read_bytes()
    translated = root / config.TRANSLATED_CHUNKS_FILE_NAME
    translated.write_text("sentinel", encoding="utf-8")
    with pytest.raises(runtime.OperationCancelledError):
        deterministic.chunk_text(root, workspace.load_manifest(root), cancel_requested=lambda: True)
    assert path.read_bytes() == before
    assert translated.read_text(encoding="utf-8") == "sentinel"
    assert (root / "chunking_pending.json").is_file()


def test_corrupted_checkpoint_text_is_rejected_before_mutation(tmp_path, monkeypatch):
    """@brief Matching source hashes alone cannot authorize a corrupted committed prefix."""
    root, manifest = _ready(tmp_path, monkeypatch)
    checks = []

    def cancelled():
        """@brief Stop after the first deterministic paragraph."""
        checks.append(True)
        return len(checks) > 1

    with pytest.raises(runtime.OperationCancelledError):
        deterministic.chunk_text(root, manifest, cancel_requested=cancelled)
    path = root / config.CHUNK_ARTIFACT_FILE_NAME
    data = json.loads(path.read_text(encoding="utf-8"))
    data["chunks"][0]["text"] = "Fabricated prefix"
    path.write_text(json.dumps(data), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        deterministic.chunk_text(root, manifest)
    assert path.read_bytes() == before


def test_manual_failure_leaves_published_chunk_bytes_untouched(tmp_path, monkeypatch):
    """@brief Selective downstream failure must not partially save a manual text edit."""
    root, manifest = _ready(tmp_path, monkeypatch)
    deterministic.chunk_text(root, manifest)
    path = root / config.CHUNK_ARTIFACT_FILE_NAME
    before = path.read_bytes()

    def fail(*args, **kwargs):
        """@brief Simulate an IO failure after the chunk write."""
        raise OSError("Cannot save translation")

    monkeypatch.setattr(edits.ai_translation_service, "sync_translation_after_chunk_change", fail)
    with pytest.raises(OSError):
        state.save_chunk_text_edit(root, manifest, "chunk-0001", "Edited source.")
    assert path.read_bytes() == before


def test_changed_model_resume_retains_prefix_and_reports_policy_change(tmp_path, monkeypatch):
    """@brief Runtime policy changes apply only to the verified unprocessed source suffix."""
    root, manifest = _ready(tmp_path, monkeypatch)
    monkeypatch.setattr(
        ai, "_build_budget_metadata", lambda *a, **k: {"text_budget_tokens": 100, "strategy_paragraph_cap": 1}
    )
    calls = []

    def respond(*a, **k):
        """@brief Resolve one window using deterministic fallback."""
        calls.append(True)
        return {"payload": {"chunks": []}}

    monkeypatch.setattr(ai.llm_provider_service, "chat_json", respond)
    with pytest.raises(runtime.OperationCancelledError):
        ai.chunk_text(root, manifest, _profile(), "paragraph", cancel_requested=lambda: len(calls) == 1)
    prefix = documents.load_chunking_document(root)["chunks"][0]
    profile = dict(_profile(), model_name="different-model")
    ai.chunk_text(root, manifest, profile, "paragraph")
    result = documents.load_chunking_document(root)
    assert result["chunks"][0] == prefix
    assert any("policy" in warning.lower() for warning in result["warnings"])


@pytest.mark.parametrize("mode", ["deterministic", "ai_assisted"])
def test_generation_publication_failure_restores_chunks_manifest_and_audio(tmp_path, monkeypatch, mode):
    """@brief A failed final file replacement restores the whole published owned set."""
    root, manifest = _ready(tmp_path, monkeypatch)
    deterministic.chunk_text(root, manifest)
    audio = root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME / "nested" / "take.wav"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"large-audio-sentinel")
    paths = (root / config.CHUNK_ARTIFACT_FILE_NAME, root / config.PROJECT_MANIFEST_FILE_NAME, audio)
    originals = {path: path.read_bytes() for path in paths}
    replace = Path.replace

    def fail_manifest(self, target):
        """@brief Fail after staging succeeds and original files have been backed up."""
        if self.parent.name.startswith(".chunking-stage-") and self.name == config.PROJECT_MANIFEST_FILE_NAME:
            raise OSError("Injected publication failure")
        return replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_manifest)
    requests = []

    def respond(*args, **kwargs):
        """@brief Track paid-work boundaries while returning a synthetic fallback response."""
        requests.append(True)
        return {"payload": {"chunks": []}}

    monkeypatch.setattr(ai.llm_provider_service, "chat_json", respond)

    def run():
        """@brief Run or resume the selected mode using the currently published project."""
        if mode == "deterministic":
            return deterministic.chunk_text(root, workspace.load_manifest(root))
        return ai.chunk_text(root, workspace.load_manifest(root), _profile(), "paragraph")

    with pytest.raises(OSError, match="publication failure"):
        run()
    assert all(path.read_bytes() == data for path, data in originals.items())
    assert not list(root.glob(".chunking-backup-*"))
    pending = documents.load_checkpoint(root)
    assert pending["status"] == "failed"
    assert pending["next_paragraph"] == 3
    assert pending["chunks"][-1]["source_paragraph_end"] == 2
    completed_requests = len(requests)
    monkeypatch.setattr(Path, "replace", replace)
    run()
    assert len(requests) == completed_requests
    assert not (root / config.CHUNKING_PENDING_FILE_NAME).exists()
    assert not audio.exists()


def test_failed_restoration_retains_identifiable_originals(tmp_path, monkeypatch):
    """@brief Denied restoration leaves a named backup containing original relative paths."""
    root, manifest = _ready(tmp_path, monkeypatch)
    deterministic.chunk_text(root, manifest)
    before = (root / config.CHUNK_ARTIFACT_FILE_NAME).read_bytes()
    replace = Path.replace

    def fail_publication_and_restore(self, target):
        """@brief Deny one publication and one original-file restoration."""
        if self.parent.name.startswith(".chunking-stage-") and self.name == config.PROJECT_MANIFEST_FILE_NAME:
            raise OSError("Publish denied")
        if self.parent.name.startswith(".chunking-backup-") and self.name == config.CHUNK_ARTIFACT_FILE_NAME:
            raise OSError("Restore denied")
        return replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_publication_and_restore)
    with pytest.raises(OSError, match="originals retained in"):
        deterministic.chunk_text(root, workspace.load_manifest(root))
    backups = list(root.glob(".chunking-backup-*"))
    assert len(backups) == 1
    assert (backups[0] / config.CHUNK_ARTIFACT_FILE_NAME).read_bytes() == before
    assert documents.load_chunking_document(root, pending=True)["status"] == "failed"


def test_manual_publication_failure_restores_originals(tmp_path, monkeypatch):
    """@brief Manual edit publication has the same rollback boundary as regeneration."""
    root, manifest = _ready(tmp_path, monkeypatch)
    deterministic.chunk_text(root, manifest)
    paths = (root / config.CHUNK_ARTIFACT_FILE_NAME, root / config.PROJECT_MANIFEST_FILE_NAME)
    originals = {path: path.read_bytes() for path in paths}
    replace = Path.replace

    def fail_chunk(self, target):
        """@brief Reject the prepared manual chunk artifact at publication time."""
        if self.parent.name.startswith(".chunking-edit-") and self.name == config.CHUNK_ARTIFACT_FILE_NAME:
            raise OSError("Manual publication failure")
        return replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_chunk)
    with pytest.raises(OSError, match="Manual publication failure"):
        state.save_chunk_text_edit(root, manifest, "chunk-0001", "Changed prose.")
    assert all(path.read_bytes() == data for path, data in originals.items())


def test_cleanup_metadata_change_rejects_resume_without_touching_checkpoint(tmp_path, monkeypatch):
    """@brief Equal text hashes cannot hide changed paragraph roles in a resume plan."""
    root, manifest = _ready(tmp_path, monkeypatch)
    with pytest.raises(runtime.OperationCancelledError):
        deterministic.chunk_text(root, manifest, cancel_requested=lambda: True)
    checkpoint = root / config.CHUNK_ARTIFACT_FILE_NAME
    before = checkpoint.read_bytes()
    path = root / config.CLEANUP_DOCUMENT_FILE_NAME
    cleanup = json.loads(path.read_text(encoding="utf-8"))
    cleanup["paragraphs"][0]["role"] = "heading"
    path.write_text(json.dumps(cleanup), encoding="utf-8")
    with pytest.raises(ValueError, match="plan changed"):
        deterministic.chunk_text(root, manifest)
    assert checkpoint.read_bytes() == before


def test_manual_edit_clears_only_changed_provenance(tmp_path, monkeypatch):
    """@brief Editing preserves sibling IDs and metadata while clearing stale source claims."""
    root, manifest = _ready(tmp_path, monkeypatch, "Chapter 1\n\nSecond paragraph.")
    deterministic.chunk_text(root, manifest)
    original = documents.load_chunks(root)
    state.save_chunk_text_edit(root, manifest, "chunk-0001", "Ordinary replacement prose.")
    changed = documents.load_chunks(root)
    assert changed[1] == original[1]
    assert changed[0]["chunk_id"] == original[0]["chunk_id"]
    assert changed[0]["source_paragraph_start"] is None
    assert changed[0]["cleanup_boundary_confidence"] is None
    assert changed[0]["cleanup_role"] == "body"


def _window(root, manifest):
    """@brief Supply only the controller contract without constructing the desktop shell."""
    return SimpleNamespace(
        _current_project_root=root,
        _current_manifest=manifest,
        _active_operation_kind=None,
        _settings_payload={"language": "en"},
    )


def test_confirmed_ui_rerun_defers_all_deletion_until_worker_success(tmp_path, monkeypatch):
    """@brief Confirming a rerun starts work while published dependent files remain intact."""
    root, manifest = _ready(tmp_path, monkeypatch)
    deterministic.chunk_text(root, manifest)
    dependent = root / config.TRANSLATED_CHUNKS_FILE_NAME
    dependent.write_bytes(b"sentinel")
    old_chunks = (root / config.CHUNK_ARTIFACT_FILE_NAME).read_bytes()
    window = _window(root, workspace.load_manifest(root))
    starts = []
    monkeypatch.setattr(controller, "confirm_chunking_rerun", lambda *a: True)
    monkeypatch.setattr(controller, "start_operation", lambda *a, **k: starts.append(k))
    controller.handle_deterministic_chunking_requested(window)
    assert len(starts) == 1
    assert dependent.read_bytes() == b"sentinel"
    assert (root / config.CHUNK_ARTIFACT_FILE_NAME).read_bytes() == old_chunks
    starts[0]["worker_callable"](root, window._current_manifest)
    assert not dependent.exists()


def test_pending_ai_resume_uses_checkpoint_instead_of_completed_manifest(tmp_path, monkeypatch):
    """@brief A pending replacement resumes without requesting fresh instructions or confirmation."""
    root, manifest = _ready(tmp_path, monkeypatch)
    deterministic.chunk_text(root, manifest)
    with pytest.raises(runtime.OperationCancelledError):
        ai.chunk_text(
            root,
            manifest,
            _profile(),
            "scene",
            cancel_requested=lambda: True,
            additional_chunking_instructions="Stored rules",
        )
    window = _window(root, workspace.load_manifest(root))
    window._settings_payload["llm_profiles"] = [_profile()]
    starts = []

    def unexpected(*args):
        """@brief A resume must not enter a new-run question flow."""
        pytest.fail("Unexpected new-run prompt")

    monkeypatch.setattr(controller, "prompt_ai_chunking_instructions", unexpected)
    monkeypatch.setattr(controller, "confirm_ai_chunking_rerun", unexpected)
    monkeypatch.setattr(controller, "start_operation", lambda *a, **k: starts.append(k))
    controller.handle_ai_chunking_requested(window, "fake", "meaning")
    assert len(starts) == 1
    calls = []
    monkeypatch.setattr(ai, "chunk_text", lambda *a, **k: calls.append((a, k)))
    starts[0]["worker_callable"](root, window._current_manifest)
    assert calls[0][0][3] == "scene"
    assert calls[0][1]["additional_chunking_instructions"] is None


def test_success_controller_reloads_manifest_without_writing_it_again(tmp_path, monkeypatch):
    """@brief The service is the single manifest publisher; success only refreshes the UI."""
    root, stale_manifest = _ready(tmp_path, monkeypatch)
    deterministic.chunk_text(root, stale_manifest)
    expected = workspace.load_manifest(root)
    window = _window(root, stale_manifest)
    refreshed = []
    window.show_project_state = lambda root, manifest: refreshed.append(manifest)

    def unexpected(*args):
        """@brief Detect any duplicate controller write from a stale snapshot."""
        pytest.fail("UI attempted to publish manifest")

    monkeypatch.setattr(workspace, "save_manifest", unexpected)
    monkeypatch.setattr(controller.misc_ui_controller, "show_message", lambda *a: None)
    controller.handle_chunking_success(window, {})
    assert refreshed == [expected]


@pytest.mark.parametrize(
    "field,value", [("reasoning_mode", "disabled"), ("reasoning_effort", "high"), ("supports_structured_output", True)]
)
@pytest.mark.parametrize("empty_prefix", [False, True])
def test_request_policy_warning_covers_reasoning_and_empty_prefix(tmp_path, monkeypatch, field, value, empty_prefix):
    """@brief Every request-affecting policy change is disclosed even before a first chunk committed."""
    root, manifest = _ready(tmp_path, monkeypatch)
    monkeypatch.setattr(
        ai, "_build_budget_metadata", lambda *a, **k: {"text_budget_tokens": 100, "strategy_paragraph_cap": 1}
    )
    calls = []

    def respond(*args, **kwargs):
        """@brief Resolve one synthetic window to control the saved prefix."""
        calls.append(True)
        return {"payload": {"chunks": []}}

    monkeypatch.setattr(ai.llm_provider_service, "chat_json", respond)
    profile = dict(_profile(), reasoning_mode="enabled", reasoning_effort="medium", supports_structured_output=False)
    with pytest.raises(runtime.OperationCancelledError):
        ai.chunk_text(root, manifest, profile, "paragraph", cancel_requested=lambda: empty_prefix or bool(calls))
    prefix = documents.load_checkpoint(root)["chunks"]
    messages = []
    profile[field] = value
    ai.chunk_text(root, manifest, profile, "paragraph", progress_callback=lambda *args: messages.append(args[3]))
    assert "policy changed" in messages[0]
    assert documents.load_chunks(root)[: len(prefix)] == prefix


@pytest.mark.parametrize("mode", ["deterministic", "ai_assisted"])
@pytest.mark.parametrize("replacement", [False, True])
def test_prepublication_cancellation_records_complete_terminal_prefix(tmp_path, monkeypatch, mode, replacement):
    """@brief Final cancellation checkpoints the complete processed prefix on the correct private path."""
    root, manifest = _ready(tmp_path, monkeypatch)
    published = None
    if replacement:
        deterministic.chunk_text(root, manifest)
        published = (root / config.CHUNK_ARTIFACT_FILE_NAME).read_bytes()
    monkeypatch.setattr(ai.llm_provider_service, "chat_json", lambda *a, **k: {"payload": {"chunks": []}})

    def cancel():
        """@brief Cancel only after preparation has reached the publication boundary."""
        return bool(list(root.glob(".chunking-stage-*")))

    with pytest.raises(runtime.OperationCancelledError):
        if mode == "deterministic":
            deterministic.chunk_text(root, manifest, cancel_requested=cancel)
        else:
            ai.chunk_text(root, manifest, _profile(), "paragraph", cancel_requested=cancel)
    checkpoint = documents.load_checkpoint(root)
    assert checkpoint["status"] == "cancelled"
    assert checkpoint["next_paragraph"] == 3
    assert checkpoint["chunks"][-1]["source_paragraph_end"] == 2
    if published is not None:
        assert (root / config.CHUNK_ARTIFACT_FILE_NAME).read_bytes() == published
    else:
        assert not (root / config.CHUNKING_PENDING_FILE_NAME).exists()


# END OF FILE
