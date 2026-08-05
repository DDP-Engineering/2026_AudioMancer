# Component Review — TTS Runtime + Audio Assembly + PCM Codec
_Reviewed 2026-08-02. Files: `services/voiceweaver_runtime_service.py` (1308), `services/tts_budget_service.py` (231), `services/pcm_codec.py` (301), `services/audio_assembly_service.py` (1765), `services/audio_assembly_state_service.py` (208), `ui/pages/audio_assembly_page.py` (730), `ui/controllers/audio_assembly_ui_controller.py` (802), `ui/pages/tts_settings_page.py` (646), `ui/controllers/tts_settings_ui_controller.py` (159), `ui/controllers/tts_runtime_ui_support.py` (130). Total ~6280 lines._

## Summary

The PCM/WAV core is in good shape: `pcm_codec` is bit-exact against `audioop` (verified with a differential run across all four sample widths, mono/stereo and five rate pairs including chunked streaming), format mismatches between blocks are converted rather than silently concatenated, and there are no file-handle leaks or subprocess/shell hazards (the runtime is plain HTTP with timeouts everywhere). Two real defects can stop a run: an approved Scene Ambience block that owns no WAV slips past Audio Assembly's pre-flight validation and then crashes composition with a raw `FileNotFoundError`, and a whole-book WAV larger than 4 GiB aborts with an opaque `struct.error` from the stdlib `wave` header patcher. Findings: 2 Major, 4 Minor, 1 Uncertain.

## Findings

### [AS-1] Scene Ambience blocks bypass WAV-existence validation, then crash composition — **Major**

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\audio_assembly_service.py:457` (validation) and `:1540` / `:1607` (inclusion + open)
- **What:** the pre-flight validation only checks blocks that are **not** metadata-only, but the composition-block filter admits **any** block carrying an `audio_relative_path` — and Scene Ambience blocks are always metadata-only after loading.

```python
    playable_blocks = [
        block
        for block in candidate_blocks
        if not bool(block.get("metadata_only", False))
        and _is_included_scene_ambience_block(block, include_scene_ambience)
    ]
    ...
    for block in playable_blocks:
        audio_path = _audio_path(project_root, block)
        if audio_path is None or not audio_path.is_file():
            raise ValueError("Every approved Audio Block must reference an existing WAV file.")
    _validate_compatible_wav_inputs(project_root, playable_blocks)
```

```python
def _is_assembly_block(audio_block: dict[str, object], include_scene_ambience: bool) -> bool:
    if _is_scene_ambience_block(audio_block):
        return bool(include_scene_ambience) and bool(str(audio_block.get("audio_relative_path", "") or "").strip())
```

```python
    audio_path = _audio_path(project_root, block)
    enriched["duration_seconds"] = 0.0 if audio_path is None else _wav_duration_seconds(audio_path)
```

  `audio_blocks_service.load_audio_blocks()` forces `metadata_only = True` for `SCENE_AMBIENCE`/`PAUSE`/`INDICATION` (`audio_blocks_service.py:3133`), so a *generated* ambience block is metadata-only too — it is never existence-checked and never passed through `_validate_compatible_wav_inputs`.

- **Why it matters:** the path is reachable and hits a plausible configuration. When the operator enables Scene Ambience placement (so Speech Blocks emits ambience rows) but leaves the Audio Blocks page's ambience-audio checkbox off, `_apply_scene_ambience_audio_policy` takes its `else` branch (`audio_blocks_service.py:2509`) and marks the row metadata-only/not-implemented **without clearing the `generated`/`approved` timestamps that `_initialize_audio_blocks` already set** (`audio_blocks_service.py:2359-2362, 2389-2390`). On the next load `_attach_derived_audio_path` therefore hands out `audio_blocks/<id>.wav` for a file that does not exist (`audio_blocks_service.py:3170`), violating the TTS Audio Blocks contract that "a set path … means generated audio exists on disk". With the default `include_scene_ambience = True`, pressing **Generate Audio** then runs: validation passes → `_build_output_plan` → `_build_composition_blocks` → `_enrich_block_duration` → `wave.open()` on the missing file → uncaught `FileNotFoundError`, surfaced verbatim in the failure message box. The operator has no way to read that as "untick Include Scene Ambience". The Scene Mix group builder already does the right check one screen over (`:557` `has_source_audio = all(path is not None and path.is_file())`), which is what makes the omission here a defect rather than a design choice.
- **Fix:** validate the same set the composition uses. In `_load_approved_audio_blocks`, replace the `not metadata_only` predicate with `_is_assembly_block(block, include_scene_ambience) and not _is_pause_block(block)` (i.e. every block that will actually be opened), so the missing WAV produces the intended `ValueError` up front. (The upstream phantom `audio_relative_path` is an Audio Blocks defect and should be fixed there too, but Audio Assembly must not trust the flag.)

### [AS-2] Whole-book output above 4 GiB aborts with `struct.error` from the WAV header patcher — **Major**

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\audio_assembly_service.py:829`
- **What:** the composed output is written straight through `wave.Wave_write` with no size guard.

