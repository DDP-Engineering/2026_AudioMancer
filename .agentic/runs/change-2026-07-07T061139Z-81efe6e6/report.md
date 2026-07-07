# Agentic Workflow Report: change-2026-07-07T061139Z-81efe6e6

- Stage: `delivery`
- Access mode: `standard`
- Intent: `I-0001` change - Replace Speech Blocks narrator-and-character generation with an operator-review direct LLM block-splitting contract that preserves source text where aligned, flags uncertain output for review, uses segment-level fallback instead of whole-chunk atomic fallback, and remains interruptible and resumable.

## Intent Alignment
- Source: user-approved implementation plan
- Understanding: Replace narrator-and-character Speech Blocks generation with an operator-review direct LLM block-splitting contract. The LLM will return ordered blocks containing text, speaker_id, content_kind, confidence, and warning_flags. AudioMancer will preserve source text where returned text can be aligned, mark uncertainty for review, fall back only the failed segment, split large chunks by output-safety limits, and keep generation interruptible/resumable at segment granularity. This is a breaking replacement for the atomic/source-span selection and repair contract; old operation checkpoints do not need migration.
- Risk: `medium`
- Decision: `pause` - Workflow policy requires a human approval pause when risk is medium; this is a breaking replacement of a core generation contract.
- Scope: In scope: prompt/schema replacement, direct block normalization, source-text alignment and review flags, segment-level fallback, output-aware segmentation, segment-level resume/cancel state, relevant tests, requirements, and component documentation. Out of scope: backward compatibility with old atomic/source-span responses or checkpoints, UI redesign beyond existing edit/review surfaces, changing Audio Blocks or Audio Assembly contracts except through existing Speech Blocks outputs, and packaging/release work.
- Acceptance: Speech Blocks can generate reviewable narrator-and-character blocks from direct LLM text responses, preserves aligned source slices, flags gaps/unmatched/unknown output for operator review, falls back only failed segments, splits large dialogue-heavy chunks before model output becomes too large, resumes after completed segments, and no longer emits a whole-chunk narrator fallback for chunk-0033-style failures.
- Assumptions: Use the recommended source policy: preserve original source text where aligned and mark uncertainty for review rather than trusting unmatched LLM text.; Use the recommended failure policy: save deterministic narrator review fallback for only the failed segment and continue.; No compatibility migration is required for old atomic/source-span operation state or old repair responses.
- Open questions: Approve medium-risk breaking replacement of the Speech Blocks narrator-and-character generation contract?
- Recommended responses: Approve and continue to requirements/checks/implementation using the provided plan.
- Planned paths: 04_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py, 04_Software/AudioMancer/src/audiomancer/services/speech_blocks_normalization_service.py, 04_Software/AudioMancer/src/audiomancer/services/speech_blocks_text_split_service.py, 04_Software/AudioMancer/prompts/speech_blocks_system.txt, 04_Software/AudioMancer/prompts/speech_blocks_user.txt, 04_Software/AudioMancer/tests/test_speech_blocks_service.py, 04_Software/AudioMancer/tests/test_speech_blocks_text_split_service.py, .agentic/requirements/functional.md, .agentic/requirements/data_privacy.md, 05_SoftwareDocu/AudioMancer_Speech_Blocks_Service.md, 05_SoftwareDocu/AudioMancer_Text_Pipeline_Support_Services.md

## Spec Items
- `SB-DIRECT-001` [behavior] accepted: Narrator-and-character Speech Blocks generation accepts direct LLM blocks with text, speaker_id, content_kind, confidence, and warning_flags, aligns returned text to the source segment, persists aligned source slices, marks uncertainty for review, and never persists unmatched invented model text as trusted audiobook text.
- `SB-DIRECT-003` [behavior] accepted: If a direct Speech Blocks LLM response is malformed or unusable, generation persists deterministic narrator needs_review fallback blocks only for that failed segment and continues with later segments instead of falling back the whole chunk.
- `SB-DIRECT-004` [behavior] accepted: Direct Speech Blocks generation persists segment-level progress, honors cooperative cancellation between provider calls and segment persistence, resumes from the next unfinished segment, and restarts incompatible old atomic/source-span checkpoints rather than migrating them.
- `SB-DIRECT-002` [behavior] accepted: Narrator-and-character Speech Blocks generation splits source chunks into contiguous LLM request segments using an output-safety source budget capped around 2000 estimated source tokens, even when the selected profile permits larger input.

