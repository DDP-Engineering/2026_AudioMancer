# Component Review — Platform / Settings / UI Infrastructure

_Reviewed 2026-08-02. Files: `src/audiomancer/config.py`, `services/settings_service.py`, `services/ui_state_service.py`, `services/ui_theme_service.py`, `services/ui_scroll_service.py`, `services/url_service.py`, `services/logging_service.py`, `services/time_service.py`, `ui/pages/settings_page.py`, `ui/controllers/settings_ui_controller.py`, plus `settings.json` / `settings.example.json`. Total ~5,570 lines._

## Summary

The component is in good shape overall: the localization catalog is provably consistent (977 keys per language, no missing keys, no placeholder mismatches, no untranslated leftovers), settings writes are genuinely atomic, and theme normalization is careful. The defects found are concentrated in two places: startup path resolution in `config.py`, and the read side of `settings_service.load_settings`. Findings: **2 Critical** (one credential exposure in git history, one import-time crash for a plausible install layout), **3 Major** (settings file destroyed on a BOM/typo, unhandled decode/IO error at startup, custom theme selection silently overwritten), **4 Minor**.

## Findings

### [PS-1] Live OpenAI API key committed to git history — **Critical**

- **File:** `04_Software/AudioMancer/settings.json` (untracked at HEAD, present in 13 reachable commits, e.g. `c52d51d`, `919274b`, `ee81887`, `84310fa`)
- **What:** `settings.json` is gitignored today (`.gitignore:81`) and is not tracked at HEAD, but it was tracked earlier and those blobs are still reachable. Each of those revisions contains a real, non-placeholder OpenAI project key:

```json
"api_key": "sk-proj-249lVduNgRap_YZZ…<redacted>…Dyv5WMA "
```

  (also `"api_key": "lm-studio"` in the local profiles, which is harmless). Retrievable with a one-line `git show <commit>:04_Software/AudioMancer/settings.json`. The repository has a push remote (`origin ssh://…@192.168.1.15:2222/dpasare/2026_AudioMancer.git`), so the key exists outside this machine.
- **Why it matters:** Anyone with read access to the repository — now or after any future clone, mirror, or open-sourcing — can bill against that OpenAI account. Removing the file from HEAD did not remove the secret.
- **Fix:** Revoke/rotate the key at the OpenAI dashboard first (that is the only step that actually closes the exposure); history rewriting is optional cleanup afterwards. The current working-tree `settings.json` also holds `"tts_runtime_api_key": "voiceweaver-dev-key"` — it is correctly ignored, but keep it that way.

### [PS-2] `APP_SOURCE_ROOT.parents[1]` raises `IndexError` at import for a one-level install root — **Critical**

- **File:** `src/audiomancer/config.py:348-353`
- **What:** Two module-level constants index the second parent of the resolved source/runtime root unconditionally:

```python
APP_HELP_SOURCE_INDEX_PATHS = {
    "en": APP_SOURCE_ROOT.parents[1] / "05_SoftwareDocu" / "UserGuide" / "index.html",
    "ro": APP_SOURCE_ROOT.parents[1] / "05_SoftwareDocu" / "UserGuide_ro" / "index.html",
}
APP_HELP_SOURCE_INDEX_PATH = APP_SOURCE_ROOT.parents[1] / "05_SoftwareDocu" / "UserGuide" / "index.html"
```

  In a frozen build `_source_tree_root_from_package()` returns `None`, so `APP_SOURCE_ROOT` falls back to `resolve_app_runtime_root()` = the executable folder (`config.py:320`). `Path("D:/AudioMancer").parents` has length 1, so `parents[1]` raises `IndexError: 1` (verified). Same for `/audiomancer` on POSIX. `C:\Program Files\AudioMancer` and `/opt/audiomancer` have depth 2 and survive.
- **Why it matters:** A portable build unzipped to `D:\AudioMancer` or `C:\AudioMancer` — the most natural place for a portable app — dies with an unhandled `IndexError` while importing `config`. This happens on `from . import config` in `app.py`, i.e. **before** `initialize_logging()` runs, so there is no log file, no console diagnostic beyond the traceback, and no window. The app simply never starts.
- **Fix:** Resolve the parent defensively, e.g. a tiny helper `_ancestor(path, 2)` that returns `path.parents[min(2, len(path.parents)) - 1]`, or compute the docs root only from the source-tree branch (`_source_tree_root_from_package(...)`) and leave the dict empty when that is `None`. `misc_ui_controller` already treats these paths as an optional dev fallback, so an absent/parent-less value is harmless.

### [PS-3] A malformed settings file (including a plain UTF-8 BOM) destroys all persisted settings — **Major**

- **File:** `src/audiomancer/services/settings_service.py:836-845`
- **What:**