```python
    with wave.open(str(temp_path), "wb") as output_wav:
        output_wav.setparams(reference_params)
```

  `Wave_write.writeframes()` re-patches the RIFF header on every chunk, and the stdlib does that with a 32-bit field (verified against the installed CPython 3.12.10):

```python
        self._file.write(struct.pack('<L', 36 + self._datawritten))
```

- **Why it matters:** `DEFAULT_AUDIO_ASSEMBLY_OUTPUT_MODE = "whole_book"` (`config.py:867`), so the default deliverable is a single WAV holding the entire audiobook. As soon as cumulative written bytes pass `2**32 - 36`, `_patchheader` raises `struct.error: 'L' format requires 0 <= number <= 4294967295` mid-write; the `with` block's `close()` then raises the same error again while unwinding. Threshold by source format: ~6.8 h at 44.1 kHz/16-bit/stereo, ~13.5 h mono, ~24.8 h at 24 kHz mono. A long book at 44.1 kHz therefore fails after possibly hours of composition, leaving a multi-GB `audiobook.wav.tmp` behind and showing the operator a `struct` error message with no hint about what to do.
- **Fix:** before opening the output, estimate `sum(block durations) * framerate * nchannels * sampwidth` (the plan already carries durations) and raise a clear `RuntimeError` — "this output would exceed the 4 GB WAV limit; use Per text chunk or Time limit output mode" — when it exceeds `2**32 - 36 - 44`. Same guard is worth adding around the temp-file cleanup so the partial `.tmp` is removed.

### [AS-3] Saving TTS Settings without pressing Test Connection wipes the persisted probe flag — **Minor**

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\ui\pages\tts_settings_page.py:262` and `:396`
- **What:** `load_state` deliberately blanks the probe state for display, and `build_settings` then writes that blank state back to disk.

```python
        # Dialog always opens with a fresh "Not connected" state — the operator must
        # re-run Test Connection in each session so the displayed status reflects the
        # live runtime and not a stale flag persisted from a previous session.
        self._probe_succeeded = False
        self._probe_message = ""
```

```python
        merged_settings["tts_runtime_probe_succeeded"] = self._probe_succeeded
        merged_settings["tts_runtime_probe_message"] = self._probe_message
```

- **Why it matters:** the display reset is intentional; persisting it is not. Open TTS Settings, change only "Scene Ambience Steps", press Save → `tts_runtime_probe_succeeded` becomes `False` in `settings.json`. Narrator Voice and Character Voices read that flag (`narrator_definition_state_service.py:124`, `character_voices_state_service.py:80`) and start telling the operator the runtime is not connected even though nothing about the connection changed. The discovered-model cache is preserved, so the message is purely wrong.
- **Fix:** keep the reset local to the widget: in `build_settings`, carry the two probe fields over from `existing_settings_payload` unless a probe actually ran in this dialog session (e.g. set a `self._probe_ran = False` in `load_state`, `True` in `apply_probe_result`, and only overwrite when it is `True`).

### [AS-4] Runtime WAV downloads do not translate `TimeoutError` — **Minor**

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\voiceweaver_runtime_service.py:1041` and `:1063`
- **What:** every other request helper in this module has four `except` arms; the two download helpers were copy-pasted with only two.

```python
    try:
        return _read_bytes(_endpoint_url(base_url, "/v1/voice"), headers, timeout_seconds)
    except error.HTTPError as exception:
        raise RuntimeError(_runtime_error_message(exception)) from exception
    except error.URLError as exception:
        raise RuntimeError(f"Connection failed: {getattr(exception, 'reason', exception)}.") from exception
```

  compare `_request_json_endpoint` (`:1188`), `_post_json_endpoint` (`:1218`), `generate_voice_clone` (`:799`) — all of which also catch `TimeoutError` (and `ValueError` where relevant).