## Checks
- `CHK-SB-DIRECT-001` green; cites SB-DIRECT-001
- `CHK-SB-DIRECT-002` red; cites SB-DIRECT-002
- `CHK-SB-DIRECT-003` red; cites SB-DIRECT-003
- `CHK-SB-DIRECT-004` red; cites SB-DIRECT-004

## Evidence
- `E-0001` test-run/fail: Focused direct Speech Blocks tests fail against the old atomic/source-span implementation: unknown speakers lack review flags, source gaps are not inserted, unmatched model text is persisted, direct generation still repairs source-span responses, output-safety segmentation is absent, and segment resume restarts the active chunk.
- `E-0002` test-run/pass: Focused Speech Blocks direct-block, segmentation, provider schema, and traceability tests passed: 83 passed, 1 warning.
- `E-0003` scan/pass: Changed-only Python codestyle audit passed.
- `E-0004` scan/pass: Scoped Ruff passed for changed Speech Blocks Python files.
- `E-0005` scan/pass: Changed-only documentation audit passed after refreshing Speech Blocks component docs.
- `E-0006` scan/pass: Workflow traceability audit passed with no issues.
- `E-0007` test-run/fail: Config hygiene check fails because ignored local runtime settings.json contains tts_runtime_api_key=voiceweaver-dev-key; file is not tracked in HEAD and was left unchanged for manual runtime testing.
- `E-0008` scan/pass: Workflow requirement coverage audit passed with no issues.
- `E-0009` scan/fail: Full Ruff currently fails on untouched src/audiomancer/services/character_voices_state_service.py import ordering; scoped Ruff for changed Speech Blocks files passed.
- `E-0010` note/info: Ignored local 04_Software/AudioMancer/settings.json contains tts_runtime_api_key for manual runtime testing; this file is not tracked in HEAD and was intentionally left unchanged.
- `E-0011` note/info: Full Ruff has one unrelated import-order issue in untouched character_voices_state_service.py; scoped Ruff for changed Speech Blocks files passed.
- `E-0012` test-run/pass: Delivery refresh focused Speech Blocks direct-block validation passed with workspace TEMP/TMP: 83 passed, 1 warning.
- `E-0013` test-run/pass: Release metadata smoke test passed for AudioMancer 1.6.3: pyproject, uv.lock, and audiomancer.__version__ align.
- `E-0014` gate/pass: Windows delivery package created through 02_Tools/package_windows_release.ps1 at 07_Delivery/AudioMancer_Windows_x64.zip with SHA256 191aa253c291d3e5c1e0f738b8351d81649983eafae44284ac54f4d8edce93da.
- `E-0015` scan/pass: Packaged archive contains AudioMancer.exe, release notes, changelog, pyproject version 1.6.3, English and Romanian help version 1.6.3, and Speech Blocks prompt templates.

## Invariants
- `INV-1` PASS (blocking): All accepted/realized spec items have checks.
- `INV-2` PASS (blocking): All checks cite existing spec items.
- `INV-3` PASS (blocking): Green checks have prior red evidence.
- `INV-4` PASS (blocking): No failing implementation/validation/delivery gate evidence.
- `INV-5` PASS (advisory): No change units recorded yet.
- `INV-6` PASS (blocking): Run has recorded evidence.
- `INV-7` PASS (non-waivable): No configured secret pattern found in diff.
- `INV-8` PASS (blocking): Green requirement-linked checks cite Active requirements.
- `INV-9` PASS (blocking): No change units recorded yet.

## Traceability Audits
- PASS: traceability, coverage, and registry audits have no findings.

## Next Prompts
- Continue the next manual gate after reviewing the report.
- Ask the agent to create or update missing artifacts named above.
- When ready for delivery, prompt: `Create PR for this agentic workflow run`.
