# Cross-Cutting Review — Duplication, Consistency, Dead Code
_Reviewed 2026-08-02. Scope: whole src tree._

## Summary

The codebase is in far better cross-cutting shape than a 68k-line app usually is: LLM JSON parsing exists exactly once, token estimation is a single shared helper with thin per-service wrappers, artifact file names all come from `config`, every text I/O call passes an explicit `encoding=`, and there are zero mutable default arguments or mutated module-level containers. Sections 2, 5 and 7 are genuinely clean.

The real problems are in three places. First, a **diverged model-normalization pair** between `settings_service` and `voiceweaver_runtime_service`: the settings copy silently drops `generation_parameter_ranges`, which three separate consumers read to size the TTS split budget — the `"range_default"` branch of `tts_budget_service.resolve_cached_tts_budget` is unreachable on the only path that actually feeds it. Second, the **five per-stage "authoritative document" loaders disagree on what a corrupt JSON document means**: four raise a typed "reset to recover" error, three silently report "not started", so a damaged `speech_blocks.json` or `audio_blocks.json` reads as never-generated with no log line and gets overwritten. Third, **two different rules derive the API path from the same `base_url` field**, so the Test Connection button and the actual chat request can disagree.

Secondary findings: a reset-glob gap that orphans character-voice WAVs, one config constant that was deprecated in `settings_service` but left behind in `config.py`, an inert per-component log-level override mechanism, and four dead UI page methods (~94 lines).

---

## 1. Diverged duplicate helpers

### [X-1] VoiceWeaver discovered-model normalization — 2 implementations, one drops a field the other keeps — **Major**

- **Copies:**
  - `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\voiceweaver_runtime_service.py:348` — `_normalize_model`
  - `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\settings_service.py:659` — `_normalize_tts_runtime_model`

- **How they differ:**

  The runtime copy emits `generation_parameter_ranges` (`voiceweaver_runtime_service.py:369-371`):
  ```python
  "generation_parameter_ranges": _normalize_generation_parameter_ranges(
      candidate_model.get("generation_parameter_ranges")
  ),
  ```
  The settings copy has **no such key at all** — its returned dict goes straight from `supported_languages` to `default_model_parameters` to `device_mode` (`settings_service.py:679-687`). The field is silently discarded.

  Two further differences in the same pair:
  - `status` casing. Runtime: `str(candidate_model.get("status", "unhealthy")).strip().lower() or "unhealthy"` (`voiceweaver_runtime_service.py:366`). Settings: `str(candidate_model.get("status", _TTS_RUNTIME_MODEL_DEFAULTS["status"])).strip()` (`settings_service.py:675-676`) — **no `.lower()`**.
  - `default_model_parameters`. Runtime filters to scalars via `_normalize_model_parameters` (`voiceweaver_runtime_service.py:235`). Settings does a bare `dict(...)` shallow copy (`settings_service.py:681-685`), so nested objects/lists survive into `settings.json`.

- **Bug this causes:** `settings_service.py:560-561` runs every persisted `tts_runtime_discovered_models` entry through the settings copy, so the on-disk cache never contains `generation_parameter_ranges`. Three consumers read the cache and then look for exactly that key:
  - `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\audio_blocks_state_service.py:357-360`
  - `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\speech_blocks_state_service.py:167-170`
  - `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\speech_blocks_normalization_service.py:978-983`

  All three call `tts_budget_service.resolve_cached_tts_budget`, whose second budget source is (`F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\tts_budget_service.py:39`):
  ```python
  ("range_default", _parameter_range_default(model_payload.get("generation_parameter_ranges"))),
  ```
  That branch is **dead on the cached path**. When a model reports its `max_new_tokens` only as a range default (not as a `default_model_parameters` entry), the budget silently falls through to `config.DEFAULT_TTS_NARRATOR_ONLY_TOKEN_BUDGET` = 512 (`tts_budget_service.py:43`) instead of the model's real capacity. Speech Blocks are then split far more aggressively than necessary — the operator gets many short blocks and pays for many more TTS requests, with nothing anywhere indicating why.

  The `.lower()` omission is currently masked: `build_capability_matrix` re-lowercases at `voiceweaver_runtime_service.py:388`. It will bite the first time someone compares the cached `status` directly.

- **Fix:** delete `settings_service._normalize_tts_runtime_model` / `_normalize_tts_generation_modes` / `_normalize_tts_device_diagnostics` and call `voiceweaver_runtime_service._normalize_model` (promoted to public) from `settings_service.py:560`. The runtime copy is the correct one — it is the one that matches the REST contract it parses.