- **Why it matters:** a socket timeout during `response.read()` is raised as bare `TimeoutError`, not converted by urllib. The block download is the longest read in the workflow (a whole synthesized WAV), so this is exactly where a stalled runtime bites. The operator sees `timed out` / an empty message instead of the module's "Connection failed: request timed out." wording that the rest of the code guarantees.
- **Fix:** add `except TimeoutError as exception: raise RuntimeError("Connection failed: request timed out.") from exception` to both `download_generated_voice` and `download_generated_audio`.

### [AS-5] `started_at` / `completed_at` are computed and thrown away; resume-token lookup is unreachable — **Minor**

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\audio_assembly_service.py:1362` (report), `:1442` (state), `:1751` (resolver)
- **What:** `_build_report` accepts `started_at` and `completed_at` but its returned dict contains neither; and the state writer that `_resolve_started_at` reads from always stores `None`.

```python
    return build_operation_state_payload(
        ...
        resume_checkpoint=None,
    )
```

```python
    resume_checkpoint = existing_state.get("resume_checkpoint", {}) if isinstance(existing_state, dict) else {}
    ...
    run_token = str(resume_checkpoint.get("run_token", "") or "").strip()
    return run_token or _utc_now_iso()
```

- **Why it matters:** `audio_assembly_report.json` carries no start/finish timestamps at all, so a resumed run is indistinguishable from a fresh one in the persisted record, and the run-token branch of `_resolve_started_at` can never be taken. Low blast radius (nothing in the UI reads them today), but the report is the durable record of the composition and silently loses data the code goes to the trouble of computing.
- **Fix:** either add `"started_at": started_at, "completed_at": completed_at` to the report dict and pass `resume_checkpoint={"run_token": started_at}` in `_build_operation_state`, or drop the three parameters and `_resolve_started_at` entirely.

### [AS-6] Every Audio Assembly page refresh SHA-1s all Scene Ambience WAVs on the GUI thread — **Minor**

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\audio_assembly_service.py:1148`
- **What:** the deterministic scene-mix filename embeds a content fingerprint, and building it hashes every source file end to end.

```python
    group_digest = hashlib.sha1(_scene_mix_group_key(first_block).encode("utf-8")).hexdigest()[:10]  # noqa: S324
    source_digest = _scene_mix_source_fingerprint(project_root, source_blocks, duration_seconds)[:10]
```

  `_scene_mix_source_fingerprint` calls `_file_sha1` per source (`:1177`), and `_scene_mix_group_record` is reached from `list_scene_mix_groups` → `build_audio_assembly_state` → `MainWindow.show_project_state` (`main_window.py:592`), i.e. on every page navigation and after every operation. `_scene_mix_duration_seconds` additionally opens every ambience WAV.
- **Why it matters:** on a project with many ambience blocks this reads and hashes hundreds of MB synchronously in the Qt event loop, freezing the window each time the operator switches pages. This is not micro-optimisation — the work is unbounded in the project's audio size and repeats on every refresh.
- **Fix:** cache the per-file digest keyed by `(path, st_mtime_ns, st_size)`, or drop `file_sha1` from the preview-path fingerprint and rely on the block ids + duration (regeneration already overwrites the deterministic path).

### [AS-7] `wait_for_terminal_operation` treats `idle` as a terminal state — **Minor (Uncertain)**

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\voiceweaver_runtime_service.py:996`
- **What:**

```python
        operation_payload = last_status_payload.get("operation", {})
        operation_status = (
            str(
                operation_payload.get("status", operation_payload.get("kind", "idle"))
                if isinstance(operation_payload, dict)
                else ""
            )
            .strip()
            .lower()
        )
        if operation_status in {"completed", "failed", "idle"}:
            return last_status_payload