```python
try:
    persisted_payload = json.loads(settings_path.read_text(encoding="utf-8"))
except json.JSONDecodeError:
    default_settings = build_default_settings()
    _write_settings_file(default_settings)
    _SETTINGS_LOGGER.warning(
        f"Replaced invalid JSON settings file at {settings_path} with defaults.",
        …
    )
    return default_settings
```

  The previous content is overwritten in place with factory defaults, with no backup and no operator prompt — only a `WARNING` line in a log the operator is unlikely to read. `encoding="utf-8"` (not `utf-8-sig`) means a byte-order mark is fed to `json.loads` as `﻿`, which raises `JSONDecodeError` — so a *perfectly valid* settings file merely saved with a BOM triggers the wipe. Windows PowerShell 5.1 `>` / `Out-File` and several editors write a BOM by default.
- **Why it matters:** The operator hand-edits `settings.json` (the shipped `settings.example.json` explicitly instructs them to: _"Copy to settings.json and fill in your own endpoints, api keys…"_), saves it with a BOM or leaves one trailing comma, restarts, and loses all five LLM profiles, both API keys, the TTS discovery cache, custom themes, and every appearance preference. Nothing on screen says so.
- **Fix:** Read with `encoding="utf-8-sig"` (fixes the BOM case entirely), and in the decode-error branch rename the bad file (`settings_path.with_suffix(".corrupt.json")`) before writing defaults, so the operator can recover their profiles.

### [PS-4] `load_settings` only catches `JSONDecodeError`; a decode or IO error is an unhandled startup crash — **Major**

- **File:** `src/audiomancer/services/settings_service.py:836-838`
- **What:** `settings_path.read_text(encoding="utf-8")` can raise `UnicodeDecodeError` (a `ValueError`, not a `JSONDecodeError`) or `OSError`/`PermissionError`; neither is caught. The sibling helper shows the intended breadth:

```python
    try:
        bundled_payload = json.loads(default_settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return build_default_settings(), "built-in defaults"
```

  `app.main()` calls `load_settings()` inside a `try` that only logs and re-raises (`app.py:97-102`), so the exception terminates the process.
- **Why it matters:** A settings file saved as UTF-16 ("Unicode" in Notepad) or as ANSI containing a non-ASCII theme name, or a file transiently locked by a sync client / left unreadable after an ACL change, means AudioMancer refuses to start at all, with a traceback instead of a message. The self-healing path that exists for malformed JSON never gets a chance to run.
- **Fix:** Widen the existing `except` to `(OSError, json.JSONDecodeError, ValueError)`, matching `_seed_settings_payload`.

### [PS-5] Settings page silently rewrites a persisted custom `ui_theme_id` to the default — **Major**

- **File:** `src/audiomancer/ui/pages/settings_page.py:97-99`, `:169-172`, `:251`
- **What:** The theme combo is populated from built-in themes only, and the selection is written straight back on save:

```python
for theme_payload in ui_theme_service.built_in_themes():
    self._theme_combo.addItem(str(theme_payload["display_name"]), str(theme_payload["theme_id"]))
…
index = self._theme_combo.findData(theme_id)
if index < 0:
    index = self._theme_combo.findData(config.DEFAULT_UI_THEME_ID)
self._theme_combo.setCurrentIndex(max(0, index))
…
merged_settings["ui_theme_id"] = str(self._theme_combo.currentData() or config.DEFAULT_UI_THEME_ID)
```

  A custom `ui_theme_id` is a fully supported persisted value: `_validate_settings_internal` validates it against `merged_theme_catalog(...)` (built-ins **plus** `ui_themes`), `ui_state_service.apply_ui_settings` resolves it through `theme_by_id(...)` with the custom collection, and the working-tree `settings.json` does carry a custom theme in `ui_themes`. But `findData` cannot find it in the combo, so `_select_theme` silently lands on `audiomancer_dark`, and the next Apply/OK persists that.
- **Why it matters:** An operator running a custom theme opens Settings only to bump the scroll steps, presses OK, and their theme is replaced by the default with no warning and no undo — the `ui_themes` entry is still on disk but the selection is gone.
- **Fix:** Populate the combo from `ui_theme_service.merged_theme_catalog(settings_payload.get("ui_themes", []))` in `load_settings()`, or, if custom themes are truly unsupported now, leave `ui_theme_id` untouched in `build_settings()` when the persisted id is not one of the built-ins.

### [PS-6] `build_default_settings()` contradicts the `config` defaults it is supposed to seed — **Minor**

- **File:** `src/audiomancer/services/settings_service.py:745-748`
- **What:**