### [X-2] Chat endpoint vs. models endpoint — 2 rules for the same `base_url` field — **Minor**

- **Copies:**
  - `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\llm_provider_service.py:380` — `_build_chat_endpoint`, hand-rolled
  - `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\ai_backend_service.py:170` — `join_endpoint_url(base_url, "/models")`, via the shared `url_service`

- **How they differ:** both consume `profile_payload["base_url"]` (`llm_provider_service.py:325`, `ai_backend_service.py:171`), but:

  1. **`/v1` insertion.** `_build_chat_endpoint` synthesizes a version segment when the base has none (`llm_provider_service.py:394-397`):
     ```python
     elif base_path:
         full_path = f"{base_path}/v1/chat/completions"
     else:
         full_path = "/v1/chat/completions"
     ```
     `join_endpoint_url` never does — with an empty base path it returns the endpoint verbatim (`url_service.py:45`). So for `base_url = "https://api.example.com"`: model discovery requests `https://api.example.com/models` while chat requests `https://api.example.com/v1/chat/completions`.
  2. **Query/fragment.** `_build_chat_endpoint` rebuilds the URL with hardcoded empty params, query and fragment (`llm_provider_service.py:398-407`):
     ```python
     return parse.urlunparse((parsed_url.scheme, parsed_url.netloc, full_path, "", "", ""))
     ```
     `join_endpoint_url` preserves them via `parsed_url._replace(path=resolved_path)` (`url_service.py:46`).

- **Bug this causes:** an operator who enters a provider root without `/v1` (or a gateway URL carrying `?api-version=...`) sees **Test Connection fail with a 404 while generation works**, or the reverse. The shipped defaults in `settings.json:8` already end in `/v1`, which is why this has not been noticed.

- **Fix:** replace `_build_chat_endpoint` with `url_service.join_endpoint_url(base_url, "/v1/chat/completions", collapse_duplicate_version=True)` and give `_probe_openai_compatible_models` the same `/v1` handling, so one rule derives both paths.

### [X-3] `_write_bytes_atomic` — 2 byte-identical copies, and a third service that does not use it at all — **Minor**

- **Copies:**
  - `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\character_voices_service.py:1265-1302` (`_write_bytes_atomic` + `_unlink_temporary_file`)
  - `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\narrator_definition_service.py:1342-1379` (identical, line for line)

- **How they differ:** they do not — this is a verbatim 38-line duplication. The divergence is with the *third* service that writes the same class of artifact. `audio_blocks_service` writes generated WAVs with a plain, non-atomic call at `audio_blocks_service.py:1891`, `:1899` and `:2024`:
  ```python
  audio_path.write_bytes(audio_bytes)
  ```
  while `audio_assembly_service` uses yet a third pattern — temp file plus `temp_path.replace(output_path)` (`audio_assembly_service.py:853-854`, `:941-942`).

- **Bug this causes:** so four services generate runtime WAVs and three different durability policies apply. `audio_blocks_service` is the one that runs unattended for hours, so it is the one most likely to be killed mid-write; it is also the only one without atomic replacement. Truncation is partly caught downstream by `is_valid_wav_path` (`audio_blocks_service.py:2163`, `:2535`, `:3246`), which is why this is Minor rather than Major.

- **Fix:** add `write_bytes_atomic` to `persistence_service.py` next to `write_text_atomic`, delete both private copies, and use it at the three `audio_blocks_service` call sites.

### [X-4] Audio Assembly settings normalization — 2 byte-identical copies (~70 lines) — **Minor**

- **Copies:**
  - `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\audio_assembly_service.py:91-145` — `default_audio_assembly_settings` + `normalize_audio_assembly_settings`
  - `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\project_workspace_service.py:1537-1607` — `_default_audio_assembly_settings` + `_normalize_audio_assembly_settings` + `_bounded_int`

- **How they differ:** they do not, today — including the hardcoded bounds `1 .. 24 * 60` and `0 .. 60_000` repeated in both. `_bounded_int` is also duplicated a third time at `audio_assembly_service.py:1734`.

- **Bug this causes / will cause:** none yet. Reported only because of the size and because the manifest writer (`project_workspace_service`) and the manifest reader (`audio_assembly_service`) must agree byte-for-byte — the next bound change made in one place silently produces a manifest that the other clamps differently.

- **Fix:** keep the `audio_assembly_service` copy (it owns the domain and exports the typed `AudioAssemblySettings`) and have `project_workspace_service` import it.