```

- **Why it matters:** two contract-dependent hazards. (1) If the runtime has not yet flipped `operation.status` away from `idle` when the first poll lands (the POST returns before the worker starts), the wait returns immediately; every caller then checks `status == "completed"` and raises a spurious "VoiceWeaver reported a failed operation." for a request that is actually running — a wasted block generation. (2) If the runtime sends `"operation": null` when idle, `operation_status` becomes `""`, never matches a terminal value, and the loop spins until the full `DEFAULT_TTS_OPERATION_TIMEOUT_SECONDS` before raising. The `operation_payload.get("kind", ...)` fallback also compares an operation *kind* against *status* tokens, which can never match. I could not confirm the VoiceWeaver `/v1/status` contract from this repository, hence Uncertain.
- **Fix:** require at least one observed non-idle poll (or a returned operation id) before accepting `idle` as terminal, and drop the `kind` fallback so a missing `status` is treated as "still running" rather than as a status token.

## Duplication

- **`_decode_pcm_sample` / `_encode_pcm_sample`** (`audio_assembly_service.py:1064`, `:1077`) reimplement what `pcm_codec._unpack_sample` / `_pack_sample` already do, and they carry an 8-bit-unsigned branch (`b"\x80"`, `+128/-128`) for a width the same module deliberately refuses in `_WAV_SAMPLE_WIDTH_BY_FORMAT`. Same for the unreachable `silence_byte = b"\x80"` branch in `_read_or_pad_wav_frames` (`:1037`). Collapsing them onto the codec would remove the only place in this component where two different 8-bit conventions coexist.
- **`_positive_int_from_mapping`** is byte-for-byte identical in `tts_budget_service.py:187` and `audio_blocks_service.py:1560`.
- **`_wav_duration_seconds`** exists in `audio_assembly_service.py:1640` and again in `audio_blocks_artifact_service` (re-exported as `audio_blocks_service._wav_duration_seconds`).
- **Request error translation** in `voiceweaver_runtime_service` is copy-pasted five times (`generate_voice_clone`, `create_voice_clone_prompt`, `_request_json_endpoint`, `_post_json_endpoint`, `_request_without_json_response`) plus two truncated copies in the download helpers — the truncation is exactly finding AS-4. One `_translate_runtime_errors` context manager would remove the class of bug.
- **`_normalize_active_model_payload`** (`:297`) and `_normalize_status_payload` (`:319`) run the identical `("effective_model_parameters", "effective_parameters", "model_parameters")` loop plus the same range normalization.

## Verified-clean notes

- **`pcm_codec` is bit-exact.** Ran a differential test against `audioop` on this interpreter (3.12.10): `lin2lin` across all 16 width pairs, `tostereo`/`tomono` for widths 1-4, and `ratecv` for 44100→22050, 22050→44100, 48000→44100, 24000→24000, 16000→48000 in mono and stereo — including a chunked stream (37-frame chunks) threading the state, which reproduced the single-call output byte for byte. The deliberate `audioop` quirks (signed 8-bit, shift-not-round widening, `value < minimum + 1.0` bounding, truncate-toward-zero division) are all faithfully reproduced.
- **WAV header arithmetic below 4 GiB.** `output_wav.setparams(reference_params)` carries the *source* file's `nframes` into the writer, but `Wave_write.writeframes` and `close` re-patch both the RIFF form length and the data length from `_datawritten`, and the output is a seekable regular file, so byte-rate, block-align, bits-per-sample and both size fields end up correct. (Above 4 GiB see AS-2.)
- **No silent format mismatch.** `_copy_or_convert_wav_frames` (`:1277`) compares `params[:3]` (channels, width, rate) *and* `params[4:]` (comptype, compname) and routes anything different through `_convert_wav_frame_chunk`; `_mix_wav_sources` (`:984`) raises on mismatched sources instead of mixing them. There is no path that concatenates raw frames of differing rate/channels/width, so no chipmunk/noise output.
- **Resampler state is scoped correctly.** `rate_state` is reset per source file and threaded across chunks within a file, which is what continuity requires.
- **8-bit PCM exclusion is coherent.** `_WAV_SAMPLE_WIDTH_BY_FORMAT` admits only 2/3/4 and `_write_silence` zero-fills, which is true silence for signed PCM at all three widths; the rejection is enforced in `_compose_output_file:849`, `_mix_wav_sources:978/982` and `_validate_compatible_wav_inputs:1667`.
- **No file-handle leaks.** Every `wave.open` is in a `with`; `_mix_wav_sources` holds its N sources in an `ExitStack`; `_file_sha1` streams in 1 MiB chunks under `with`.
- **Output publish/overwrite is safe.** Outputs and scene mixes are written to `<name>.tmp` then `replace()`d; playback is stopped before Generate and before Reset (`audio_assembly_ui_controller.py:78`, `:111`, `:525`), so the Windows "file in use" unlink failure is avoided.
- **Cancellation.** `raise_if_cancelled` is polled per output, per source block, per copy chunk and per mix chunk; the cancelled report/state is persisted before re-raising, and completed outputs survive (`_completed_records_for_resume` re-checks that each file still exists).
- **Time-limit planning boundaries.** `_plan_time_limited_outputs` uses strict `>` on both the pack test and the over-limit warning, flushes the pending group before starting a new one, and re-seeds `added_seconds` after a flush — traced against a short/long/short block sequence with no off-by-one.
- **No subprocess surface.** The "runtime" is HTTP over `urllib` only; every request passes an explicit `timeout`, so the shell-quoting, pipe-deadlock, orphaned-process and ignored-exit-code classes of bug do not apply here.
