#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file chatgpt_catalog_service.py
@brief Discover primary subscription models and supported reasoning efforts.
@details Uses only AudioMancer's connection and fixed native endpoint. Normalized
         metadata is cached with the account generation; discovery grants no inference capability.
"""

# IMPORTS

import copy
import json
import re
import time

import httpx

from audiomancer.services import chatgpt_http_service as http
from audiomancer.services.chatgpt_credential_service import get_manager
from audiomancer.services.chatgpt_storage_service import check_cancel
from audiomancer.services.logging_service import get_component_logger
from audiomancer.services.operation_runtime_service import OperationCancelledError

# CONSTANTS

CATALOG_TTL_SECONDS = 3600
MAX_CATALOG_BYTES = 4 * 1024 * 1024
MODEL_CANDIDATES = ("gpt-5.5", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-6-astra")
_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}\Z")
_EFFORT_ID = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")
_LOGGER = get_component_logger("chatgpt_catalog")


# PUBLIC API


def builtin_models():
    """@brief Return independent candidate metadata from the observed subscription catalog."""
    models = []
    for model in MODEL_CANDIDATES:
        efforts = ["low", "medium", "high", "xhigh"]
        if model != "gpt-5.5":
            efforts.append("max")
        if model in {"gpt-5.6-sol", "gpt-5.6-terra", "gpt-6-astra"}:
            efforts.append("ultra")
        models.append(
            {"id": model, "efforts": efforts, "default_effort": "low" if model == "gpt-5.6-sol" else "medium",
             "context_window": 272000}
        )
    return models


def list_models(*, manager=None, cancel=None, force=False, now=None):
    """@brief Refresh visible text models or return labelled account-cache/built-in fallback.
    @param[in] force Bypass the one-hour freshness cache for an explicit user refresh.
    @param[in] now Optional timestamp seam; production uses wall-clock UTC seconds.
    @return Safe models, source and fetched_at fields, without provider instructions or tokens.
    """
    check_cancel(cancel)
    manager = manager if manager is not None else get_manager()
    timestamp = time.time() if now is None else now
    try:
        generation = manager.begin_login(cancel)
        connected = manager.status(cancel)["connected"]
    except OperationCancelledError:
        raise
    except RuntimeError:
        return _result(None, "builtin")
    cached = _read_cached(manager, generation, cancel) if connected else None
    if not connected:
        return _result(None, "builtin")
    if (cached and cached["has_context_metadata"] and not force
            and 0 <= timestamp - cached["fetched_at"] < CATALOG_TTL_SECONDS):
        return _result(cached, "cache")
    _LOGGER.debug("Refreshing ChatGPT subscription model metadata")
    try:
        generation, credential = manager.acquire(cancel, expected=generation)
        for attempt in range(2):
            try:
                payload = http.run_cancellable(_fetch(credential), cancel, 15)
                break
            except http.ProviderError as error:
                if error.status != 401 or attempt:
                    raise
                generation, credential = manager.acquire(
                    cancel, expected=generation, rejected_token=credential.access_token
                )
        models = _parse_models(payload)
    except OperationCancelledError:
        raise
    except (RuntimeError, ValueError):
        manager.assert_current(generation, cancel)
        return _result(cached, "stale_cache" if cached else "builtin")
    manager.assert_current(generation, cancel)
    updated = {"models": models, "fetched_at": timestamp}
    manager.write_catalog(generation, updated, cancel)
    return _result(updated, "live")


def cached_models(manager, generation, cancel=None):
    """@brief Read current-account options without fetching during an inference request."""
    cached = _read_cached(manager, generation, cancel)
    return cached["models"] if cached else builtin_models()


def requested_effort(profile):
    """@brief Preserve explicit choices and map legacy subscription enabled/disabled preferences."""
    value = profile.get("reasoning_effort")
    if value is None:
        value = {"enabled": "medium", "disabled": "none"}.get(profile.get("reasoning_mode"), "provider_default")
    if not isinstance(value, str) or not _EFFORT_ID.fullmatch(value):
        raise ValueError("Invalid ChatGPT reasoning effort. Choose an effort in AI Settings.")
    return value


def reasoning_mode(effort):
    """@brief Summarize explicit effort for existing workflow budget and metadata contracts."""
    return "provider_default" if effort == "provider_default" else "disabled" if effort == "none" else "enabled"


def validate_effort(profile, models):
    """@brief Reject an unsupported explicit choice instead of silently changing request cost."""
    effort = requested_effort(profile)
    if effort == "provider_default":
        return effort
    model = next((item for item in models if item["id"] == profile.get("model_name")), None)
    if model is None or effort not in model["efforts"]:
        raise ValueError(
            "This reasoning effort is unavailable for the selected ChatGPT model. "
            "Refresh models and choose a supported effort in AI Settings."
        )
    return effort


# LOCAL HELPERS


def _result(catalog, source):
    """@brief Keep all results detached from protected mutable state."""
    return {
        "models": copy.deepcopy(catalog["models"]) if catalog else builtin_models(),
        "source": source,
        "fetched_at": catalog["fetched_at"] if catalog else None,
    }


def _read_cached(manager, generation, cancel):
    """@brief Discard malformed optional cache data while retaining the protected account."""
    cached = manager.read_catalog(generation, cancel)
    if not isinstance(cached, dict):
        return None
    timestamp = cached.get("fetched_at")
    entries = cached.get("models")
    if type(timestamp) not in (int, float) or not 0 < timestamp < 1e12 or not isinstance(entries, list):
        return None
    try:
        models = _parse_models({"models": [
            {"slug": item["id"], "visibility": "list", "input_modalities": ["text"],
             "supported_reasoning_levels": [{"effort": effort} for effort in item["efforts"]],
             "default_reasoning_level": item.get("default_effort"), "context_window": item.get("context_window")}
            for item in entries
        ]})
    except (KeyError, TypeError, AttributeError, ValueError):
        return None
    return {"models": models, "fetched_at": timestamp,
            "has_context_metadata": all("context_window" in item for item in entries)}


def _parse_models(payload):
    """@brief Whitelist bounded picker metadata; ignore instructions, tools and hidden entries."""
    entries = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(entries, list) or len(entries) > 200:
        raise ValueError("Invalid model catalog.")
    models, seen = [], set()
    for item in entries:
        if not isinstance(item, dict) or item.get("visibility") != "list":
            continue
        modalities = item.get("input_modalities")
        if not isinstance(modalities, list) or "text" not in modalities:
            continue
        model = item.get("slug")
        if not isinstance(model, str) or not _MODEL_ID.fullmatch(model) or model in seen:
            continue
        raw_efforts = item.get("supported_reasoning_levels", [])
        if not isinstance(raw_efforts, list) or len(raw_efforts) > 16:
            continue
        efforts = []
        for option in raw_efforts:
            effort = option.get("effort") if isinstance(option, dict) else None
            if (
                isinstance(effort, str)
                and _EFFORT_ID.fullmatch(effort)
                and effort != "provider_default"
                and effort not in efforts
            ):
                efforts.append(effort)
        default = item.get("default_reasoning_level")
        context = item.get("context_window")
        if type(context) is not int or not 0 < context <= 2_147_483_647:
            context = None
        priority = item.get("priority", 1000)
        if not isinstance(priority, (int, float)) or not -1e6 <= priority <= 1e6:
            priority = 1000
        models.append(
            (priority, {"id": model, "efforts": efforts, "default_effort": default if default in efforts else None,
                        "context_window": context})
        )
        seen.add(model)
    if not models:
        raise ValueError("No primary text models in catalog.")
    return [model for _, model in sorted(models, key=lambda pair: pair[0])]


async def _fetch(credential):
    """@brief Read bounded JSON from the single fixed catalog URL, never following redirects."""
    from audiomancer import __version__

    headers = {
        "Authorization": "Bearer " + credential.access_token,
        "ChatGPT-Account-Id": credential.account_id,
        "originator": "audiomancer",
        "User-Agent": "AudioMancer",
        "Accept": "application/json",
    }
    if credential.residency:
        headers["x-openai-internal-codex-residency"] = credential.residency
    try:
        async with (
            http.new_client() as client,
            client.stream("GET", http.MODELS_URL, params={"client_version": __version__}, headers=headers) as response,
        ):
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > MAX_CATALOG_BYTES:
                    raise http.ProviderError()
            http.check_status(response, bytes(raw))
            try:
                return json.loads(raw)
            except (ValueError, UnicodeError):
                raise http.ProviderError() from None
    except httpx.TimeoutException:
        raise http.ProviderError("timeout") from None
    except httpx.HTTPError:
        raise http.ProviderError("network") from None


# END OF FILE