_Also checked and found genuinely centralized, no action:_ token estimation (`ai_budget_service.estimate_text_tokens` at `:23`, wrapped by four thin per-service delegates), `is_path_inside_project` (three names, all delegating to `operation_runtime_service.py:395`), `safe_file_stem` (two delegating wrappers), the five `_normalized_additional_*_instructions` helpers (all one-liners), `_normalize_warning_flags` / `_normalize_device_diagnostics` / `_normalize_string_list` (identical short copies), and `_read_json` in `ai_backend_service.py:223` vs `voiceweaver_runtime_service.py:54` (identical apart from the error message text).

---

## 2. LLM response parsing

**None found.** There is exactly one hand-rolled "parse the model's JSON reply" implementation, and it is the strong one: `_parse_json_content` at `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\llm_provider_service.py:542`. It strips fences (`:549-550`), rejects empty content (`:551-552`), trims trailing prose via `raw_decode` (`:580-598`), repairs bad escaping (`:601`), rejects non-dict results (`:561-562`), and falls back to a model-driven repair pass (`:662`). Every service reaches the model through this one function; no other module touches `choices`, code fences, or `json.loads` on a model reply. The other `json.loads` sites (`ai_backend_service.py:238`, `voiceweaver_runtime_service.py:65/98/187`) parse REST envelopes, not model output, and both guard the non-dict case.

---

## 3. Silently swallowed failures

### [X-5] Corrupt authoritative documents — 3 stages report "not started", 4 stages raise, 1 logs — **Major**

- **Silent (`return None`, no log, no user signal):**
  - `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\speech_blocks_service.py:198-200`
  - `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\audio_blocks_service.py:186-188`
  - `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\text_cleanup_service.py:1009-1011`

- **Typed error the UI surfaces:**
  - `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\chunking_document_service.py:122-125` → `IncompatibleChunkingDocumentError`
  - `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\character_discovery_service.py:143-145` → `CharacterDocumentError`
  - `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\narrator_definition_service.py:159-163` → `NarratorVoiceDocumentContractError("... Reset Narrator Voice to recover ...")`
  - `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\ai_translation_service.py:119-121`

- **Logged warning, returns None:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\operation_runtime_service.py:651-658`

- **How they differ:** same operation, same failure, three policies. Compare directly —

  `speech_blocks_service.py:197-200`:
  ```python
  try:
      payload = load_optional_json_artifact(document_path)
  except (OSError, ValueError, json.JSONDecodeError):
      return None
  ```
  `narrator_definition_service.py:158-163`:
  ```python
  except (OSError, json.JSONDecodeError) as error:
      raise NarratorVoiceDocumentContractError(
          f"Narrator Voice data is unreadable. Reset Narrator Voice to recover: {error}"
      ) from error
  ```

- **Bug this causes:** Speech Blocks and Audio Blocks are the two most expensive artifacts in the app — hours of LLM and TTS work. If `speech_blocks.json` or `audio_blocks.json` becomes unreadable (external edit, disk-full, sync client, partially restored backup), the page reports **"not started"**, offers a fresh generation, and the next `write_*_document` overwrites the damaged file. No log line, no dialog, no warning — the operator has no way to learn the document existed. Every other stage tells them to reset explicitly. Note the `except` also swallows `ValueError`, so a `UnicodeDecodeError` on a partially written file lands here too.

- **Fix:** make the two block loaders log a warning at minimum (matching `operation_runtime_service.py:654`), and preferably raise the same "reset to recover" typed error the other four stages already raise. Keep the lenient path only for the genuinely optional `_read_checkpoint` in `text_cleanup_service`.

### [X-6] `except Exception` around manifest load on a write path — **Minor**

- **Location:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\character_voices_service.py:114-117`
  ```python
  try:
      manifest = project_workspace_service.load_manifest(project_root)
  except Exception:
      manifest = None
  ```
- **How it differs:** the sibling read-only helper at `:92-95` has the same swallow, which is defensible. This one is on `save_selected_voice_language`. `load_manifest` raises `ValueError` from `validate_project_manifest` for a corrupt manifest; catching it here means the `project_options_locked` guard at `:118-122` is skipped entirely.
- **Bug this causes:** with a corrupt `project.json`, a locked project silently accepts a voice-language change that the lock exists to prevent, and the save reports success.
- **Fix:** narrow to the expected `(FileNotFoundError, ValueError)` and log a warning; a corrupt manifest should not silently unlock project options.

_Checked and found fine:_ every `except ValueError` in the UI controllers surfaces a dialog (`narator_voice_ui_controller.py:94/202`, `character_voices_ui_controller.py:123`, `characters_ui_controller.py:166`, etc.), all four `cleanup_ai_adjudication_service` broad catches carry the failure into an operator-visible warning string (`:254`, `:348`, `:446`), `llm_provider_service.py:239` writes an AI-log failure record before re-raising, and the ~50 `except (TypeError, ValueError)` sites are numeric-coercion fallbacks with defined defaults.

