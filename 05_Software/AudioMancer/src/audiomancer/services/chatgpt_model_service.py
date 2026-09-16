#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file chatgpt_model_service.py
@brief Verify subscription model access and the strict Cleanup schema dialect.
@details Candidates are hints, not account model discovery. Only successful live
         requests grant capabilities in the protected account generation.
"""

# IMPORTS

import json

from audiomancer.services import chatgpt_provider_service as provider
from audiomancer.services.chatgpt_catalog_service import MODEL_CANDIDATES, cached_models
from audiomancer.services.chatgpt_credential_service import get_manager
from audiomancer.services.chatgpt_http_service import ProviderError
from audiomancer.services.cleanup_ai_adjudication_service import _answer_schema
from audiomancer.services.operation_runtime_service import OperationCancelledError

# CONSTANTS

# @brief Candidate identifiers observed in current clients; entitlement is verified explicitly.


# PUBLIC API


def verify_profile(profile, *, cancel=None, manager=None):
    """@brief Test tiny synthetic text/schema requests and return existing probe metadata.
    @param[in] profile Selected profile, including manual model identifier.
    @param[in] cancel Optional cooperative cancellation callback.
    @param[in] manager Optional injected account manager.
    @return Probe result; candidate list and verified capabilities are distinguished.
    """
    manager = manager if manager is not None else get_manager()
    model = str(profile.get("model_name", "")).strip()
    result = {
        "success": False,
        "message": "Sign in to ChatGPT and test a model.",
        "discovered_models": [{"id": item, "label": item + " (candidate)"} for item in MODEL_CANDIDATES],
        "discovered_model_count": len(MODEL_CANDIDATES),
        "selected_model_valid": False,
        "discovered_context_window": None,
        "discovered_context_model_name": None,
        "supports_structured_output": False,
        "capability_verified": False,
        "candidate_catalog": True,
    }
    try:
        generation, _ = manager.acquire(cancel)
        result["discovered_models"] = [
            {"id": item["id"], "label": item["id"] + " (candidate)"}
            for item in cached_models(manager, generation, cancel)
        ]
        result["discovered_model_count"] = len(result["discovered_models"])
        if not model:
            result["message"] = (
                "Select or enter a model, then test it. Candidates are not verified account entitlements."
            )
            return result
        test_profile = {**profile, "request_timeout_seconds": min(60, int(profile.get("request_timeout_seconds", 60)))}
        completion = provider.complete(
            test_profile,
            'Return exactly {"ok":true}.',
            "Connectivity check.",
            cancel=cancel,
            manager=manager,
            generation=generation,
            retry_count=0,
        )
        if json.loads(completion.text) != {"ok": True}:
            raise ValueError("Unexpected connectivity response.")
        schema = _answer_schema("audiomancer-probe", [{"question_id": "q1", "choices": ["keep", "remove"]}])
        schema_verified = False
        try:
            constrained = provider.complete(
                test_profile,
                "Follow the response schema.",
                "Return only the word HELLO instead of JSON.",
                cancel=cancel,
                manager=manager,
                generation=generation,
                schema=schema,
                schema_name="audiomancer_cleanup_probe",
                verify_schema=True,
                retry_count=0,
            )
            payload = json.loads(constrained.text)
            schema_verified = payload in [
                {"batch_id": "audiomancer-probe", "answers": [{"question_id": "q1", "choice": choice}]}
                for choice in ("keep", "remove")
            ]
        except (ProviderError, ValueError):
            # Text access remains useful, but Cleanup never receives an optimistic capability flag.
            schema_verified = False
        manager.mark_verified(generation, model, schema_verified, cancel)
        result.update(
            success=True,
            selected_model_valid=True,
            supports_structured_output=schema_verified,
            capability_verified=True,
            message=(
                "ChatGPT model verified: text and strict Cleanup schema."
                if schema_verified
                else "ChatGPT text verified. Strict schema is unverified; Cleanup AI requires it."
            ),
        )
        result["discovered_models"] = [{"id": model, "label": model + " (verified)"}] + [
            entry for entry in result["discovered_models"] if entry["id"] != model
        ]
        result["discovered_model_count"] = len(result["discovered_models"])
    except OperationCancelledError:
        raise
    except RuntimeError as error:
        result["message"] = str(error)
    except (ValueError, TypeError):
        result["message"] = "ChatGPT model verification did not return the expected JSON. Try another model."
    return result


# END OF FILE
