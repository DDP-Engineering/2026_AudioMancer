#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file chatgpt_auth_service.py
@brief Browser PKCE and device-code sign-in for the experimental subscription adapter.
@details Uses AudioMancer-owned credentials only. Loopback listeners, polling and
         HTTP connections are bounded and closed before cancellation returns.
"""

# IMPORTS

import asyncio
import base64
from contextlib import suppress
import hashlib
import json
import math
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from audiomancer.services import chatgpt_http_service as http
from audiomancer.services.chatgpt_credential_service import Credential, get_manager

# CONSTANTS

REDIRECT_URI = "http://localhost:1455/auth/callback"
_CLAIM_NAMESPACE = "https://api.openai.com/auth"


# PUBLIC API


def authorization_request():
    """@brief Generate independent PKCE verifier and state for one browser attempt."""
    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode().rstrip("=")
    query = {
        "client_id": http.CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": "openid profile email offline_access",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "originator": "audiomancer",
    }
    return "https://auth.openai.com/oauth/authorize?" + urlencode(query), verifier, state


def credential_from_tokens(payload, *, previous=None, clock=time.time):
    """@brief Validate OAuth fields and decode JWT metadata without treating it as local authorization proof."""
    try:
        access = payload["access_token"]
        refresh = payload.get("refresh_token") or (previous.refresh_token if previous else "")
        expiry = float(payload["expires_in"])
        if not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh:
            raise ValueError
        if not math.isfinite(expiry) or not 0 < expiry <= 365 * 86400:
            raise ValueError
        claims = _claims(access)
        identity = _claims(payload.get("id_token", ""))
        auth = claims.get(_CLAIM_NAMESPACE, {})
        account = auth.get("chatgpt_account_id") or identity.get(_CLAIM_NAMESPACE, {}).get("chatgpt_account_id")
        if not isinstance(account, str) or not account or any(c in account for c in "\r\n\0"):
            raise ValueError
        label = identity.get("email", claims.get("email", "ChatGPT account"))
        if not isinstance(label, str) or len(label) > 200 or any(ord(c) < 32 for c in label):
            label = "ChatGPT account"
        residency = auth.get("chatgpt_compute_residency", "")
        if not isinstance(residency, str) or len(residency) > 64 or not residency.replace("-", "").isalnum():
            residency = ""
        if residency == "no_constraint":
            residency = ""
        return Credential(access, refresh, clock() + expiry, account, label, residency)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise RuntimeError("ChatGPT returned invalid credentials or no account identity. Sign in again.") from None


def sign_in(method="browser", *, progress=None, cancel=None, manager=None):
    """@brief Run one login and publish credentials only if its account generation is still current."""
    manager = manager if manager is not None else get_manager()
    generation = manager.begin_login(cancel)
    callback = progress if progress is not None else lambda _: None
    if method == "browser":
        operation, timeout = _browser_flow(callback), 300
    elif method == "device":
        operation, timeout = _device_flow(callback), 900
    else:
        raise ValueError("Unknown ChatGPT sign-in method.")
    credential = http.run_cancellable(operation, cancel, timeout)
    manager.finish_login(generation, credential, cancel)
    return manager.status(cancel)


def refresh_credential(previous, cancel=None):
    """@brief Rotate the refresh token at the fixed OAuth endpoint within a bounded request."""
    result = http.run_cancellable(
        http.request_json(
            http.TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": previous.refresh_token,
                "client_id": http.CLIENT_ID,
            },
        ),
        cancel,
        15,
    )
    return credential_from_tokens(result, previous=previous)


# LOCAL HELPERS


def _claims(token):
    """@brief Decode bounded JWT payload metadata; token validation belongs to the upstream service."""
    try:
        if not isinstance(token, str) or len(token) > 64000:
            return {}
        part = token.split(".")[1]
        result = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        return result if isinstance(result, dict) else {}
    except (ValueError, IndexError, UnicodeError):
        return {}


async def _exchange(code, verifier, redirect):
    """@brief Exchange a short-lived authorization code without writing it to logs or settings."""
    payload = await http.request_json(
        http.TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": http.CLIENT_ID,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect,
        },
    )
    return credential_from_tokens(payload)


async def _browser_flow(progress):
    """@brief Own the loopback listener and all connection tasks for a single PKCE attempt."""
    url, verifier, state = authorization_request()
    result = asyncio.get_running_loop().create_future()
    connections = set()

    async def receive(reader, writer):
        """@brief Validate callback path and state before accepting a code or authorization denial."""
        current = asyncio.current_task()
        connections.add(current)
        valid = False
        try:
            line = await asyncio.wait_for(reader.readline(), 5)
            if len(line) > 8192:
                raise ValueError
            method, target, _ = line.decode("ascii").split(" ", 2)
            parsed = urlsplit(target)
            query = parse_qs(parsed.query)
            supplied = query.get("state", [])
            valid = (
                method == "GET"
                and parsed.path == "/auth/callback"
                and len(supplied) == 1
                and secrets.compare_digest(supplied[0], state)
                and not result.done()
            )
            codes = query.get("code", [])
            if valid and "error" in query:
                result.set_exception(RuntimeError("ChatGPT sign-in was denied. Try signing in again."))
            elif valid and len(codes) == 1 and 0 < len(codes[0]) <= 4096:
                result.set_result(codes[0])
            else:
                valid = False
            message = b"Sign-in received. Return to AudioMancer." if valid else b"Invalid authorization callback."
            status = b"200 OK" if valid else b"400 Bad Request"
            writer.write(
                b"HTTP/1.1 " + status + b"\r\nContent-Type: text/plain\r\nConnection: close\r\n"
                b"Cache-Control: no-store\r\nContent-Length: " + str(len(message)).encode() + b"\r\n\r\n" + message
            )
            await writer.drain()
        except (ValueError, UnicodeError, OSError, TimeoutError):
            pass
        finally:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()
            connections.discard(current)

    try:
        server = await asyncio.start_server(receive, "127.0.0.1", 1455, limit=8192)
    except OSError:
        raise RuntimeError(
            "Port 1455 is unavailable. Close the other sign-in attempt or use device-code sign-in."
        ) from None
    try:
        progress({"kind": "browser", "url": url})
        code = await asyncio.wait_for(result, 300)
        return await _exchange(code, verifier, REDIRECT_URI)
    finally:
        server.close()
        await server.wait_closed()
        for connection in tuple(connections):
            connection.cancel()
        await asyncio.gather(*tuple(connections), return_exceptions=True)


async def _device_flow(progress):
    """@brief Poll the official device flow with bounded expiry and server-requested slowdown."""
    result = await http.request_json(http.DEVICE_CODE_URL, payload={"client_id": http.CLIENT_ID})
    device_id, code = result.get("device_auth_id"), result.get("user_code")
    try:
        interval = min(30.0, max(1.0, float(result.get("interval", 5))))
        if (
            not isinstance(device_id, str)
            or not device_id
            or not isinstance(code, str)
            or not 1 <= len(code) <= 32
            or not math.isfinite(interval)
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise http.ProviderError() from None
    progress({"kind": "device", "url": "https://auth.openai.com/codex/device", "code": code})
    deadline = asyncio.get_running_loop().time() + 900
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(interval)
        try:
            result = await http.request_json(
                http.DEVICE_TOKEN_URL, payload={"device_auth_id": device_id, "user_code": code}
            )
        except http.ProviderError as error:
            if error.code == "slow_down":
                interval = min(30.0, interval + 5)
                continue
            if error.code == "pending" or (error.code == "rejected" and error.status in {403, 404}):
                continue
            raise
        authorization, verifier = result.get("authorization_code"), result.get("code_verifier")
        if not isinstance(authorization, str) or not authorization or not isinstance(verifier, str) or not verifier:
            raise http.ProviderError()
        return await _exchange(authorization, verifier, "https://auth.openai.com/deviceauth/callback")
    raise http.ProviderError("timeout")


# END OF FILE