---

## 4. Non-atomic / unguarded file writes and deletes

### [X-7] `reset_operation_data` has no glob for character-voice sample WAVs — **Minor**

- **Writer:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\character_voices_service.py:477` puts sample WAVs at the project root:
  ```python
  audio_path = Path(project_root) / f"audio_{_normalized_audio_name(audio_name_source)}.wav"
  ```
- **Reset map:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\operation_runtime_service.py:107-109`
  ```python
  _OPERATION_ARTIFACT_GLOBS = {
      "narrator_definition": ("audio_narator_*.wav",),
  }
  ```
  and `:86` gives `character_voices` only `(config.CHARACTER_VOICES_TARGETS_FILE_NAME,)` — no glob entry.
- **Bug this causes:** resetting Character Voices (`workflow_impact_service.py:246` → `operation_runtime_service.py:603-610`) deletes `characters_voice.json` but leaves every `audio_*.wav` in the project root forever. They accumulate across resets and are picked up by `project_snapshot_service._iter_project_files`, inflating every ZIP snapshot with dead audio. Secondary edge: a character whose display name normalizes to `narator_*` produces `audio_narator_*.wav`, which the *narrator* reset glob would then delete.
- **Fix:** add `"character_voices": ("audio_*.wav",)` to `_OPERATION_ARTIFACT_GLOBS`, or give the character-voice files a distinct prefix (`audio_voice_*`) so the two globs cannot overlap.

_Checked and found fine:_ every important project artifact goes through `persistence_service.write_json_atomic` / `write_text_atomic` (30 call sites across all stages). Deletions are guarded: `workflow_impact_service.py:612` checks `is_path_inside_project` before `unlink`, `project_snapshot_service.py:109-110` refuses a destination inside the project, and `reset_operation_data` only unlinks names drawn from the `config`-backed constant map. `home_ui_controller.py:388` writes the user-chosen export non-atomically, but it is outside the project root and any `OSError` is reported in a dialog at `:389-395`. No `shutil.rmtree` anywhere in `src`.

---

## 5. Missing explicit encoding

**None found.** Every `read_text` / `write_text` / `Path.open` in text mode passes `encoding=` explicitly. The three `read_text(` hits that looked bare (`text_cleanup_service.py:121`, `:427`, `:910`) carry `encoding="utf-8"` on the following line. `persistence_service.write_text_atomic` defaults to `encoding="utf-8"` (`:33`) and pins `newline=""` (`:53`). The four remaining `open()` calls are `"rb"` (`audio_assembly_service.py:1715`, `source_ledger_service.py:204`) or already encoded (`llm_provider_service.py:790`, `project_export_service.py:1084`). Source-file import handles encoding deliberately through `_read_text_with_fallback` / `_decode_bytes_with_fallback` (`text_extraction_adapters.py:667-677`) and records the selected encoding in the metadata.

---

## 6. Config constant drift

### [X-8] `DEFAULT_SCENE_AMBIENCE_GENERATION_ENABLED` — deprecated in the service, left behind in config — **Minor**

- **Definition:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\config.py:700`
  ```python
  DEFAULT_SCENE_AMBIENCE_GENERATION_ENABLED = False
  ```
- **Evidence it is inert:** the matching settings key was explicitly retired at `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\settings_service.py:380-390`, which pops it and logs *"Removed deprecated 'scene_ambience_generation_enabled' setting; Scene Ambience placement now owns enablement."* The constant itself is referenced nowhere in `src` or `tests` — the only surviving name is `config.DEFAULT_SCENE_AMBIENCE_PLACEMENT` (`audio_blocks_state_service.py:187`, `:190`). Meanwhile eight call sites hardcode `False` as the enablement default (`audio_blocks_service.py:493, 530, 607, 1094, 1154, 1254, 2288, 2487`), e.g. `bool(generation_context.get("generate_scene_ambience_audio", False))`.
- **Bug this causes:** a maintainer flipping the constant to `True` gets no behaviour change at all — the deprecation note lives in `settings_service`, not next to the constant.
- **Fix:** delete `config.py:699-700`.

### [X-9] Per-component log-level override mechanism is inert — **Minor**

- **Definitions:** `config.py:899` `DEFAULT_LOG_LEVEL_OVERRIDES: dict[str, str] = {}` and `config.py:908-928` `AVAILABLE_LOG_COMPONENTS` (19 entries, documented as *"Stable component logger identifiers used for per-component overrides"*).
- **Consumer:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\logging_service.py:145-146`
  ```python
  component_override = config.DEFAULT_LOG_LEVEL_OVERRIDES.get(component_name)
  return _resolve_level(level_name or component_override or config.DEFAULT_LOG_LEVEL)
  ```