```python
        "default_ai_chunking_strategy": "scene",
        …
        "play_completion_beep": True,
```

  while `config.py:572` declares `DEFAULT_PLAY_COMPLETION_BEEP = False` and `config.py:728` declares `DEFAULT_AI_CHUNKING_STRATEGY = "paragraph"`. Both config constants are live: the settings page initializes its checkbox from `config.DEFAULT_PLAY_COMPLETION_BEEP` (`settings_page.py:76`), `completion_beep_enabled_from_settings` falls back to it, and `DEFAULT_AI_CHUNKING_STRATEGY` is the fallback in `ai_chunking_service.py:534/539`, `text_chunking_state_service.py`, and `ai_settings_page.py:290`.
- **Why it matters:** The knowledge contract states the completion beep default is "staying silent", but a fresh install writes `play_completion_beep: true` and beeps. Two sources of truth for the same default will drift again the next time one of them is edited.
- **Fix:** Seed from the constants — `config.DEFAULT_PLAY_COMPLETION_BEEP` and `config.DEFAULT_AI_CHUNKING_STRATEGY` — or change the constants and let the seeds reference them; do not keep both.

### [PS-7] Startup theme is applied without the persisted font-size steps — **Minor**

- **File:** `src/audiomancer/app.py:82` (call site of `ui_state_service.apply_theme`, `ui_state_service.py:2779-2810`)
- **What:**

```python
        ui_state_service.apply_theme(application, startup_theme, None)
```

  `apply_theme` derives the application point size from `ui_font_size_step` / `text_font_size_step`, and falls back to `config.DEFAULT_UI_FONT_SIZE_STEP` ("normal") when they are omitted. They are omitted here, even though `settings_payload` was loaded two statements earlier and may hold `"large"` (the working-tree `settings.json` does). The comment directly above this line states the whole purpose of the early call is "every widget built by MainWindow inherits the themed font".
- **Why it matters:** The one operator-chosen quantity the pre-construction call exists to propagate — font size — is the one it drops. `MainWindow.__init__` re-applies correctly at line 228, so the end state is right, but the widgets are built at the wrong size first, which is exactly the situation the comment says `setFont()` does not fully recover from.
- **Fix:** Pass the two steps from `settings_payload`, or simply call `ui_state_service.apply_ui_settings`-equivalent argument set here.

### [PS-8] Interface-language combo is not localized and round-trips through `currentText()` — **Minor**

- **File:** `src/audiomancer/ui/pages/settings_page.py:69-70`, `:250`
- **What:**

```python
        self._language_combo.addItems(config.SUPPORTED_LANGUAGES)
…
        merged_settings["language"] = self._language_combo.currentText()
```

  The items carry no `itemData`, so the visible text *is* the persisted value: the operator sees "en" / "ro". `apply_language()` relabels the theme and font-size combos in place but skips this one, although `language.en` / `language.ro` ("English"/"Engleza", "Romanian"/"Romana") exist in the catalog. The documented contract says language codes should "keep language-neutral item data while their combo labels are replaced in place".
- **Why it matters:** Cosmetically wrong today; actively broken the moment someone adds the missing relabel line, because `currentText()` would then persist "English" and `validate_settings` would silently reset the language to `en`.
- **Fix:** `addItem(translate(f"language.{code}", lang), code)` for each supported code, read with `currentData()`, and relabel in `apply_language()` like the other combos.

### [PS-9] `settings.example.json` uses `null` where the loader requires a string — **Minor**

- **File:** `04_Software/AudioMancer/settings.example.json:18`, `:39`
- **What:** Both example profiles declare `"discovered_model_name": null`, but `_validate_llm_profile` treats `discovered_model_name` as an optional **string** field (`settings_service.py:194-235`): a non-`str` is replaced with `""` and logged as a repair.
- **Why it matters:** Every operator who follows the example file's own instruction to copy it to `settings.json` gets a "repair" pass and a rewritten settings file on first launch, plus warning lines that make a clean install look damaged. The example also omits `ui_theme_id`, `ui_themes`, and `default_ai_chunking_context_mode` (those are correctly filled from defaults, so only the `null` is a genuine schema mismatch).
- **Fix:** Change both to `"discovered_model_name": ""`.

## Duplication

