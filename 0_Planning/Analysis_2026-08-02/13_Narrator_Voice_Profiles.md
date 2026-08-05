# Component Review — Narrator Voice / Voice Profiles

_Reviewed 2026-08-02. Files: `services/narrator_definition_service.py` (1382), `services/narrator_definition_state_service.py` (551), `services/narrator_profile_generation_service.py` (1395), `ui/pages/narator_voice_page.py` (789), `ui/controllers/narator_voice_ui_controller.py` (1461). Total ~5578 lines._

## Summary

The persistence layer is in good shape: the strict `narrator_voice.json` contract is enforced on every read and write, the atomic WAV/JSON writes are correct, the resume checkpoint is internally consistent, and playback file handles are released before every path that replaces or deletes a sample WAV. The defects cluster in two places: (a) a word-count helper that is wrong for space-less scripts, which makes AI narrator generation permanently impossible for Japanese/Chinese projects and disables the TTS preview budget guard for them, and (b) the AI-generation entry point in the controller, which mishandles the "previous run failed/cancelled" state in three separate ways. 6 Major, 3 Minor. No Critical (no crash-on-normal-path or corrupted persisted state was found).

## Findings

### [NV-1] Generated preview text is validated with a whitespace word count, so AI narrator generation can never succeed for Japanese/Chinese — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/narrator_profile_generation_service.py:984`
- **What:** the minimum/maximum preview length gate uses `tts_budget_service.estimated_word_count`, which is pure whitespace splitting.

```python
preview_word_count = tts_budget_service.estimated_word_count(preview_text)
if preview_word_count < min_preview_words:
    raise ValueError(
        f"Generated narrator profile '{display_name}' preview_text is too short for a Qwen TTS reference "
        f"({preview_word_count} words, minimum {min_preview_words})."
    )
```

  `_minimum_preview_word_count()` resolves to `int(6.0 * 2.5 + 0.999) == 15`. The helper it calls is documented as whitespace-only:

```python
def estimated_word_count(text: str) -> int:
    return len([word for word in str(text).split() if word.strip()])
```

  The codebase already has the script-aware replacement, `tts_budget_service.estimate_budget_units`, whose docstring says "Word counting is meaningless for scripts written without spaces"; it is what `speech_blocks_narrator_split_service` and `speech_blocks_normalization_service` use.