- **How it drifted:** `DEFAULT_LOG_LEVEL_OVERRIDES` is a literal empty dict, never populated at import or runtime (confirmed: no `global`, no mutation, no settings key feeds it). `component_override` is therefore always `None` and the whole branch is unreachable. `AVAILABLE_LOG_COMPONENTS` — the list the overrides were meant to be keyed by — has no reference anywhere in `src`; its only consumer is the assertion at `tests/test_config_contract.py:63-64`.
- **Bug this causes:** the app looks like it supports per-component log levels and does not. Anyone debugging one noisy subsystem will find the knob and find it does nothing.
- **Fix:** either wire `DEFAULT_LOG_LEVEL_OVERRIDES` to a settings key, or delete both constants and the dead branch at `logging_service.py:145`.

_Checked and found clean:_ 154 constants scanned; the only names unreferenced outside `config.py` are the six that `config.py` itself consumes internally (`APP_PACKAGE_ROOT`, `APP_SOURCE_ROOT`, `APP_DATA_DIR_ENVIRONMENT_VARIABLE`, and the three `DEFAULT_AI_CHUNKING_*_WINDOW_SIZE` values folded into the two window-size maps at `config.py:762-773`) plus `DEFAULT_SCENE_AMBIENCE_GENERATION_ENABLED` above. No artifact filename literal is hardcoded anywhere outside `config.py` — all 18 names are reached via `config.*`. No numeric literal duplicates a config constant (`0.08`, `2.5`, `14.0`, `0.80`, `512` all appear only at their definitions). `WORKFLOW_OPERATION_ORDER` has an `_OPERATION_ARTIFACT_FILE_NAMES` entry for all ten kinds (`operation_runtime_service.py:50-104`); `OPERATION_STAGE_BY_KIND` deliberately omits `"extraction"` and the reader handles it explicitly at `project_workspace_service.py:587`.

---

## 7. Mutable defaults / shared mutable state

**None found.** An AST sweep over every `.py` in `src` returned zero mutable default arguments (`[]`, `{}`, `set()`, `list()`, `dict()`) and zero module-level `dict`/`list`/`set` constants that are mutated at runtime (subscript assignment or `append`/`update`/`pop`/`clear`/`setdefault`/`add`/`remove`/`insert`/`sort`). The single `global` statement in the tree is `ui_state_service.py:2398` (`_BASE_FONT_FAMILY`, `_BASE_FONT_POINT_SIZE`), which rebinds two immutable scalars. Shared config dicts such as `config.AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY` and `config.OPERATION_STAGE_BY_KIND` are read-only at every call site, and `character_discovery_service._first_model` returns `deepcopy(...)` (`character_voices_service.py:1252`) rather than a shared reference.

---

## 8. Dead code

### [X-10] Four unreferenced UI page methods (~94 lines) — **Minor**

Each is defined once and referenced nowhere in `src` or `tests` (verified by name grep across both trees):

- `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\ui\pages\speech_blocks_page.py:491` — `remove_speech_block_item` (27 lines)
- `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\ui\pages\character_voices_page.py:312` — `apply_selected_target` (25 lines)
- `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\ui\pages\narator_voice_page.py:357` — `apply_selected_profile` (21 lines)
- `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\ui\pages\speech_blocks_page.py:469` — `insert_speech_block_item` (21 lines)

**Why this misleads:** the two `speech_blocks_page` methods are documented as incremental-update paths — *"Insert one Speech Block row without rebuilding the whole page"* (`:471`) — implying the page supports incremental row updates. It does not; the controller always does a full rebuild. `apply_selected_target` and `apply_selected_profile` are the surviving halves of the same refactor: both pages still expose the paired getters `current_target_id` (`character_voices_page.py:338`) and `current_profile_id` (`narator_voice_page.py:379`), which *are* called, so the setters read as live API. They also mutate private state (`_edit_mode`, `_dirty`, `_original_payload`) that is now owned entirely by the controllers — calling them today would desynchronize the page from its controller.

**Fix:** delete all four.

_Scan detail:_ every `FunctionDef` / `AsyncFunctionDef` / `ClassDef` in `src` of 20+ lines was checked for a single name occurrence across `src` + `tests`; these four were the only hits. No dead classes, no dead service-layer functions.
