<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->


# Environment guide

## Toolchain

Python 3.12 or 3.13 with uv; PySide6 desktop runtime and pytest/pytest-qt for
verification. Runtime/development dependencies are declared by the application
pyproject.toml and resolved in uv.lock.

## Setup

From `05_Software/AudioMancer`, use `uv sync --extra dev` as documented in
README.MD. Use an OS-native environment for platform tests and freezing; a
Windows virtual environment is not shared with WSL Python.

## Configuration and services

Legacy endpoints use profile settings. ChatGPT uses fixed HTTPS authorization,
model-metadata and inference endpoints and a loopback callback on 127.0.0.1:1455. Browser/device
verification requires user sign-in; synthetic tests inject transports and stores.

## Readiness checks

Confirm pytest, PySide6 and httpx imports before tests. Linux QtMultimedia requires
the host multimedia libraries, including libpulse. Account persistence uses DPAPI
on Windows or an available native Secret Service/KWallet on Linux; explicit
session-only mode works without a keyring.

## Build and run

Run `uv run audiomancer`. Packaging entry points are the Windows spec/script
and the Linux packaging script under `02_Tools`; generated artifacts belong to
their staging/output folders.

## Verification

The commands in `.agentic/aegis.toml` own final verification. Focused provider and
account checks use `uv run pytest -q tests/test_chatgpt_*.py`; the autouse test fixture isolates the subscription manager in memory and requires
an injected HTTP transport, preventing automatic settings discovery from using
the operator's credentials or network. Offscreen Qt is available with QT_QPA_PLATFORM=offscreen. On Windows,
QT_QPA_FONTDIR can point to the installed system font directory for readable
offscreen captures. HowToTest.md keeps UI tests serial; service-tier parallelism
is an opt-in route.

Focused Chunking regressions use `tests/test_chunking_refinement.py`, the
deterministic/AI Chunking service tests, descriptor/document contracts and
text-chunking state/controller tests. These use synthetic provider responses;
recovery tests inject filesystem failures without live model access.

Focused AI Translation checks use the translation service/state/page/controller
modules and selected Chunking, Character Discovery, Speech Blocks, narrator and
project tests. AI replies and publication failures use controlled test doubles.

Focused Character Discovery checks use the discovery service/state and Characters
page/controller tests with simulated provider responses and offscreen Qt.

Focused Character Voices checks use the character voice service, state, page
and controller tests, with simulated generation and injected file replacement
failures. Audio Blocks, export and project reset tests cover consumers.

Focused Speech Blocks checks use the service, normalization, text split,
document contract and offscreen Qt tests. Resume and ambience tests use
controlled provider responses.

Focused Audio Blocks checks use the service, WAV artifact, document, state,
page and selected offscreen controller tests. They simulate VoiceWeaver and
inject file replacement errors. Listening uses an installed local runtime.

Focused Audio Assembly checks use synthetic PCM WAVs in the assembly service,
state, UI, sample-width and codec tests, plus affected Audio Blocks and Speech
Blocks selectors. Replacement faults are injected without touching user projects.

## Platform details

Protected account state lives outside portable data. Windows uses
`%LOCALAPPDATA%/AudioMancer/Auth`; Linux locks live beneath the per-user XDG data
root, while secrets live in the native keyring. Package dependency analysis
includes httpx/CA data and native keyring backends.

## Authoritative references

- `05_Software/AudioMancer/README.MD`
- `05_Software/AudioMancer/pyproject.toml` and `uv.lock`
- `.agentic/aegis.toml`
- `02_Tools/audiomancer_windows.spec` and platform packaging scripts
- `.agentic/knowledge/AI_Runtime.md` and `Release_Packaging.md`

Focused Export checks use the export and snapshot service suites with synthetic PCM WAVs,
plus the export/snapshot selectors in the Home controller and main-window tests with Qt offscreen.

Focused AI context/limit checks use the backend, shared budget, provider wire and
AI Settings tests plus Book Analysis, Cleanup and budget-specific consumer tests.
A live local smoke check uses synthetic prompts with the operator's LM Studio
endpoint, loading and unloading only its own model instances.