- **Why it matters:** `_voice_language_state` can legitimately resolve the voice language to `ja` or `zh` (both are in `config.TRANSLATION_LANGUAGE_OPTIONS`, and the code comes from the cleanup document's detected language or the completed translation target). A correct Japanese one-sentence preview contains no spaces, so `estimated_word_count` returns `1`, which is always `< 15`. Every AI narrator-profile run for such a project fails at the very last step — after the whole multi-window style-analysis pass has already been paid for — with "preview_text is too short … (1 words, minimum 15)", and the document is left at `status="failed"` (which in turn triggers NV-3/NV-4). Korean is affected in practice too: the project's own built-in Korean default preview text (`DEFAULT_PREVIEW_TEXT_BY_LANGUAGE["ko"]`) is 12 whitespace tokens, below the 15 minimum.
- **Fix:** use the script-aware helper for both bounds: `preview_word_count = tts_budget_service.estimate_budget_units(preview_text)`.

### [NV-2] The narrator sample "preview text over budget" guard is inert for space-less scripts — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/controllers/narator_voice_ui_controller.py:978`
- **What:** the same whitespace helper is used to compare the preview text against the TTS model's safe budget.

```python
budget_payload = tts_budget_service.resolve_cached_tts_budget(discovered_models)
safe_word_count = tts_budget_service.estimated_safe_word_count(budget_payload)
preview_word_count = tts_budget_service.estimated_word_count(preview_text)
if preview_word_count > safe_word_count:
    raise RuntimeError(
        progress_messages["preview_text_over_budget"].format(...)
    )
```

- **Why it matters:** for a Chinese/Japanese profile, a 512-character preview text (the full `DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT`, which the editor happily allows) counts as **1 word**, so the guard never fires. That is roughly 85 s of speech handed to a runtime whose default `max_new_tokens` budget corresponds to ~40 s; VoiceWeaver truncates or rejects it and the operator gets an opaque runtime error instead of the localized over-budget message that exists for exactly this case. The same helper feeds the operator-facing budget readouts, so the status line (`narrator_definition_state_service.py:322`) and the page label (`narator_voice_page.py:608`, its own `toPlainText().split()`) both show "1 word" for a full-length CJK preview.
- **Fix:** `preview_word_count = tts_budget_service.estimate_budget_units(preview_text)` in the worker, and the same helper for the two display counters.

### [NV-3] After any failed or cancelled generation, the operator is never asked for profile instructions again — the old ones are silently reused — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/controllers/narator_voice_ui_controller.py:549`
- **What:**

```python
additional_profile_instructions = None
if _is_resuming_profile_generation(window):
    pass
else:
    additional_profile_instructions = prompt_ai_narrator_profile_instructions(window, current_language)
    if additional_profile_instructions is None:
        return
```

  `_is_resuming_profile_generation` returns `True` for *any* non-completed AI state, without checking whether the checkpoint is actually reusable:

```python
return is_ai_profile_generation and str(operation_state.get("status", "")) in {
    "running",
    "failed",
    "cancelled",
}
```

  Passing `None` then makes the service fall back to the stored text (`narrator_profile_generation_service.py:738-751`).
- **Why it matters:** the document status only returns to `completed` on a successful run. So once a run fails (which, per NV-1, is guaranteed for some languages, and is generally common with LLM contract validation) or is cancelled, the instructions dialog never appears again, and every subsequent attempt silently re-applies the old instruction text — including attempts that are *not* resumes at all, because `_restore_resume_state` rejected the checkpoint (different profile count, different AI profile, changed source text). The operator has no way to clear or change the instructions short of getting one run to succeed.
- **Fix:** only skip the prompt when the checkpoint is genuinely reusable; the simplest correct version is to always prompt, pre-filled with the stored `metadata["additional_profile_instructions"]` from `load_operation_state`, instead of skipping the dialog.

### [NV-4] Resuming re-asks for the profile count with the config default, silently discarding the saved checkpoint — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/controllers/narator_voice_ui_controller.py:538`
- **What:** the count dialog is always seeded with the config constant, never with the checkpointed value.

```python
profile_count, accepted = QInputDialog.getInt(
    window,
    ui_state_service.translate("dialog.narator_voice_generate_profiles_title", current_language),
    ui_state_service.translate("dialog.narator_voice_generate_profiles_count_prompt", current_language),
    config.DEFAULT_NARRATOR_PROFILE_GENERATION_COUNT,
    1,
    config.MAX_NARRATOR_PROFILE_GENERATION_COUNT,
    1,
)
```

  The service treats a differing count as an incompatible checkpoint and starts over:

```python
if resume_checkpoint.get("requested_count") != requested_count:
    return fallback
```

- **Why it matters:** operator requests 12 profiles, the run is cancelled after 9 of 11 style windows. On retry the dialog shows `6`; accepting it (the natural action — the dialog gives no hint that the number is load-bearing) throws away all 9 checkpointed windows and re-runs the entire style analysis, re-spending the tokens the resume feature exists to protect. `load_operation_state` already returns `resume_checkpoint["requested_count"]`, so the correct default is available at the call site.
- **Fix:** when `_is_resuming_profile_generation(window)` is true, seed the dialog from `load_operation_state(...)["resume_checkpoint"]["requested_count"]` instead of `config.DEFAULT_NARRATOR_PROFILE_GENERATION_COUNT`.

### [NV-5] The operator's AI-profile choice is reset to the settings default on every page refresh — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/main_window.py:482` (with `services/narrator_definition_state_service.py:35`)
- **What:** the state builder accepts a `selected_profile_id`, but the only production caller never passes one:

```python
self._narator_voice_page.set_ai_profiles(
    **narrator_definition_state_service.build_narrator_profile_generation_profile_state(
        self._settings_payload,
        project_root,
    )
)
```

  With `selected_profile_id=None`, the builder always re-resolves to the configured default:

```python
resolved_selected_id = (
    selected_profile_id
    if selected_profile_id in enabled_ids
    else (
        str(default_profile_id) if default_profile_id in enabled_ids else (enabled_ids[0] if enabled_ids else None)
    )
)
```

  and `NaratorVoicePage.set_ai_profiles` unconditionally applies it via `setCurrentIndex`.
- **Why it matters:** every state refresh rewrites the combo. `handle_selection_change_requested` (clicking a different narrator in the list) calls `_refresh_narator_voice_page_state` directly, as does every `show_project_state`. So the natural sequence "pick the online AI profile → click the narrator I want → Generate Narators" runs against `default_narrator_profile_generation_profile_id`, not the profile the operator chose. The AI Translation and Character Discovery pages do not have this problem — they thread the selection through their state payloads (`main_window.py:433`, `:462`).
- **Fix:** have the page keep its own selection and pass it back, i.e. call the builder with `self._narator_voice_page.current_ai_profile_id()` as the third argument.

### [NV-6] Page-state building persistently rewrites `narrator_voice.json` and wipes every profile's preview text on a voice-language change — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/narrator_definition_state_service.py:143` (with `services/narrator_definition_service.py:312`)
- **What:** a read-only-looking state builder performs a document mutation on every refresh:

```python
narrator_definition_service.apply_voice_language_to_profiles(project_root, selected_voice_language)
profiles = narrator_definition_service.load_profiles(project_root)
```

  and that function replaces the stored preview text of *every* profile whenever the language differs, without checking whether the text was operator- or AI-authored:

```python
previous_language = narrator_language_code(profile.get("language", DEFAULT_NARRATOR_LANGUAGE))
profiles.append(
    _normalize_profile(
        {
            **dict(profile),
            "language": normalized_language,
            "preview_text": (
                localized_preview_text
                if previous_language != normalized_language
                else profile.get("preview_text", localized_preview_text)
            ),
        }
    )
)
```

- **Why it matters:** the resolved voice language flips in normal use. With `project_options_locked`, `validate_project_manifest` pins `selected_voice_language` to `target_language`, but `_voice_language_state` only makes the translated code *selectable* once `translation_is_completed(project_root)` is true — so the effective language changes from the original code to the target code the moment translation finishes. The very next time the Narator Voice page is refreshed, every AI-generated and every operator-edited `preview_text` in the project is silently overwritten with `DEFAULT_PREVIEW_TEXT_BY_LANGUAGE[...]`. Nothing warns, nothing confirms, and there is no undo. Note that the profile `sample` block is left attached and `has_profile_sample` still returns `True`, so the page keeps reporting a valid sample whose recorded `preview_text` no longer matches the profile.
- **Fix:** keep the language migration but preserve authored text — only substitute the localized default when the stored `preview_text` still equals the previous language's `DEFAULT_PREVIEW_TEXT_BY_LANGUAGE` entry. (Separately worth moving the call out of the state builder into the place that actually changes the language, so a page refresh stops writing to disk.)

### [NV-7] `handle_edit_profile_requested` swallows the only error it can actually receive — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/controllers/narator_voice_ui_controller.py:167`
- **What:**

```python
except ValueError as error:
    if str(error) == "readonly_profile":
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("narator_voice.error_readonly_profile", current_language),
        )
    return
```

  `"readonly_profile"` is not raised anywhere in the codebase (only `character_voices_service` raises the analogous `"readonly_target"`), so this branch is dead. The error `begin_profile_edit` actually raises is `ValueError("missing_profile")`, which falls through to the bare `return`.
- **Why it matters:** if the inspected profile has disappeared (stale inspected id after an external change or a failed refresh), pressing Edit does nothing at all: no edit mode, no message, no log. The operator sees an unresponsive button.
- **Fix:** show the generic profile-error message for the non-`readonly_profile` case instead of returning silently.

### [NV-8] `delete_profile_sample` can raise `OSError` out of a Qt slot; `delete_profile` suppresses the same failure — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/narrator_definition_service.py:751`
- **What:** the two deletion paths disagree.

```python
def delete_profile_sample(project_root: str | Path, profile_id: str) -> None:
    audio_path, _metadata_path = profile_sample_paths(project_root, profile_id)
    if audio_path.exists():
        audio_path.unlink()          # no suppression
    _update_profile_sample_metadata(project_root, profile_id, None)
```

  versus `delete_profile` (`:607`):

```python
audio_path = _current_profile_sample_audio_path(project_root, profile_id)
with suppress(OSError):
    audio_path.unlink(missing_ok=True)
```

- **Why it matters:** `delete_profile_sample` is reached from `begin_profile_edit`, whose caller (`handle_edit_profile_requested`) only catches `ValueError`. On Windows, a WAV still held open by the media backend makes `unlink()` raise `PermissionError`, which escapes the slot; the sample metadata is then never cleared, so the profile keeps a `sample` entry for a file that may or may not still exist. `_stop_preview_playback` is called first, which makes this unlikely but not impossible (the FFmpeg backend releases the handle asynchronously).
- **Fix:** use the same `with suppress(OSError): audio_path.unlink(missing_ok=True)` form in `delete_profile_sample`, so the metadata is cleared either way.

### [NV-9] Deleting a profile does not stop preview playback, leaving an orphan WAV — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/controllers/narator_voice_ui_controller.py:242`
- **What:** `handle_generate_sample_requested`, `handle_import_sample_requested` and `handle_edit_profile_requested` all call `_stop_preview_playback(window)` before touching the WAV; `handle_delete_profile_requested` does not. After a preview has finished, `handle_preview_playback_state_changed` only calls `set_preview_active(False)` — the player's source is still the profile's WAV.
- **Why it matters:** on Windows the `unlink` inside `delete_profile` then fails and is suppressed, so `audio_narator_<id>.wav` stays in the project root forever, unreferenced by the document. Profile ids are UUID-based so no wrong sample is ever served, but the stray file is picked up by anything that globs the project root (export/snapshot inventories).
- **Fix:** call `_stop_preview_playback(window)` in `handle_delete_profile_requested` alongside the other mutation paths.

## Duplication

- **Preview-text character-limit resolution exists four times** with identical logic and identical defaults: `narrator_definition_state_service._preview_text_character_limit` (:210), `narator_voice_ui_controller._preview_text_character_limit` (:1406), `narator_voice_ui_controller._limited_preview_text` (:1097), and `narator_voice_page._positive_character_limit` (:776). One shared helper would also guarantee the page and the sample worker truncate at the same point.
- **Preview word counting exists three times** — `narator_voice_page._update_preview_budget_label` (:608) reimplements `tts_budget_service.estimated_word_count` inline, while `build_status_lines` (:322) and `_generate_and_store_sample` (:980) call it. All three should call the single script-aware helper (see NV-1/NV-2).
- **`_write_operation_state` is invoked with the same 20-argument block three times** in `generate_narrator_profiles` (:223, :263, :333) with only `status`/`progress_current` differing; the function then discards 9 of those arguments (`_ = state_path`, `_ = input_path`, `_ = report_path`, …). Collapsing to the fields it actually persists would remove a large copy-paste surface.

## Verified-clean notes

- **Document contract round-trip.** `_validate_narrator_voice_document` is applied on both read and write, and every mutator (`create_custom_profile`, `update_custom_profile`, `delete_profile`, `_update_profile_sample_metadata`, `_write_operation_state`) does load → mutate → write on the full document, so no field is ever dropped. `delete_profile` correctly clears `selected_profile_id` before writing, which is what the `selected_profile_id in profile_ids` invariant requires.
- **Resume checkpoint consistency.** `_gender_allocation` always satisfies `male + female == requested_count` and `random ∈ {0,1}`, which is exactly what both `_validate_resume` and `_is_valid_gender_allocation` demand; `completed_window_count` is always written as `len(style_observations)`, satisfying the `len(observations) == completed_count` check. The closure `_write_interrupted_state` reads `allocation`/`token_usage`/`observations` as free variables, so it always persists the current values after a resume rebinds them.
- **Cancellation.** Every LLM call and every loop iteration is bracketed by `raise_if_cancelled` / `except OperationCancelledError`, and both paths persist `status="cancelled"` with an intact checkpoint before re-raising; profiles are appended only after full validation, so a cancelled run never leaves partial profiles.
- **WAV file handling.** `_write_bytes_atomic` uses a same-directory temp file + `os.replace`, and all three paths that replace or delete a profile WAV while the player could hold it (`generate sample`, `import sample`, `edit profile`) call `_stop_preview_playback` first — the one exception is NV-9.
- **Progress-callback signatures.** `_emit_sample_progress` passes 4 positional args and `emit_progress_update` passes 5; `ThreadedOperationWorker._emit_progress` has `token_usage=None` defaulted, so both are correct. The synchronous `_update(percent, message_key)` callback handed to `invalidate_audio_blocks_for_voice_targets` matches that function's documented `(percent, translation key)` contract.
- **LLM response parsing.** `_normalize_style_observation` and `_validated_generated_profiles` both coerce non-dict payloads to `{}`, so a model returning a bare list or a string yields a clear "must return exactly N profiles" error rather than a `TypeError`. The generation prompt's `male_count`/`female_count` already include the random extra, so the prompt and the post-validation allocation check agree for odd counts.
- **`can_generate` hardcoded to `True` in `_build_profile_entry`** is intentional, not a bug — `tests/test_narrator_definition_state_service.py:104` explicitly asserts Generate Sample stays clickable with a stale runtime cache, and the worker re-probes and raises the real reason.
- **Narration-mode handling.** The narrator component does not branch on `voice_assignment_mode` at all: `validate_tts_plan` normalizes it against `config.TTS_VOICE_ASSIGNMENT_MODE_OPTIONS` and `profile_generation_request` explicitly ignores the plan (`_ = tts_plan`). Mode-dependent behaviour lives entirely in Speech/Audio Blocks and Character Voices, so there is no path here that assumes one mode while the project is locked to the other.
- **Voice-parameter clamping.** There is nothing to clamp: `_build_generation_request` never emits a `model_parameters` key, so the defensive read in `_generate_and_store_sample:1050` always resolves to `None` and VoiceWeaver runs on its own defaults. Dead but harmless — worth deleting if model parameters are not planned.