- **Two parallel colour-label key families in the catalog.** `settings.theme_color_window_background` … `settings.theme_color_disabled` (`ui_state_service.py:280-289`) and `settings.theme_color.window_background` … `settings.theme_color.disabled` (`:290-299`) are the same 10 roles with the same text, duplicated in both languages — 40 dead entries. Neither family is referenced anywhere in `src/`.
- **Theme-editor strings left behind after the feature was removed.** `settings.theme_new`, `settings.theme_duplicate`, `settings.theme_delete`, `settings.theme_import`, `settings.theme_export`, `settings.theme_import_failed`, `settings.theme_export_failed`, `settings.theme_import_too_large`, `settings.theme_imported`, `settings.theme_exported`, `settings.theme_name`, `settings.theme_font_family`, `settings.theme_text_font_family`, `settings.theme_colors`, `settings.theme_builtin_readonly`, `settings.theme_preview_status`, and the whole `settings.scale.*` family are defined but never looked up (the page docstring says "Colour/custom-theme editing has been intentionally removed"). Same for `settings_ui_controller.MAX_THEME_IMPORT_BYTES` / `THEME_JSON_FILTER`, and for `ui_theme_service.duplicate_theme` / `import_theme_payload` / `export_theme_payload`, which are exercised only by tests.
- **Latent trap if theme editing is re-wired:** `duplicate_theme` (`ui_theme_service.py:541`) assigns `_theme_id_from_name(display_name)` without the `_unique_theme_id(...)` guard that `import_theme_payload` uses, so duplicating "Classic Light" as "Classic Light" yields `theme_id = "classic_light"`, which `normalize_theme_collection` then discards as a built-in collision — the new theme would vanish on save. Worth fixing at the same time as any re-wiring, not before.
- `ui_theme_service.default_theme_id()` returns the literal `"audiomancer_dark"` instead of `config.DEFAULT_UI_THEME_ID`; same value today, second source of truth.

## Verified-clean notes

- **Localization catalog (the largest risk surface): clean.** Programmatic check of `_UI_STRINGS`: 977 keys in `en` and 977 in `ro`, zero missing, zero extra, zero duplicate literal keys inside either block, zero `str.format` placeholder mismatches between the two languages, and zero multi-word strings left identical in Romanian (no copy-paste leftovers). Every statically-written `translate("literal")` key across `src/audiomancer` exists in the catalog. `translate()` degrades key → English → raw key and cannot raise `KeyError`; `get_ui_strings` and `apply_language` use the same guarded language resolution.
- **Settings writes cannot leave an empty or truncated file.** `_write_settings_file` → `write_json_atomic` → `write_text_atomic` serializes the full payload *before* touching disk, writes to a same-directory `mkstemp` file, `flush()` + `os.fsync()`, then `os.replace()`, and unlinks the temp file on `OSError`. No partial-write path.
- **Dialog semantics match the contract.** Cancel → `self._settings_dialog.close` only, and `show_settings_dialog` re-runs `load_settings(payload)` on every open, so edits are genuinely discarded; Apply → `_persist_settings_from_dialog(close_dialog=False)`; OK → `close_dialog=True` (`main_window.py:1106-1112`). All three save call sites merge into the live `window._settings_payload`, so no page can blank another page's fields.
- **`url_service` never launches anything** — it only joins/strips REST paths; there is no `open`/`webbrowser`/`QDesktopServices` call in it, so scheme validation is not applicable. Base URLs that reach it are pre-validated by `_is_valid_http_url` (`http`/`https` + netloc) in `validate_settings`. `join_endpoint_url`'s `endswith` checks are segment-safe (`/v1/xspeech` does not match `/speech`).
- **Logging does not leak secrets.** `_safe_value` renders any `dict` as `dict(keys=[…])`, so the traced `save_settings`/`validate_settings`/`apply_ui_settings` calls record key names only, never API-key values; strings are `repr`-truncated at 240 chars. Per-run file name includes the pid as documented, retention cleanup is best-effort and skips unlistable/unremovable entries, and file-handler creation failure degrades to console-only instead of raising.
- **Theme normalization and clamping.** `_normalize_colors` fills missing roles from `classic_light` and rejects non-`#RRGGBB`; `apply_theme` clamps the resolved point size into `[MIN_FONT_POINT_SIZE, MAX_FONT_POINT_SIZE]` before re-validating in `build_theme_stylesheet`, so the internal `validate_theme_payload` call cannot raise on its own output. `_BUILT_IN_THEMES` order and index-0 fallback are intact, and all 11 built-in ids have `settings.theme_name.<id>` entries in both languages.
- **Mutable module-level defaults are copied, not shared.** `_LLM_PROFILE_DEFAULTS` (contains a mutable `[]`) is only ever read or `copy.deepcopy`-ed; `build_default_settings()` builds a fresh dict per call and `_validate_settings_internal` deep-copies each default it injects; `built_in_themes()` returns deep copies.
- **Scroll filter** clamps the step count on both the setter and the apply path, ignores Ctrl+wheel (zoom), and reuses a single application-wide filter instance via the `QApplication` attribute.
- Doc drift, not a code defect: `.agentic/knowledge/Platform_Settings_UI.md` lists `tests/test_config_hygiene.py`, which does not exist.
