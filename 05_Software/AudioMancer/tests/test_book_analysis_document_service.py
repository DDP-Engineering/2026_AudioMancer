#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_book_analysis_document_service.py
@brief Verify the strict atomic Book Analysis project document.
@details Covers completed/candidate separation, safe deterministic fingerprints,
         exact candidate resume matching, source/language freshness, schema
         rejection, and preservation of an existing document on write failure.
"""

# IMPORTS

from importlib import import_module
import json

import pytest

from audiomancer.services import token_usage_service

# LOCAL HELPERS


def _service():
    """Return the document service or fail as missing behavior."""
    try:
        return import_module("audiomancer.services.book_analysis_document_service")
    except ModuleNotFoundError:
        pytest.fail("Book Analysis document service is not implemented.")


def _source(fingerprint: str = "source-a", chunk_count: int = 2) -> dict[str, object]:
    """Build one source descriptor."""
    return {"fingerprint": fingerprint, "chunk_count": chunk_count}


def _summary() -> dict[str, object]:
    """Build one valid intermediate summary."""
    return {
        "summary": "Ana discovers the archive.",
        "characters": [{"name": "Ana", "role": "protagonist"}],
        "subjects": ["memory"],
        "themes": ["identity"],
        "settings": ["Bucharest"],
        "narrative_notes": ["third-person limited"],
        "audiobook_notes": ["restrained suspense"],
        "uncertainties": [],
    }


def _report_payload() -> dict[str, object]:
    """Build one valid layered report payload."""
    return {
        "concise": {
            "book_type": "novel",
            "genres": ["mystery"],
            "subjects": ["memory"],
            "setting_time": ["Bucharest, present day"],
            "summary": "Ana investigates a hidden archive.",
            "main_characters": [{"name": "Ana", "role": "protagonist"}],
            "themes": ["identity"],
        },
        "details": {
            "detailed_summary": "Ana uncovers the archive's history.",
            "supporting_characters": [
                {
                    "name": "Mihai",
                    "role": "archivist",
                    "relationships": ["Ana's guide"],
                }
            ],
            "narrative_perspective": "third-person limited",
            "narrative_structure": "linear",
            "tone": ["intimate", "suspenseful"],
            "pacing": "measured",
            "diction": "literary and direct",
            "emotional_range": ["curiosity", "grief", "resolve"],
            "audiobook_guidance": {
                "narration_style": "restrained suspense",
                "character_voice_notes": ["Keep Mihai reserved."],
            },
            "uncertainties": [],
            "source_evidence": [
                {"chunk_ids": ["chunk-0001"], "note": "Introduces Ana."}
            ],
        },
    }


def _completed_report(
    *,
    source_fingerprint: str = "source-a",
    target_language: str = "ro",
    profile_id: str = "profile-a",
) -> dict[str, object]:
    """Build one valid completed report slot."""
    return {
        "source": _source(source_fingerprint),
        "target_language": target_language,
        "profile_id": profile_id,
        "profile_fingerprint": "profile-fingerprint-a",
        "completed_at": "2026-08-29T12:00:00Z",
        "report": _report_payload(),
        "token_usage": token_usage_service.empty_token_usage(),
    }


def _candidate(*, status: str = "running") -> dict[str, object]:
    """Build one valid candidate slot."""
    return {
        "run_id": "run-0001",
        "status": status,
        "source": _source(),
        "target_language": "ro",
        "profile_id": "profile-a",
        "profile_fingerprint": "profile-fingerprint-a",
        "reasoning_mode": "provider_default",
        "budget": {
            "context_window": 16_384,
            "source_budget_tokens": 8_192,
            "output_reserve_tokens": 3_276,
            "reasoning_reserve_tokens": 1_638,
            "prompt_reserve_tokens": 100,
            "safety_reserve_tokens": 819,
            "reasoning_mode": "provider_default",
        },
        "phase": "leaf",
        "chunk_cursor": 1,
        "progress_current": 1,
        "progress_total": 3,
        "leaf_summaries": [
            {
                "index": 0,
                "chunk_ids": ["chunk-0001"],
                "first_sequence": 0,
                "last_sequence": 0,
                "summary": _summary(),
                "usage": token_usage_service.empty_token_usage(),
            }
        ],
        "consolidation_levels": [],
        "token_usage": token_usage_service.empty_token_usage(),
        "failure": None,
        "started_at": "2026-08-29T11:00:00Z",
        "updated_at": "2026-08-29T11:05:00Z",
    }


# TESTS


def test_write_document_preserves_completed_report_while_candidate_changes(tmp_path) -> None:
    """Candidate work and the last completed report occupy independent slots."""
    service = _service()
    completed = _completed_report()
    document = service.empty_document()
    document["completed_report"] = completed
    document["candidate_run"] = _candidate(status="running")

    service.write_document(tmp_path, document)
    loaded = service.load_document(tmp_path)

    assert loaded["completed_report"] == completed
    assert loaded["candidate_run"]["status"] == "running"


def test_candidate_resume_requires_source_language_profile_and_config_match() -> None:
    """Every semantic request input must match before a candidate is resumed."""
    service = _service()
    candidate = _candidate(status="cancelled")
    matching = {
        "source": _source(),
        "target_language": "ro",
        "profile_id": "profile-a",
        "profile_fingerprint": "profile-fingerprint-a",
    }

    assert service.candidate_resume_matches(candidate, **matching) is True
    for field_name, replacement in (
        ("source", _source("source-b")),
        ("target_language", "de"),
        ("profile_id", "profile-b"),
        ("profile_fingerprint", "profile-fingerprint-b"),
    ):
        changed = dict(matching)
        changed[field_name] = replacement
        assert service.candidate_resume_matches(candidate, **changed) is False


def test_completed_report_staleness_ignores_profile_selection() -> None:
    """Freshness depends on canonical source and project target language only."""
    service = _service()
    report = _completed_report(profile_id="profile-a")

    assert service.completed_report_is_stale(report, _source(), "ro") is False
    assert service.completed_report_is_stale(report, _source("source-b"), "ro") is True
    assert service.completed_report_is_stale(report, _source(), "de") is True


def test_canonical_source_descriptor_changes_with_chunk_content_or_order() -> None:
    """The source fingerprint covers ordered canonical chunk identity and text."""
    service = _service()
    chunks = [
        {"chunk_id": "chunk-0001", "sequence_index": 0, "text": "One"},
        {"chunk_id": "chunk-0002", "sequence_index": 1, "text": "Two"},
    ]

    original = service.canonical_source_descriptor(chunks)
    changed_text = service.canonical_source_descriptor([chunks[0], {**chunks[1], "text": "Changed"}])
    changed_order = service.canonical_source_descriptor([chunks[1], chunks[0]])

    assert original["chunk_count"] == 2
    assert original["fingerprint"] != changed_text["fingerprint"]
    assert original["fingerprint"] != changed_order["fingerprint"]


def test_profile_fingerprint_excludes_api_key_but_tracks_request_configuration() -> None:
    """Resume fingerprints contain no secret-derived value but track request semantics."""
    service = _service()
    profile = {
        "backend_kind": "lmstudio",
        "base_url": "http://127.0.0.1:1234/v1",
        "api_key": "secret-a",
        "model_name": "vendor/new-model",
        "context_window": 16_384,
        "output_reserve_tokens": 4_096,
        "request_timeout_seconds": 300,
        "temperature": 0.1,
        "supports_structured_output": True,
        "reasoning_mode": "enabled",
    }

    original = service.safe_profile_fingerprint(profile)
    assert original == service.safe_profile_fingerprint({**profile, "api_key": "secret-b"})
    assert original != service.safe_profile_fingerprint({**profile, "reasoning_mode": "disabled"})


def test_invalid_document_is_rejected(tmp_path) -> None:
    """Unknown root fields make the sole authoritative document incompatible."""
    path = tmp_path / "book_analysis.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "completed_report": None,
                "candidate_run": None,
                "unexpected": True,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="incompatible"):
        _service().load_document(tmp_path)


def test_atomic_write_preserves_previous_document_on_replace_failure(
    monkeypatch,
    tmp_path,
) -> None:
    """An atomic writer failure leaves the prior complete document untouched."""
    service = _service()
    original = service.empty_document()
    original["completed_report"] = _completed_report()
    service.write_document(tmp_path, original)
    original_bytes = service.document_path(tmp_path).read_bytes()

    def fail_write(*_args, **_kwargs) -> None:
        raise OSError("simulated replacement failure")

    monkeypatch.setattr(service, "write_json_atomic", fail_write)
    replacement = service.empty_document()
    replacement["candidate_run"] = _candidate()

    with pytest.raises(OSError, match="simulated replacement failure"):
        service.write_document(tmp_path, replacement)

    assert service.document_path(tmp_path).read_bytes() == original_bytes


# END OF FILE
