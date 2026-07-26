#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ui_state_service.py
@brief Runtime UI-state helpers for AudioMancer.
@details Applies runtime UI language and text-size settings to the running Qt
         application through one centralized string catalog, scale mapping, and
         theme runtime adapter, and resolves settings-backed runtime preferences
         such as the operator completion beep.
@author Eng. Dan Dumitru Pasare
@date 2026-04-21
@version 0.59.0
"""

# ruff: noqa: E501

# IMPORTS

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from .. import config
from . import ui_theme_service
from .logging_service import get_component_logger, trace_function

# CONSTANTS

# @brief Component logger used by runtime UI language and scale helpers.
_UI_STATE_LOGGER = get_component_logger("ui_state")
# @brief Scale-factor mapping applied to the base application font size.
_UI_SCALE_FACTORS = {
    "very_small": 0.82,
    "small": 0.91,
    "normal": 1.0,
    "large": 1.12,
    "very_large": 1.24,
}

# @brief Multiplier applied to the base font point size for each operator font-size step.
FONT_SIZE_STEP_FACTORS = {
    "extra_small": 0.80,
    "small": 0.90,
    "medium": 0.95,
    "normal": 1.00,
    "large": 1.15,
    "very_large": 1.30,
    "huge": 1.50,
}

# @brief Dynamic Qt property used by read-only operator status editors.
CONTROL_TEXT_FONT_ROLE_PROPERTY = "audiomancerFontRole"
# @brief Dynamic Qt property value for editors that should use the UI font.
CONTROL_TEXT_FONT_ROLE_VALUE = "ui_controls"

# @brief Default runtime UI language used as the catalog fallback.
_DEFAULT_LANGUAGE = config.DEFAULT_LANGUAGE
# @brief Lazily captured unscaled application font size used as the scaling baseline.
_BASE_FONT_POINT_SIZE: float | None = None
# @brief Lazily captured platform-default application font family.
_BASE_FONT_FAMILY: str | None = None

# @brief Centralized runtime UI string catalog keyed by language and stable identifier.
_UI_STRINGS = {
    "en": {
        "window_title.main": "AudioMancer | Transform written words into real audio experience!",
        "toolbar.new_project": "New Project",
        "toolbar.open_project": "Open Project",
        "toolbar.settings": "Settings",
        "toolbar.ai_settings": "AI Settings",
        "toolbar.tts_settings": "TTS Settings",
        "toolbar.help": "Help",
        "toolbar.about": "About",
        "dialog.settings_title": "Settings",
        "dialog.theme_name_title": "Theme Name",
        "dialog.theme_name_prompt": "Enter the theme name:",
        "dialog.theme_delete_title": "Delete Theme",
        "dialog.theme_delete_message": "Delete this custom theme? Built-in themes cannot be deleted.",
        "dialog.theme_import_title": "Import Theme",
        "dialog.theme_export_title": "Export Theme",
        "dialog.theme_import_error_title": "Theme Import Error",
        "dialog.theme_export_error_title": "Theme Export Error",
        "dialog.ai_settings_title": "AI Settings",
        "dialog.tts_settings_title": "TTS Settings",
        "dialog.about_title": "About",
        "dialog.new_project_title": "New Project",
        "dialog.open_project_title": "Open Project",
        "dialog.select_project_parent_title": "Select Project Parent Folder",
        "dialog.select_source_title": "Select Source File",
        "dialog.select_source_filter": "Supported source files (*.txt *.pdf *.rtf *.docx *.odt *.md *.epub)",
        "dialog.export_title": "Export Project Artifact",
        "dialog.export_filter_txt": "Text Files (*.txt)",
        "dialog.export_filter_markdown": "Markdown Files (*.md)",
        "dialog.snapshot_title": "Export Project ZIP Snapshot",
        "dialog.snapshot_filter_zip": "ZIP Archives (*.zip)",
        "dialog.project_error_title": "Project Error",
        "dialog.project_repair_title": "Repair Project",
        "dialog.confirm_extraction_rerun_title": "Confirm Extraction Rerun",
        "dialog.confirm_cleanup_rerun_title": "Confirm Cleanup Rerun",
        "dialog.confirm_cleanup_mode_switch_title": "Change Cleanup Mode",
        "dialog.confirm_cleanup_reset_title": "Reset Cleanup",
        "dialog.confirm_chunking_rerun_title": "Confirm Chunking Rerun",
        "dialog.confirm_ai_chunking_rerun_title": "Confirm AI Chunking Rerun",
        "dialog.confirm_cleaned_text_edit_title": "Confirm Cleaned Text Edit",
        "dialog.confirm_chunk_edit_title": "Confirm Chunk Edit",
        "dialog.confirm_chunk_insert_title": "Confirm Chunk Insert",
        "dialog.confirm_chunk_delete_title": "Confirm Chunk Delete",
        "dialog.confirm_ai_cleanup_title": "Start AI-Assisted Cleanup",
        "dialog.confirm_ai_cleanup_rerun_title": "Confirm AI Cleanup Rerun",
        "dialog.ai_cleanup_extra_prompt_title": "AI Cleanup Instructions",
        "dialog.ai_cleanup_extra_prompt_label": (
            "Optional extra cleanup rules to add to the AI prompt. Leave empty to use the standard prompt."
        ),
        "dialog.ai_chunking_extra_prompt_title": "AI Chunking Instructions",
        "dialog.ai_chunking_extra_prompt_label": (
            "Optional extra chunking rules to add to the AI prompt. Leave empty to use the standard prompt."
        ),
        "dialog.ai_translation_extra_prompt_title": "AI Translation Instructions",
        "dialog.ai_translation_extra_prompt_label": (
            "Optional extra translation rules to add to the AI prompt. Leave empty to use the standard prompt."
        ),
        "dialog.character_discovery_extra_prompt_title": "Character Discovery Instructions",
        "dialog.character_discovery_extra_prompt_label": (
            "Optional extra Character Discovery rules to add to the AI prompt. Leave empty to use the standard prompt."
        ),
        "dialog.narator_profile_generation_extra_prompt_title": "Narator Profile Instructions",
        "dialog.narator_profile_generation_extra_prompt_label": (
            "Optional extra Narator profile rules to add to the AI prompt. Leave empty to use the standard prompt."
        ),
        "dialog.speech_blocks_extra_prompt_title": "Speech Blocks Instructions",
        "dialog.speech_blocks_extra_prompt_label": (
            "Optional extra Speech Blocks rules to add to the AI prompt. Leave empty to use the standard prompt."
        ),
        "dialog.confirm_project_options_title": "Lock Project Options",
        "dialog.operation_progress_title": "{operation_name} In Progress",
        "dialog.operation_progress_cancel": "Cancel Operation",
        "dialog.operation_progress_token_usage": "Input tokens: {input_tokens} | Output tokens: {output_tokens} | Total: {total_tokens}",
        "dialog.operation_progress_token_usage_unavailable": "Token usage was not reported by the backend.",
        "about.subtitle": "Transform written words into real audio experience!",
        "about.version": "Version: {version}",
        "about.license": "License",
        "about.details": "Eng. Dipl. Dan Dumitru Pasare\npasaredan1979@gmail.com",
        "dialog.help_error_title": "Help",
        "help.missing_file": "The offline help file was not found. Reinstall AudioMancer or open the UserGuide folder from the documentation package.",
        "help.open_failed": "AudioMancer could not open the help file:\n{path}",
        "status.stop_ai": "Stop AI",
        "status.stage_prefix": "Stage",
        "status.idle": "idle",
        "status.saved_settings": "Settings saved.",
        "status.saved_ai_settings": "AI settings saved.",
        "status.saved_tts_settings": "TTS settings saved.",
        "status.project_created": "Project created.",
        "status.project_opened": "Project opened.",
        "status.project_repaired": "Project repaired and opened.",
        "status.project_options_locked": "Project audiobook options locked.",
        "status.source_imported": "Source file imported.",
        "status.project_exported": "Export saved.",
        "status.project_snapshot_exported": "Project ZIP snapshot saved.",
        "status.project_snapshot_cancelled": "Project ZIP snapshot export cancelled.",
        "status.text_extracted": "Text extracted.",
        "status.text_cleaned": "Text cleaned.",
        "status.cleaned_text_saved": "Cleaned text saved.",
        "status.text_ai_cleaned": "AI-assisted cleanup completed.",
        "status.ai_cleanup_spacing_applied": "AI cleanup spacing applied.",
        "status.cleanup_reset": "Cleanup and all downstream results were reset.",
        "status.text_chunked": "Text chunked.",
        "status.text_ai_chunked": "Text chunked with AI.",
        "status.chunk_saved": "Chunk saved.",
        "status.chunk_inserted": "Chunk inserted.",
        "status.chunk_deleted": "Chunk deleted.",
        "status.text_translated": "Text translated.",
        "status.translation_reset": "Translation reset.",
        "status.characters_discovered": "Character discovery completed.",
        "status.speech_blocks_generated": "Speech Blocks generated.",
        "status.speech_blocks_reset": "Speech Blocks reset.",
        "status.speech_blocks_approved_all": "All Speech Blocks approved.",
        "status.speech_block_saved": "Speech Block saved.",
        "status.speech_block_approved": "Speech Block approved.",
        "status.speech_block_unapproved": "Speech Block unapproved.",
        "status.speech_block_inserted": "Speech Block inserted.",
        "status.speech_block_deleted": "Speech Block deleted.",
        "status.speech_blocks_resplit": "Selected chunk re-split completed.",
        "status.audio_blocks_generated": "Audio Blocks generated.",
        "status.audio_blocks_reset": "Audio Blocks reset.",
        "status.audio_blocks_approved_all": "All generated audio blocks approved.",
        "status.audio_block_approved": "Audio block approved.",
        "status.audio_block_unapproved": "Audio block unapproved.",
        "status.audio_block_regenerated": "Audio block regenerated.",
        "status.character_discovery_reset": "Character discovery reset.",
        "status.character_added": "Character added.",
        "status.character_saved": "Character changes saved.",
        "status.character_deleted": "Character deleted.",
        "status.theme_imported": "Theme imported.",
        "status.theme_exported": "Theme exported.",
        "status.theme_deleted": "Theme deleted.",
        "status.operation_cancelled": "Operation cancelled.",
        "sidebar.home": "Home / Project",
        "sidebar.text_cleanup": "Text Cleanup",
        "sidebar.text_chunking": "Text Chunking",
        "sidebar.ai_translation": "AI Translation",
        "sidebar.characters": "Characters",
        "sidebar.narator_voice": "Narator Voice",
        "sidebar.character_voices": "Character Voices",
        "sidebar.speech_blocks": "Speech Blocks",
        "sidebar.audio_blocks": "Audio Blocks",
        "sidebar.audio_assembly": "Audio Assembly",
        "settings.language": "Language",
        "settings.play_beep": "Play completion beep",
        "settings.scroll_steps": "Scroll steps",
        "settings.cancel": "Cancel",
        "settings.apply": "Apply",
        "settings.ok": "OK",
        "settings.save": "OK",
        "settings.scale.very_small": "Very Small",
        "settings.scale.small": "Small",
        "settings.scale.normal": "Normal",
        "settings.scale.large": "Large",
        "settings.scale.very_large": "Very Large",
        "settings.theme_group": "Theme",
        "settings.theme": "Theme",
        "settings.theme_new": "New",
        "settings.theme_duplicate": "Duplicate",
        "settings.theme_delete": "Delete",
        "settings.theme_import": "Import Theme",
        "settings.theme_export": "Export Theme",
        "settings.theme_import_failed": "Theme import failed.",
        "settings.theme_export_failed": "Theme export failed.",
        "settings.theme_import_too_large": "Theme file is larger than the 256 KB limit.",
        "settings.theme_imported": "Imported theme: {theme_name}.",
        "settings.theme_exported": "Theme exported to {path}.",
        "settings.theme_name": "Name",
        "settings.theme_font_family": "UI font family",
        "settings.theme_text_font_family": "Text font family",
        "settings.theme_font_size": "UI font size",
        "settings.theme_text_font_size": "Text font size",
        "settings.theme_colors": "Colors",
        "settings.theme_preview": "Preview",
        "settings.theme_preview_label": "Sample text",
        "settings.theme_preview_input": "Sample text window",
        "settings.theme_preview_button": "Sample button",
        "settings.theme_preview_status": "Ready",
        "settings.theme_builtin_readonly": "Built-in themes are read-only.",
        "settings.theme_color_window_background": "Window background",
        "settings.theme_color_panel_background": "Panel background",
        "settings.theme_color_text_primary": "Primary text",
        "settings.theme_color_text_muted": "Muted text",
        "settings.theme_color_accent": "Accent",
        "settings.theme_color_border": "Border",
        "settings.theme_color_success": "Success",
        "settings.theme_color_warning": "Warning",
        "settings.theme_color_danger": "Danger",
        "settings.theme_color_disabled": "Disabled",
        "settings.theme_color.window_background": "Window background",
        "settings.theme_color.panel_background": "Panel background",
        "settings.theme_color.text_primary": "Primary text",
        "settings.theme_color.text_muted": "Muted text",
        "settings.theme_color.accent": "Accent",
        "settings.theme_color.border": "Border",
        "settings.theme_color.success": "Success",
        "settings.theme_color.warning": "Warning",
        "settings.theme_color.danger": "Danger",
        "settings.theme_color.disabled": "Disabled",
        "ai_settings.title": "AI Settings",
        "ai_settings.profile_name": "Profile Name",
        "ai_settings.profile_enabled": "Profile enabled",
        "ai_settings.backend_kind": "Backend Kind",
        "ai_settings.base_url": "Base URL",
        "ai_settings.api_key": "API Key",
        "ai_settings.model_name": "Model Name",
        "ai_settings.context_window": "Context Window",
        "ai_settings.max_output_tokens": "Max Output Tokens",
        "ai_settings.timeout": "Timeout (s)",
        "ai_settings.temperature": "Temperature",
        "ai_settings.structured_output": "Structured output",
        "ai_settings.default_cleanup": "Default Cleanup Profile",
        "ai_settings.default_chunking": "Default Chunking Profile",
        "ai_settings.default_translation": "Default Translation Profile",
        "ai_settings.default_narrator_generation": "Default Narator Generation Profile",
        "ai_settings.default_speech_blocks": "Default Speech Blocks Profile",
        "ai_settings.default_strategy": "Default AI Chunking Strategy",
        "ai_settings.default_context_mode": "Chunking Context Mode",
        "ai_settings.context_mode_balanced": "Balanced",
        "ai_settings.context_mode_wide_scene": "Wide scene context",
        "ai_settings.context_mode_maximum": "Maximum context",
        "ai_settings.default_character": "Default Character Extraction Profile",
        "ai_settings.none": "(none)",
        "ai_settings.add_profile": "Add Profile",
        "ai_settings.remove_profile": "Remove Profile",
        "ai_settings.connect": "Connect",
        "ai_settings.cancel": "Cancel",
        "ai_settings.save": "Save",
        "ai_settings.ok": "OK",
        "ai_settings.no_profiles": "(no profiles)",
        "ai_settings.not_connected": "Not connected yet.",
        "ai_settings.connection_status": "Connection status",
        "ai_settings.connection_failed": "Connection failed",
        "ai_settings.popup_success_title": "Connection Successful",
        "ai_settings.popup_failure_title": "Connection Failed",
        "ai_settings.popup_discovered_models": "Discovered models",
        "ai_settings.popup_success_message": "Connection successful.",
        "ai_settings.popup_failure_message": "Connection failed.",
        "tts_settings.runtime_group": "VoiceWeaver Runtime",
        "tts_settings.base_url": "Base URL",
        "tts_settings.api_key": "API Key",
        "tts_settings.test_connection": "Test Connection",
        "tts_settings.models_group": "Discovered Models",
        "tts_settings.no_models": "No models discovered yet.",
        "tts_settings.active_model_marker": "active",
        "tts_settings.not_connected": "Not connected",
        "tts_settings.connected": "Connected",
        "tts_settings.connection_failed": "Connection failed",
        "tts_settings.plan_group": "Runtime Audio Limits",
        "tts_settings.voice_assignment": "Voice Assignment Mode",
        "tts_settings.voice_assignment_same_narrator": "Same narrator for whole book",
        "tts_settings.voice_assignment_with_characters": "Narrator + character voices",
        "tts_settings.preview_timeout": "Audio Preview Timeout (s)",
        "tts_settings.generation_timeout": "Audio Generation Timeout (s)",
        "tts_settings.preview_text_limit": "Preview Text Limit (chars)",
        "tts_settings.scene_ambience_enabled": "Scene Ambience Generation",
        "tts_settings.scene_ambience_placement": "Scene Ambience Placement",
        "tts_settings.scene_ambience_duration": "Scene Ambience Max Sequence Duration (s)",
        "tts_settings.scene_ambience_max_blocks": "Scene Ambience Max Blocks",
        "tts_settings.scene_ambience_guidance": "Scene Ambience Guidance",
        "tts_settings.scene_ambience_steps": "Scene Ambience Steps",
        "tts_settings.scene_ambience_seed": "Scene Ambience Seed",
        "tts_settings.scene_ambience_placement_none": "None",
        "tts_settings.scene_ambience_placement_openers_and_closers": "Openers and closers",
        "tts_settings.scene_ambience_placement_openers_closers_and_scene_changes": (
            "Openers, closers, and scene changes"
        ),
        "tts_settings.plan_no_project": "Runtime audio limits are global and apply to preview and generation.",
        "tts_settings.plan_probe_required": "Test the VoiceWeaver connection first so AudioMancer can verify the required Qwen3 TTS models.",
        "tts_settings.plan_missing_qwen": "The required Qwen3 TTS capabilities are missing: {missing_capabilities}.",
        "tts_settings.plan_ready": "The required Qwen3 base and Voice Designer capabilities are available.",
        "tts_settings.cancel": "Cancel",
        "tts_settings.save": "Save",
        "tts_settings.ok": "OK",
        "tts_settings.popup_success_title": "Connection Successful",
        "tts_settings.popup_failure_title": "Connection Failed",
        "tts_settings.popup_discovered_models": "Discovered models",
        "tts_settings.popup_success_message": "Connection successful.",
        "tts_settings.popup_failure_message": "Connection failed.",
        "text_cleanup.title": "Text Cleanup",
        "text_cleanup.extract": "Extract Text",
        "text_cleanup.clean": "Deterministic Cleanup",
        "text_cleanup.ai_profile": "AI Profile",
        "text_cleanup.ai_clean": "AI-Assisted Cleanup",
        "text_cleanup.reset": "Reset Cleanup",
        "text_cleanup.edit_cleaned": "Edit",
        "text_cleanup.save_cleaned": "Save",
        "text_cleanup.spacing_label": "Insert new line for:",
        "text_cleanup.spacing_heading": "Heading",
        "text_cleanup.spacing_separator": "Separator",
        "text_cleanup.spacing_noise": "Noise",
        "text_cleanup.spacing_header": "Header",
        "text_cleanup.spacing_footer": "Footer",
        "text_cleanup.apply_spacing": "Apply Spacing",
        "text_cleanup.find": "Find",
        "text_cleanup.find_next": "Find Next",
        "text_cleanup.find_title": "Find Text",
        "text_cleanup.find_prompt": "Text to find:",
        "text_cleanup.find_not_found": "No match found for '{search_text}'.",
        "text_cleanup.extracted_group": "Extracted Text Preview",
        "text_cleanup.cleaned_group": "Cleaned Text Preview",
        "text_cleanup.status_group": "Cleanup Status",
        "text_cleanup.extracted_note": "Raw extracted text will appear here after source processing.",
        "text_cleanup.cleaned_note": "Deterministic or AI-assisted cleanup output will appear here.",
        "text_cleanup.notes_text": "Import a source to begin text extraction.\nDeterministic cleanup and AI-assisted cleanup are not wired yet.",
        "text_cleanup.note_no_project": "Create or open a project to begin text extraction.",
        "text_cleanup.note_no_source": "Import a source file to begin extraction.",
        "text_cleanup.note_ready": "Extraction is ready to run for the current source file.",
        "text_cleanup.note_resume": "A previous extraction was not finalized. Press Extract Text to continue from progress {progress_current}/{progress_total}.",
        "text_cleanup.note_report_summary": "Extracted {word_count} words across {line_count} lines. Pages: {page_count}.",
        "text_cleanup.note_rerun_warning": "Running extraction again will replace the current extraction data and reset all following workflow data.",
        "text_cleanup.note_extraction_invalid": "Extraction data is incompatible. Use Reset Extraction before continuing.",
        "text_cleanup.note_cleanup_ready": "Deterministic cleanup is ready to run for the current extracted text.",
        "text_cleanup.note_cleanup_resume": "A previous cleanup was not finalized. Press Deterministic Cleanup to continue from progress {progress_current}/{progress_total}.",
        "text_cleanup.note_cleanup_summary": "Cleanup produced {paragraph_count} paragraphs, removed {removed_line_count} lines, and detected {chapter_count} chapter or scene headings.",
        "text_cleanup.note_page_break_metadata": "Page-break cleanup repaired {page_break_repair_count} continuation(s) and preserved {weak_boundary_count} low-confidence boundary/boundaries.",
        "text_cleanup.note_cleanup_rerun_warning": "Running deterministic cleanup again will replace the current cleanup data and reset chunking plus all following workflow data.",
        "text_cleanup.note_ai_cleanup_ready": "AI-assisted cleanup is ready for the current extracted text and selected AI profile.",
        "text_cleanup.note_ai_cleanup_continue": "Press AI-Assisted Cleanup to continue the validated source prefix with the current profile settings.",
        "text_cleanup.note_ai_cleanup_invalid": "The AI Cleanup document is invalid or belongs to another source. Use Reset Cleanup before starting again.",
        "text_cleanup.note_ai_cleanup_resume": "A previous AI-assisted cleanup was not finalized. Press AI-Assisted Cleanup to continue.",
        "text_cleanup.note_ai_cleanup_summary": "AI-assisted cleanup produced {paragraph_count} paragraphs, removed {removed_line_count} units, and detected {chapter_count} chapter or scene headings.",
        "text_cleanup.note_ai_cleanup_profile": "AI cleanup used profile: {profile_label}.",
        "text_cleanup.note_ai_cleanup_review_warning": "AI-assisted cleanup completed with validation warnings. Review the cleaned text before chunking.",
        "text_cleanup.note_ai_cleanup_rerun_warning": "Running AI-assisted cleanup again will replace the current cleanup data and reset chunking plus all following workflow data.",
        "text_chunking.title": "Text Chunking",
        "text_chunking.ai_profile": "AI Profile",
        "text_chunking.ai_strategy": "AI Strategy",
        "text_chunking.chunk": "Deterministic Chunking",
        "text_chunking.ai_chunk": "AI-Assisted Chunking",
        "text_chunking.cleaned_group": "Cleaned Text Reference",
        "text_chunking.chunk_list_group": "Chunk List",
        "text_chunking.selected_group": "Selected Chunk",
        "text_chunking.insert_chunk": "Insert",
        "text_chunking.delete_chunk": "Delete",
        "text_chunking.edit_chunk": "Edit",
        "text_chunking.save_chunk": "Save",
        "text_chunking.find": "Find",
        "text_chunking.find_next": "Find Next",
        "text_chunking.find_title": "Find Text",
        "text_chunking.find_prompt": "Text to find:",
        "text_chunking.find_not_found": "No match found for '{search_text}'.",
        "text_chunking.status_group": "Chunking Status",
        "text_chunking.cleaned_note": "Cleaned text will appear here and serve as the chunking reference.",
        "text_chunking.selected_note": "The full text of the selected chunk will appear here.",
        "text_chunking.notes_text": "Run cleanup before chunking.\nDeterministic chunking will populate the chunk list and selected preview.",
        "text_chunking.note_no_project": "Create or open a project to begin text chunking.",
        "text_chunking.note_no_source": "Import a source file and complete cleanup before chunking.",
        "text_chunking.note_missing_cleanup": "Run deterministic or AI-assisted cleanup before chunking.",
        "text_chunking.note_ready": "Deterministic chunking is ready to run for the current cleaned text.",
        "text_chunking.note_in_progress": "Deterministic chunking is in progress at {progress_current}/{progress_total}.",
        "text_chunking.note_resume": "A previous chunking run was not finalized. Press Deterministic Chunking to resume from the saved checkpoint.",
        "text_chunking.note_summary": "Chunking produced {chunk_count} chunks and detected {chapter_count} chapter or scene headings.",
        "text_chunking.note_rerun_warning": "Running deterministic chunking again will replace the current chunk data and reset translation plus all following workflow data.",
        "text_chunking.note_no_ai_profile": "Enable at least one AI profile in AI Settings to run AI-assisted chunking.",
        "text_chunking.note_ai_ready": "AI-assisted chunking is ready for the current cleaned text and selected AI profile.",
        "text_chunking.note_ai_in_progress": "AI-assisted chunking is in progress at {progress_current}/{progress_total} using the {strategy} strategy.",
        "text_chunking.note_ai_resume": "A previous AI-assisted chunking run was not finalized. Press AI-Assisted Chunking to resume from the saved checkpoint using the {strategy} strategy.",
        "text_chunking.note_ai_summary": "AI-assisted chunking produced {chunk_count} chunks, detected {chapter_count} chapter or scene headings, and used the {strategy} strategy.",
        "text_chunking.note_ai_rerun_warning": "Running AI-assisted chunking again will replace the current chunk data and reset translation plus all following workflow data.",
        "ai_translation.title": "AI Translation",
        "ai_translation.original_language": "Original Language",
        "ai_translation.target_language": "Target Language",
        "ai_translation.ai_profile": "AI Profile",
        "ai_translation.chunk_list_group": "Chunk List",
        "ai_translation.status_group": "Translation Status",
        "ai_translation.start": "Start Translation",
        "ai_translation.reset": "Reset Translation",
        "ai_translation.approve_all": "Approve All",
        "ai_translation.original_group": "Original Chunk",
        "ai_translation.translated_group": "Translated Chunk",
        "ai_translation.approved_chunks": "Approved chunks: 0/0",
        "ai_translation.retranslate": "Re-Translate Selected",
        "ai_translation.approve_selected": "Approve Selected",
        "ai_translation.source_note": "The source chunk selected from the list will appear here.",
        "ai_translation.translated_note": "Translated text for the selected chunk will appear here.",
        "ai_translation.note_no_project": "Create or open a project to begin AI translation.",
        "ai_translation.note_no_source": "Import a source file and complete chunking before translation.",
        "ai_translation.note_missing_chunking": "Run deterministic or AI-assisted chunking before translation.",
        "ai_translation.note_no_profile": "Enable at least one AI profile in AI Settings to run AI translation.",
        "ai_translation.note_ready": "AI translation is ready for the current chunk set and selected target language.",
        "ai_translation.note_in_progress": "AI translation is in progress at {progress_current}/{progress_total}.",
        "ai_translation.note_resume": "A previous translation run was not finalized. Press Start Translation to continue from progress {progress_current}/{progress_total}.",
        "ai_translation.note_approval_pending": "Translation is generated. Review and approve every chunk before continuing.",
        "ai_translation.note_completed_locked": "Translation is fully approved. Reset Translation to change the language or start over.",
        "ai_translation.note_summary": "Translated chunks: {translated_count}/{total_count}. Approved chunks: {approved_count}/{total_count}.",
        "ai.note_token_usage_summary": "Input tokens: {input_tokens} | Output tokens: {output_tokens} | Total: {total_tokens}",
        "ai.note_token_usage_unavailable": "Token usage was not reported by the backend.",
        "characters.title": "Characters",
        "characters.ai_profile": "AI Profile",
        "characters.start": "Start Discovery",
        "characters.reset": "Reset Discovery",
        "characters.add_character": "Add Character",
        "characters.edit_character": "Edit Character",
        "characters.save_character": "Save Character",
        "characters.delete_character": "Delete Character",
        "characters.prompt_save": "Save",
        "characters.prompt_discard": "Discard",
        "characters.prompt_cancel": "Cancel",
        "characters.summary": "Run text chunking before Character Discovery.",
        "characters.list_group": "Character List",
        "characters.profile_group": "Character Profile",
        "characters.evidence_group": "Evidence",
        "characters.status_group": "Character Discovery Status",
        "characters.canonical_name": "Canonical Name",
        "characters.aliases": "Aliases",
        "characters.gender_hint": "Gender Hint",
        "characters.gender_confidence": "Gender Confidence",
        "characters.age_hint": "Age Hint",
        "characters.age_confidence": "Age Confidence",
        "characters.voice_definition_prompt": "Voice Definition Prompt",
        "characters.confidence": "Confidence",
        "characters.evidence_note": "Selected source evidence excerpt will appear here.",
        "characters.find": "Find",
        "characters.find_next": "Find Next",
        "characters.find_title": "Find Text",
        "characters.find_prompt": "Text to find:",
        "characters.find_not_found": "No match found for '{search_text}'.",
        "characters.note_no_project": "Create or open a project to begin character discovery.",
        "characters.note_no_source": "Import a source file and complete chunking before character discovery.",
        "characters.note_missing_chunking": "Run deterministic or AI-assisted chunking before character discovery.",
        "characters.note_no_profile": "Enable at least one AI profile in AI Settings to run character discovery.",
        "characters.note_ready": "Character discovery is ready for the current chunk set and selected AI profile.",
        "characters.note_in_progress": "Character discovery is in progress at {progress_current}/{progress_total}.",
        "characters.note_resume": "A previous character discovery run was not finalized. Press Start Discovery to continue from progress {progress_current}/{progress_total}.",
        "characters.note_completed_locked": "Character discovery is completed. Reset Discovery to start over with the current chunk set.",
        "characters.note_summary": "Discovered {character_count} speaking characters across {analyzed_window_count} analysis windows.",
        "characters.note_rerun_replaces_manual": "A fresh discovery rerun replaces the current character list, including manual additions and deletions.",
        "narator_voice.title": "Narator Voice",
        "narator_voice.profiles_group": "Narator Voices",
        "narator_voice.designer_group": "Voice Designer Prompt",
        "narator_voice.preview_group": "Preview Text",
        "narator_voice.status_group": "Narator Voice Status",
        "narator_voice.ai_profile": "AI Profile",
        "narator_voice.language_unknown": "Unknown",
        "narator_voice.language_not_translated": "Not translated",
        "narator_voice.create_profile": "Create",
        "narator_voice.edit_profile": "Edit",
        "narator_voice.save_profile": "Save",
        "narator_voice.delete_profile": "Delete",
        "narator_voice.select_profile": "Select",
        "narator_voice.generate_sample": "Generate Sample",
        "narator_voice.import_sample": "Import Sample",
        "narator_voice.generate_profiles": "Generate Narators",
        "narator_voice.preview": "Play",
        "narator_voice.stop_preview": "Stop",
        "narator_voice.custom_profiles_group_header": "Custom profiles",
        "narator_voice.preview_budget": "Preview budget: {word_count}/{safe_word_count} safe words",
        "narator_voice.list_selected": "Selected",
        "narator_voice.profile_kind_preset": "Preset",
        "narator_voice.profile_kind_custom": "Custom",
        "narator_voice.note_no_project": "Create or open a project before defining narator voice profiles.",
        "narator_voice.note_no_source": "Import one source document before defining the narator voice.",
        "narator_voice.note_runtime_not_connected": "Open TTS Settings and run Test Connection to discover VoiceWeaver models for this project.",
        "narator_voice.note_no_profiles": "No narator voice profiles are stored for the current project.",
        "narator_voice.note_qwen_capabilities_ready": "Qwen3 TTS minimum capabilities are available for narator voice sample generation.",
        "narator_voice.note_qwen_capabilities_missing": "Qwen3 TTS minimum capabilities are missing: {missing_capabilities}.",
        "narator_voice.note_upstream_not_ready": "Character Discovery is not completed yet, but narator voice profiles can already be prepared locally.",
        "narator_voice.note_no_selected_profile": "Select one narator voice profile before preparing character voices.",
        "narator_voice.note_selected_profile": "Selected {profile_kind} profile: {profile_name}.",
        "narator_voice.note_selected_profile_missing_sample": "The selected narator voice still needs a generated sample before it can be previewed or reused for narration.",
        "narator_voice.note_selected_profile_runtime_missing": "The selected narator voice sample references a model that is not reported by the current VoiceWeaver runtime.",
        "narator_voice.note_generate_sample_required": "Generate a sample for the inspected profile before previewing or selecting it.",
        "narator_voice.note_profile_runtime_missing": "This stored sample references a model that is not currently reported by VoiceWeaver.",
        "narator_voice.error_invalid_profile_name": "Enter one narator voice profile name before creating or saving a custom profile.",
        "narator_voice.error_duplicate_profile_name": "A narator voice profile with this name already exists in the current project.",
        "narator_voice.error_readonly_profile": "This narator voice profile cannot be edited.",
        "narator_voice.error_missing_preview_text": "Enter one preview text before generating the narator voice sample.",
        "narator_voice.error_missing_sample": "Generate one sample for this narator voice profile before selecting or previewing it.",
        "narator_voice.error_runtime_model_missing": "The TTS model required by this narator voice profile is not reported by the current VoiceWeaver runtime.",
        "narator_voice.error_qwen_capabilities_missing": "Cannot generate the narator voice sample because the required Qwen3 TTS capabilities are missing: {missing_capabilities}.",
        "narator_voice.error_generation_missing_audio": "VoiceWeaver finished the request but did not report any downloadable audio.",
        "narator_voice.error_preview_text_over_budget": "Preview text is too long for the active TTS runtime budget ({word_count} words, safe limit {safe_word_count}). Shorten the preview text before generating a sample.",
        "narator_voice.status_runtime_connected": "Runtime: connected",
        "narator_voice.status_runtime_not_connected": "Runtime: not connected",
        "narator_voice.status_active_model": "Active model: {model_id}",
        "narator_voice.status_active_model_none": "Active model: none",
        "narator_voice.status_preview_budget": "Preview budget: {word_count}/{safe_word_count} safe words",
        "narator_voice.status_profile_count": "Profiles: {profile_count}",
        "narator_voice.status_sample_count": "Profiles with samples: {sample_count}",
        "narator_voice.status_selected_count": "Selected profiles: {selected_count}",
        "narator_voice.status_qwen_ready": "Qwen3 TTS readiness: ready",
        "narator_voice.status_qwen_missing": "Qwen3 TTS readiness: missing {missing_capabilities}",
        "dialog.narator_voice_create_title": "Create Narator Voice Profile",
        "dialog.narator_voice_create_prompt": "Enter the display name for the new custom narator voice profile:",
        "dialog.narator_voice_delete_title": "Delete Narator Voice Profile",
        "dialog.narator_voice_delete_message": "Delete the selected custom narator voice profile from the current project?",
        "dialog.narator_voice_edit_title": "Edit Narator Voice Profile",
        "dialog.narator_voice_edit_message": "Continuing will delete the current audio sample. You will need to generate a new sample before this profile can be selected again. Continue?",
        "dialog.narator_voice_generate_sample_title": "Generate Narator Voice Sample",
        "dialog.narator_voice_generate_sample_message": "AudioMancer will contact the configured TTS runtime and requires the connection to be tested first in TTS Settings. Continue?",
        "dialog.narator_voice_generate_sample_message_replace": "Continuing will delete the current audio sample and AudioMancer will contact the configured TTS runtime. The connection must be tested first in TTS Settings. Continue?",
        "dialog.voice_sample_import_title": "Import Sample",
        "dialog.voice_sample_import_filter": "WAV audio files (*.wav)",
        "dialog.voice_sample_text_title": "Sample Text",
        "dialog.voice_sample_text_prompt": "Enter the exact text spoken in the imported sample:",
        "dialog.narator_voice_generate_profiles_title": "Generate Narator Voice Profiles",
        "dialog.narator_voice_generate_profiles_message": "AudioMancer will analyze the current book style with the selected AI profile. This can take a long time and may consume paid tokens or credits. Continue?",
        "dialog.narator_voice_generate_profiles_count_prompt": "How many narator profiles should be generated?",
        "progress.narator_voice_sample_prepare": "Preparing narator voice sample generation...",
        "progress.narator_voice_sample_load_model": "Loading voice generation model...",
        "progress.narator_voice_sample_generate": "Generating narator voice sample...",
        "progress.narator_voice_sample_download": "Downloading narator voice sample...",
        "progress.narator_voice_generate_profiles": "Generating narator profiles...",
        "progress.narator_voice_change_prepare": "Preparing narator voice change...",
        "progress.narator_voice_change_profile": "Saving narator voice profile...",
        "progress.narator_voice_change_audio_blocks": "Clearing affected generated audio...",
        "progress.narator_voice_change_audio_assembly": "Resetting Audio Assembly...",
        "progress.narator_voice_change_manifest": "Saving project workflow state...",
        "progress.narator_voice_change_refresh": "Refreshing project state...",
        "status.narator_voice_profile_created": "Narator voice profile created.",
        "status.narator_voice_profile_saved": "Narator voice profile saved.",
        "status.narator_voice_profile_deleted": "Narator voice profile deleted.",
        "status.narator_voice_preview_cancelled": "Narator voice preview cancelled.",
        "status.narator_voice_profile_selected": "Narator voice profile selected.",
        "status.narator_voice_profiles_imported": "Imported {imported_count} model profiles and skipped {skipped_count} existing ones.",
        "status.narator_voice_sample_generated": "Narator voice sample generated.",
        "status.narator_voice_sample_imported": "Narator voice sample imported.",
        "status.narator_voice_profiles_generated": "Generated {generated_count} narator voice profiles.",
        "status.narator_voice_language_changed": "Audiobook voice language changed. Generated samples and downstream data were reset.",
        "status.character_voices_prompt_saved": "Voice prompt saved.",
        "status.character_voices_sample_generated": "Character sample generated.",
        "status.character_voices_sample_imported": "Character sample imported.",
        "status.character_voices_missing_samples_generated": "Character samples regenerated.",
        "voice_sample_import.error_unsupported_file_type": "Import a WAV audio file.",
        "voice_sample_import.error_missing_file": "The selected sample file could not be found.",
        "voice_sample_import.error_invalid_wav": "The selected file is not a readable WAV sample.",
        "voice_sample_import.error_sample_too_short": "The imported sample must be at least {min_duration_seconds:.1f} seconds long.",
        "voice_sample_import.error_sample_silent": "The imported sample is silent or too close to silence.",
        "voice_sample_import.error_empty_sample_text": "Enter the text spoken in the imported sample.",
        "voice_sample_import.error_readonly_target": "Import samples for character targets only on this page.",
        "character_voices.title": "Character Voices",
        "character_voices.list_group": "Voice Targets",
        "character_voices.setup_group": "Voice Target",
        "character_voices.prompt_group": "Voice Designer Prompt",
        "character_voices.preview_group": "Preview Text",
        "character_voices.status_group": "Character Voices Status",
        "character_voices.original_language": "Original language: {language_label}",
        "character_voices.translated_language": "Translated language: {language_label}",
        "character_voices.assignment_mode": "Voice assignment",
        "character_voices.voice_language": "Voice language",
        "character_voices.target_name": "Target Name",
        "character_voices.target_kind": "Target Kind",
        "character_voices.target_kind_narrator": "Narator Voice",
        "character_voices.target_kind_character": "Character",
        "character_voices.assignment_same_narrator": "Same narrator for whole book",
        "character_voices.assignment_narrator_and_characters": "Narrator + character voices",
        "character_voices.import_sample": "Import Sample",
        "character_voices.edit_prompt": "Edit Voice Prompt",
        "character_voices.save_prompt": "Save Voice Prompt",
        "character_voices.generate_sample": "Generate Sample",
        "character_voices.generate_missing_samples": "Generate Character Samples",
        "character_voices.preview": "Preview",
        "character_voices.stop_preview": "Stop Preview",
        "character_voices.sample_present": "Sample present",
        "character_voices.sample_missing": "Sample missing",
        "character_voices.note_no_project": "Create or open a project before preparing character voices.",
        "character_voices.note_no_source": "Import one source document before preparing character voices.",
        "character_voices.note_no_characters": "Complete Character Discovery so this page can list every character.",
        "character_voices.note_no_selected_narrator": (
            "Select one narator voice profile on the Narator Voice page before preparing character voices."
        ),
        "character_voices.note_missing_narrator_sample": (
            "Generate the selected narator voice sample on the Narator Voice page before preparing character voices."
        ),
        "character_voices.note_translation_not_fully_approved": "The translated language will become selectable only after every translated chunk is approved.",
        "character_voices.note_same_narrator_mode": "Voice assignment is set to use the same narrator voice for the whole book, so character prompts and generation are disabled.",
        "character_voices.note_runtime_not_connected": "Open TTS Settings and run Test Connection to verify VoiceWeaver before generating character samples.",
        "character_voices.note_profile_runtime_missing": "This stored sample references a model that is not currently reported by VoiceWeaver.",
        "character_voices.note_qwen_capabilities_ready": "Qwen3 TTS minimum capabilities are available for character sample generation.",
        "character_voices.note_qwen_capabilities_missing": "Qwen3 TTS minimum capabilities are missing: {missing_capabilities}.",
        "character_voices.error_missing_prompt": "Enter one voice designer prompt before saving.",
        "character_voices.error_missing_preview_text": "Enter one preview text before saving or generating a sample.",
        "character_voices.error_missing_sample": "No stored sample is available for the inspected target.",
        "character_voices.error_qwen_capabilities_missing": "Cannot generate the character sample because the required Qwen3 TTS capabilities are missing: {missing_capabilities}.",
        "character_voices.error_generation_missing_audio": "VoiceWeaver finished the request but did not report any downloadable audio.",
        "speech_blocks.title": "Speech Blocks",
        "speech_blocks.ai_profile": "AI Profile",
        "speech_blocks.generate": "Generate All",
        "speech_blocks.reset_generation": "Reset",
        "speech_blocks.approve_all": "Approve All",
        "speech_blocks.chunk_list_group": "Chunk List",
        "speech_blocks.selected_group": "Selected Chunk",
        "speech_blocks.blocks_group": "Speech Blocks",
        "speech_blocks.status_group": "Speech Blocks Status",
        "speech_blocks.note_no_project": "Create or open a project to begin Speech Blocks generation.",
        "speech_blocks.note_no_source": "Import a source file and complete Character Voices before generating Speech Blocks.",
        "speech_blocks.note_missing_source": "Run text chunking, resolve the Character Voices language, and approve translation if needed before generating Speech Blocks.",
        "speech_blocks.note_no_profile": "Enable at least one AI profile in AI Settings to run Speech Blocks generation.",
        "speech_blocks.note_ready": "Speech Blocks generation is ready for the current Character Voices language and selected AI profile.",
        "speech_blocks.note_in_progress": "Speech Blocks generation is in progress at {progress_current}/{progress_total}.",
        "speech_blocks.note_resume": "A previous Speech Blocks run was not finalized. Press Generate Speech Blocks to continue from progress {progress_current}/{progress_total}.",
        "speech_blocks.note_summary": "Generated {block_count} speech blocks from {processed_chunk_count}/{total_chunk_count} chunks.",
        "speech_blocks.note_approval_summary": "Approved speech blocks: {approved_block_count}/{total_block_count}.",
        "speech_blocks.note_waiting_for_approval": "Review and approve every Speech Block before continuing to Audio Blocks.",
        "speech_blocks.note_ready_for_audio": "Every Speech Block is approved. The workflow is ready for Audio Blocks.",
        "speech_blocks.note_warning_summary": "Speech Blocks recorded {warning_count} warning entries that should be reviewed.",
        "speech_blocks.note_warning_entry": "{chunk_id}: {reason}",
        "speech_blocks.note_rerun_warning": "Running Speech Blocks again will replace the current speech-block data and reset Audio Blocks plus Audio Assembly.",
        "speech_blocks.detail_speaker": "Speaker",
        "speech_blocks.detail_block_id": "Block ID",
        "speech_blocks.detail_content_kind": "Content Kind",
        "speech_blocks.detail_warning_flags": "Warning Flags",
        "speech_blocks.detail_none": "(none)",
        "speech_blocks.content_narration": "Narration",
        "speech_blocks.content_dialogue": "Dialogue",
        "speech_blocks.content_scene_ambience": "Scene Ambience",
        "speech_blocks.content_pause": "Pause",
        "speech_blocks.content_indication": "Indication",
        "speech_blocks.ambient_prompt": "Prompt",
        "speech_blocks.ambient_negative_prompt": "Negative Prompt",
        "speech_blocks.ambient_duration": "Duration (s)",
        "speech_blocks.insert_block": "Insert",
        "speech_blocks.delete_block": "Delete",
        "speech_blocks.resplit_selected": "Split Chunk",
        "speech_blocks.edit_block": "Edit",
        "speech_blocks.save_block": "Save",
        "speech_blocks.approve_block": "Approve",
        "speech_blocks.unapprove_block": "Unapprove",
        "speech_blocks.generate_audio_selected": "Generate Audio",
        "speech_blocks.warning_indicator": "Warning: {warning_flags}",
        "audio_blocks.title": "Audio Blocks",
        "audio_blocks.scene_ambience_audio_selector": "Scene Ambience Audio",
        "audio_blocks.scene_ambience_audio_disabled": "Off",
        "audio_blocks.scene_ambience_audio_enabled": "On",
        "audio_blocks.start_generation": "Start Audio Generation",
        "audio_blocks.play_audiobook": "Play Audiobook",
        "audio_blocks.stop_audiobook": "Stop Audiobook",
        "audio_blocks.reset_generation": "Reset Audio Generation",
        "audio_blocks.approve_all": "Approve All",
        "audio_blocks.source_group": "Source Text",
        "audio_blocks.blocks_group": "Speech Blocks",
        "audio_blocks.selected_group": "Selected Block",
        "audio_blocks.status_group": "Audio Blocks Status",
        "audio_blocks.regenerate_selected": "Re-Generate Audio",
        "audio_blocks.play_selected": "Play",
        "audio_blocks.stop_playback": "Stop",
        "audio_blocks.approve_selected": "Approve",
        "audio_blocks.unapprove_selected": "Unapprove",
        "audio_blocks.error_missing_audio": "The selected Audio Block has no generated audio file to play.",
        "audio_blocks.note_no_project": "Create or open a project before generating Audio Blocks.",
        "audio_blocks.note_no_source": "Import one source document before generating Audio Blocks.",
        "audio_blocks.note_missing_speech_blocks": "Generate Speech Blocks before starting Audio Blocks.",
        "audio_blocks.note_summary": (
            "Generated audio for {generated_count}/{total_count} speech blocks and approved "
            "{approved_count}/{total_count}."
        ),
        "audio_blocks.note_in_progress": "Audio generation is in progress at {progress_current}/{progress_total}.",
        "audio_blocks.note_prepare_prompts": "Preparing reusable voice prompts. Available: {prompt_count}.",
        "audio_blocks.note_generating_blocks": "Generating audio blocks from the prepared reusable voice prompts.",
        "audio_blocks.note_resume": (
            "A previous Audio Blocks run was not finalized. Press Start Audio Generation to continue from "
            "{progress_current}/{progress_total}."
        ),
        "audio_blocks.note_ready": "Audio Blocks generation is ready for the current Speech Blocks and voice samples.",
        "audio_blocks.note_waiting_for_approval": (
            "Every speech block has generated audio, but approval is still required before Audio Assembly."
        ),
        "audio_blocks.note_ready_for_assembly": (
            "Every generated speech block is approved. The workflow is ready for Audio Assembly."
        ),
        "audio_blocks.note_invalidated": "The previous Audio Blocks data is stale: {invalidation_reason}",
        "audio_blocks.status_generated": "Generated audio: {generated_count}/{total_count}",
        "audio_blocks.status_approved": "Approved audio: {approved_count}/{total_count}",
        "audio_blocks.status_voice_language": "Voice language: {language_label}",
        "audio_blocks.status_prompts": "Reusable prompts: {prompt_count}",
        "audio_blocks.progress_label": "Generated blocks: {progress_current}/{progress_total}",
        "audio_blocks.detail_speaker": "Speaker: {speaker_label}",
        "audio_blocks.detail_approval_status": "Status: {status_label}",
        "audio_blocks.approval_status_approved": "Approved",
        "audio_blocks.approval_status_pending": "Pending",
        "audio_blocks.marker_generated": "audio",
        "audio_blocks.marker_missing": "none",
        "audio_blocks.marker_approved": "approved",
        "audio_blocks.marker_pending": "pending",
        "audio_blocks.marker_current": "current",
        "audio_blocks.duration_seconds": "{duration_seconds:.1f}s",
        "audio_blocks.duration_unknown": "--.-s",
        "character_voices.status_total_targets": "Total targets: {target_count}",
        "character_voices.status_targets_with_samples": "Targets with samples: {sample_count}",
        "character_voices.status_assignment_mode": "Voice assignment: {assignment_mode}",
        "character_voices.status_voice_language": "Voice language: {language_label}",
        "character_voices.status_generation_ready": "Generation readiness: {readiness}",
        "character_voices.readiness_ready": "ready",
        "character_voices.readiness_not_ready": "not ready",
        "dialog.character_voices_edit_title": "Edit Voice Prompt",
        "dialog.character_voices_edit_message": "Continuing will delete the current sample for this character. You will need to generate a new sample after saving the edited prompt. Continue?",
        "dialog.character_voices_generate_sample_title": "Generate Character Sample",
        "dialog.character_voices_generate_sample_message": "AudioMancer will contact the configured TTS runtime and requires the connection to be tested first in TTS Settings. Continue?",
        "dialog.character_voices_generate_sample_message_replace": "Continuing will delete the current sample and AudioMancer will contact the configured TTS runtime. The connection must be tested first in TTS Settings. Continue?",
        "dialog.character_voices_generate_missing_samples_title": "Generate Character Samples",
        "dialog.character_voices_generate_missing_samples_message": "AudioMancer will regenerate samples for all {sample_count} current character target(s). Existing character samples will be replaced. The configured TTS runtime must be available. Continue?",
        "dialog.character_voices_missing_narrator_sample_title": "Narator Voice Sample Required",
        "dialog.character_voices_missing_narrator_sample_message": (
            "The selected narator voice profile does not have a generated sample yet. Open the Narator Voice page and "
            "generate the narator voice sample before preparing character voices."
        ),
        "progress.character_voices_sample_prepare": "Preparing character sample generation...",
        "progress.character_voices_sample_load_model": "Loading voice generation model...",
        "progress.character_voices_sample_generate": "Generating character sample...",
        "progress.character_voices_sample_download": "Downloading character sample...",
        "progress.character_voices_batch_prepare": "Preparing character sample batch...",
        "progress.character_voices_batch_target": "Generating sample {current}/{total}: {target_name}",
        "placeholder.character_voices.title": "Character Voices",
        "placeholder.character_voices.note": "Character voice preparation is implemented on this page.",
        "placeholder.speech_blocks.title": "Speech Blocks",
        "placeholder.speech_blocks.note": (
            "This future step will split workflow chunks into speaker-attributed TTS blocks based on speaking "
            "changes and TTS token limits."
        ),
        "placeholder.audio_blocks.title": "Audio Blocks",
        "placeholder.audio_blocks.note": (
            "This future step will generate and approve audio for each speaker-attributed block while preserving "
            "original text and editable text."
        ),
        "placeholder.audio_assembly.title": "Audio Assembly",
        "placeholder.audio_assembly.note": (
            "This future step will assemble approved audio blocks into final audio files and package metadata such "
            "as subtitles and speaker data."
        ),
        "audio_assembly.title": "Audio Assembly",
        "audio_assembly.settings_group": "Output Settings",
        "audio_assembly.scene_mix_group": "Scene Mix Previews",
        "audio_assembly.outputs_group": "Generated Audiobook Files",
        "audio_assembly.status_group": "Audio Assembly Status",
        "audio_assembly.output_mode": "Output Mode",
        "audio_assembly.max_duration": "Max Duration",
        "audio_assembly.output_format": "Output Format",
        "audio_assembly.inter_block_silence": "Inter-Block Silence",
        "audio_assembly.inter_chunk_silence": "Inter-Chunk Silence",
        "audio_assembly.include_scene_ambience": "Include Scene Ambience",
        "audio_assembly.generate": "Generate Audio",
        "audio_assembly.reset": "Reset Audio Assembly",
        "audio_assembly.play_audio": "Play Audio",
        "audio_assembly.generate_scene_mix": "Generate / Refresh Scene Mix",
        "audio_assembly.play_scene_mix": "Play Scene Mix",
        "audio_assembly.stop_playing": "Stop Playing",
        "audio_assembly.rewind_10s": "-10s",
        "audio_assembly.forward_10s": "+10s",
        "audio_assembly.mode.per_chunk": "Per text chunk",
        "audio_assembly.mode.time_limit": "Time limit",
        "audio_assembly.mode.whole_book": "Whole audiobook",
        "audio_assembly.note_no_project": "Create or open a project before assembling audio.",
        "audio_assembly.note_missing_audio_blocks": "Generate and approve Audio Blocks before Audio Assembly.",
        "audio_assembly.note_missing_approvals": (
            "Approve every Audio Block before Audio Assembly. Approved: {approved_blocks}/{total_blocks}."
        ),
        "audio_assembly.note_ready": "Audio Assembly is ready. Generation can be interrupted and resumed later.",
        "audio_assembly.note_resume": "Audio Assembly was interrupted. Press Generate Audio to continue.",
        "audio_assembly.note_completed": "Audio Assembly completed. Generated files are stored in the audiobook folder.",
        "audio_assembly.status_blocks": "Approved audio blocks: {approved_blocks}/{total_blocks}",
        "audio_assembly.status_outputs": "Generated output files: {generated_outputs}/{planned_outputs}",
        "audio_assembly.status_duration": "Total composed duration: {duration}",
        "audio_assembly.status_mode": "Output mode: {mode}",
        "audio_assembly.error_missing_audio": "The selected audiobook file is missing.",
        "audio_assembly.error_missing_scene_mix": "The selected scene mix preview is missing.",
        "audio_assembly.output_item": "{file_name} | {duration} | {block_count} audio blocks",
        "audio_assembly.scene_mix_item": "{label} | {duration} | {block_count} sounds | {status}",
        "audio_assembly.scene_mix_ready": "ready",
        "audio_assembly.scene_mix_not_ready": "needs generated audio",
        "audio_assembly.scene_mix_generated": "preview ready",
        "home.title": "Home / Project",
        "home.summary_group": "Project Summary",
        "home.exports_group": "Exports",
        "home.project": "Project",
        "home.path": "Path",
        "home.stage": "Stage",
        "home.source": "Source",
        "home.audiobook_language": "Translation Language: {language_label}",
        "home.narration_mode": "Audio Output Style: {mode_label}",
        "home.translation_language": "Translation language",
        "home.audio_output_style": "Audio output style",
        "home.options_locked": "Project options locked. Source import is available.",
        "home.options_unlocked": "Select a source file, choose translation language and audio output style, then press Start Project.",
        "home.mode_same_narrator": "Same narrator for whole book",
        "home.mode_narrator_and_characters": "Narrator + character voices",
        "home.start_project": "Start Project",
        "home.none": "none",
        "home.source_import_group": "Source Import",
        "home.source_import_note": "Each project is bound to exactly one source file. After the source is imported, the selection is locked for that project.",
        "home.select_source": "Select Source File",
        "home.export_project_zip": "Export Project ZIP",
        "home.no_source": "No source imported yet.",
        "home.selected_source_prefix": "Selected source",
        "home.selected_source_suffix": ". Press Start Project to lock it.",
        "home.locked_source_prefix": "Locked source",
        "home.locked_source_suffix": ". Create a new project to use another file.",
        "home.export.cleaned_text": "Cleaned Text",
        "home.export.text_chunks": "Text Chunks",
        "home.export.ai_translation": "AI Translation",
        "home.export.characters": "Characters",
        "home.export.narrator_voice": "Narator Voice",
        "home.export.character_voices": "Character Voices",
        "home.export.speech_blocks": "Speech Blocks",
        "home.export.audio_assembly": "Audio Assembly",
        "home.export_status.available": "Available",
        "home.export_status.not_ready": "Not ready",
        "home.export_status.missing_artifact": "Missing artifact",
        "home.export_format.txt": "TXT",
        "home.export_format.markdown": "Markdown",
        "home.export_format.zip": "ZIP",
        "home.export_button": "Export",
        "home.export_not_ready_message": "This export is not available yet.",
        "home.export_inside_project_message": (
            "Choose a destination outside the active project folder so runtime files cannot be overwritten."
        ),
        "home.snapshot_inside_project_message": (
            "Choose a ZIP destination outside the active project folder so the snapshot is not archived into itself."
        ),
        "home.snapshot_active_operation_message": (
            "Project ZIP export is blocked while an operation is running. Wait for the current operation to finish first."
        ),
        "home.snapshot_failure_message": "The project ZIP snapshot could not be created.",
        "home.workflow_group": "Workflow Progress",
        "home.status.not_started": "Not Started",
        "home.status.in_progress": "In Progress",
        "home.status.finished": "Finished",
        "home.stage_label.source_selected": "Source Selected",
        "home.stage_label.text_cleanup_ready": "Text Cleanup",
        "home.stage_label.text_chunking_ready": "Text Chunking",
        "home.stage_label.translation_ready": "AI Translation",
        "home.stage_label.character_discovery_ready": "Characters",
        "home.stage_label.narrator_definition_ready": "Narator Voice",
        "home.stage_label.character_voices_ready": "Character Voices",
        "home.stage_label.speech_blocks_ready": "Speech Blocks",
        "home.stage_label.audio_blocks_ready": "Audio Blocks",
        "home.stage_label.audio_assembly_ready": "Audio Assembly",
        "home.stage_note.inactive.source_selected": "Create or open a project first.",
        "home.stage_note.inactive.text_cleanup_ready": "Create or open a project first.",
        "home.stage_note.inactive.text_chunking_ready": "Create or open a project first.",
        "home.stage_note.inactive.translation_ready": "Create or open a project first.",
        "home.stage_note.inactive.character_discovery_ready": "Create or open a project first.",
        "home.stage_note.inactive.narrator_definition_ready": "Create or open a project first.",
        "home.stage_note.inactive.character_voices_ready": "Create or open a project first.",
        "home.stage_note.inactive.speech_blocks_ready": "Create or open a project first.",
        "home.stage_note.inactive.audio_blocks_ready": "Create or open a project first.",
        "home.stage_note.inactive.audio_assembly_ready": "Create or open a project first.",
        "home.stage_note.active.source_selected": "Select and import one source file for the project.",
        "home.stage_note.active.text_cleanup_ready": "Prepare the imported source text for chunking.",
        "home.stage_note.active.text_chunking_ready": "Split the cleaned text into workflow chunks.",
        "home.stage_note.active.translation_ready": "Translate the chunk set when needed.",
        "home.stage_note.active.character_discovery_ready": "Extract and review the character set.",
        "home.stage_note.active.narrator_definition_ready": "Select and adapt the narator voice profile for the project.",
        "home.stage_note.active.character_voices_ready": "Prepare narrator and character voice samples for later audio generation.",
        "home.stage_note.active.speech_blocks_ready": "Split translated or original chunks into speaker-attributed speech blocks.",
        "home.stage_note.active.audio_blocks_ready": "Generate and approve audio for each speech block.",
        "home.stage_note.active.audio_assembly_ready": "Assemble approved audio blocks into final deliverables.",
        "project.new_dialog_intro": "Choose the parent folder where the project will be created and enter the exact project name.",
        "project.parent_folder": "Parent Folder",
        "project.project_name": "Project Name",
        "project.browse": "Browse",
        "project.create": "Create",
        "project.cancel": "Cancel",
        "project.error_missing_parent": "Select the parent folder where the project should be created.",
        "project.error_missing_name": "Enter the exact project name.",
        "project.error_no_active_project": "Create or open a project before importing a source file.",
        "project.error_missing_source": "Import a source file before running text extraction.",
        "project.error_missing_extracted_text": "Run Extract Text before starting cleanup.",
        "project.error_missing_cleaned_text": "Run text cleanup before starting chunking.",
        "project.error_missing_chunk_artifact": "Run text chunking before starting AI translation.",
        "project.error_missing_ai_profile": "Select a valid AI profile before starting AI-assisted cleanup.",
        "project.error_missing_ai_chunking_profile": "Select a valid AI profile before starting AI-assisted chunking.",
        "project.error_missing_ai_translation_profile": "Select a valid AI profile before starting AI translation.",
        "project.error_missing_character_discovery_profile": "Select a valid AI profile before starting character discovery.",
        "project.error_missing_narrator_generation_profile": "Select a valid AI profile before generating narator profiles.",
        "project.error_missing_speech_blocks_profile": "Select a valid AI profile before starting Speech Blocks generation.",
        "project.error_project_options_unlocked": "Start the project before continuing.",
        "project.error_project_already_started": "This project is already started. Create a new project to use another source file.",
        "project.error_start_project_missing_source": "Select a source file before starting the project.",
        "project.error_duplicate_character_name": "A character with that name already exists in the current list.",
        "project.error_invalid_character_name": "Enter a character name that contains letters or digits.",
        "project.error_locked_source": "This project already has a locked source file. Create a new project to use another source.",
        "project.confirm_project_options_lock": (
            "The selected source file, translation language, and audio output style will be fixed for this project. "
            "Continue?"
        ),
        "project.confirm_extraction_rerun": "Continuing will delete the current extraction data and all subsequent-step data, clear the following operation folders, and reset workflow progress. Continue?",
        "project.confirm_cleanup_rerun": "Continuing will delete the current cleanup data and every downstream result. Continue?",
        "project.confirm_cleanup_mode_switch": "Changing Cleanup mode will delete the current Cleanup result and every downstream result. Continue?",
        "project.confirm_cleanup_reset": "Reset Cleanup will delete cleanup.json, clean_text.txt, legacy Cleanup metadata, Cleanup logs, and every downstream result, including characters, voices, and audio. Continue?",
        "project.ai_cleanup_reset_required_invalid": "AI Cleanup cannot continue because cleanup.json is invalid, incompatible, or missing for a legacy run. Use Reset Cleanup first.",
        "project.ai_cleanup_reset_required_completed": "AI Cleanup is completed. Use Reset Cleanup before starting a new run.",
        "project.confirm_chunking_rerun": "Continuing will delete the current chunking data, clear translation and all following operation folders, and reset workflow progress after cleanup. Continue?",
        "project.confirm_ai_chunking_rerun": "Continuing will delete the current chunking data, clear translation and all following operation folders, and reset workflow progress after cleanup before starting new AI-assisted chunking. Continue?",
        "project.confirm_cleaned_text_edit": "Editing cleaned text can affect downstream chunking, translation, character discovery, Speech Blocks, Audio Blocks, and Audio Assembly after the change is saved. Continue?",
        "project.confirm_chunk_edit": "Editing this chunk can reset Translation for this chunk, remove Speech Blocks and Audio Blocks for this chunk, and reset Audio Assembly after the change is saved. Unaffected chunks are preserved. Continue?",
        "project.confirm_chunk_insert": "Inserting a chunk will add an untranslated record, update chunk sequence metadata, and reset Audio Assembly. Existing chunk ids and unaffected downstream data are preserved. Continue?",
        "project.confirm_chunk_delete": "Deleting this chunk will remove its Translation, Speech Blocks, Audio Blocks, and generated audio, then reset Audio Assembly. Unaffected chunks are preserved. Continue?",
        "project.confirm_speech_blocks": "Speech Blocks generation can take time because it sends one AI request per chunk and consumes AI tokens. A successful run will reset Audio Blocks and Audio Assembly. Continue?",
        "project.confirm_speech_blocks_rerun": "Continuing will delete the current Speech Blocks data, clear Audio Blocks and Audio Assembly, and reset workflow progress after Character Voices before starting a new Speech Blocks run. Continue?",
        "project.confirm_speech_blocks_resplit": (
            "Continuing will erase the Speech Blocks for the selected chunk and send a new AI request. "
            "AI operations can take a long time and may consume paid tokens. Continue?"
        ),
        "project.confirm_scene_ambience_speech_blocks": (
            "Scene Ambience analysis adds extra LLM calls for each chunk, can take more time, and can be "
            "cancelled and resumed at the next unfinished chunk. Continue?"
        ),
        "project.confirm_delete_speech_block": (
            "Continuing will delete the selected Speech Block, remove only its generated Audio Block data, renumber "
            "the chunk sequence, and reset Audio Assembly. Continue?"
        ),
        "project.confirm_speech_block_audio_reset": (
            "This Speech Block change affects generated audio for the selected block. Continuing will delete only "
            "that block's generated WAV files, reset its audio metadata, and reset downstream Audio Assembly data. "
            "Continue?"
        ),
        "project.confirm_speech_block_sequence_change": (
            "Continuing will preserve existing Audio Blocks, update the Speech Blocks sequence, and reset Audio "
            "Assembly because the final playback order changes. Continue?"
        ),
        "project.confirm_audio_blocks": (
            "Audio generation can take a long time because it prepares reusable voice prompts and then "
            "generates each speech block one by one. The run can be interrupted and resumed later. Continue?"
        ),
        "project.confirm_scene_ambience_audio_blocks": (
            "Scene Ambience sound generation can take significant time and requires a healthy VoiceWeaver model "
            "that supports sound_prompt. Continue?"
        ),
        "project.confirm_audio_blocks_rerun": (
            "Continuing will delete the current generated audio blocks, reusable voice-prompt metadata, and Audio "
            "Assembly data before starting a new run. Continue?"
        ),
        "project.confirm_audio_blocks_reset": (
            "Continuing will delete all generated audio blocks, reusable voice prompts, and downstream Audio Assembly "
            "data. Continue?"
        ),
        "project.confirm_audio_blocks_invalidation": (
            "This change affects the current Audio Blocks inputs. Continuing will reset generated audio blocks, "
            "their approvals, and downstream Audio Assembly data. Continue?"
        ),
        "project.confirm_audio_block_regeneration": (
            "Continuing will regenerate only the selected Audio Block, clear its approval, and reset downstream "
            "Audio Assembly outputs. Other Audio Blocks and upstream workflow data will be preserved. Continue?"
        ),
        "project.confirm_audio_block_approval_change": (
            "Changing Audio Block approval affects Audio Assembly eligibility. Continuing will preserve generated "
            "Audio Blocks and reset downstream Audio Assembly outputs. Continue?"
        ),
        "project.confirm_single_voice_target_invalidation": (
            "This voice-target change preserves Speech Blocks and Audio Block rows, and clears only generated audio "
            "that uses this voice. Reusable prompts for the voice and Audio Assembly data will also be reset. Continue?"
        ),
        "project.confirm_narrator_voice_invalidation": (
            "This narrator voice change preserves Speech Blocks and Audio Block rows, and clears only generated "
            "audio that uses the Narrator voice. In same-narrator projects, all spoken Audio Blocks are affected. "
            "Audio Assembly data will also be reset. Continue?"
        ),
        "project.confirm_global_voice_settings_invalidation": (
            "This global voice setting change preserves Speech Blocks but resets all generated Audio Blocks, reusable "
            "voice prompts, and Audio Assembly data. Continue?"
        ),
        "project.confirm_translation_reset": (
            "Continuing will delete the current translation data plus downstream character, voice, speech, audio, "
            "and audiobook outputs. Continue?"
        ),
        "project.confirm_ai_cleanup": "AI-assisted cleanup can take longer because it sends multiple requests through the selected AI provider. Continue?",
        "project.confirm_ai_cleanup_rerun": "Continuing will delete the current cleanup data, clear chunking and all following operation folders, and reset workflow progress after extraction before starting a new AI-assisted cleanup. Continue?",
        "project.info_character_discovery": "Character discovery can take a long time because it analyzes overlapping chunk windows and then synthesizes final character profiles. You can continue the run later if needed. A fresh discovery rerun replaces the current character list, including manual additions and deletions.",
        "progress.extracting": "Text extraction in progress...",
        "progress.cleaning": "Deterministic cleanup in progress...",
        "progress.ai_cleaning": "AI-assisted cleanup in progress...",
        "progress.chunking": "Deterministic chunking in progress...",
        "progress.ai_chunking": "AI-assisted chunking in progress...",
        "progress.ai_translation": "AI translation in progress...",
        "progress.ai_translation_retranslate": "Selected chunk re-translation in progress...",
        "progress.character_discovery": "Character discovery in progress...",
        "progress.character_save_prepare": "Preparing character save...",
        "progress.character_save_profile": "Saving character profile...",
        "progress.character_save_character_voices": "Synchronizing Character Voices...",
        "progress.character_save_speech_blocks": "Updating Speech Blocks...",
        "progress.character_save_audio_blocks": "Clearing affected generated audio...",
        "progress.character_save_manifest": "Saving project workflow state...",
        "progress.character_save_refresh": "Refreshing project state...",
        "progress.speech_blocks": "Speech Blocks generation in progress...",
        "progress.speech_blocks_resplit": ("Selected chunk Speech Blocks re-splitting in progress..."),
        "progress.audio_blocks": "Audio Blocks generation in progress...",
        "progress.audio_block_regeneration": "Selected audio block regeneration in progress...",
        "progress.audio_assembly": "Audio Assembly composition in progress...",
        "progress.scene_mix_preview": "Scene Mix preview generation in progress...",
        "progress.project_snapshot": "Project ZIP export in progress...",
        "dialog.confirm_translation_reset_title": "Confirm Translation Reset",
        "dialog.confirm_speech_blocks_title": "Start Speech Blocks Generation",
        "dialog.confirm_speech_blocks_rerun_title": "Confirm Speech Blocks Rerun",
        "dialog.confirm_speech_blocks_resplit_title": "Confirm Selected Chunk Re-Split",
        "dialog.confirm_scene_ambience_speech_blocks_title": "Enable Scene Ambience Analysis",
        "dialog.confirm_delete_speech_block_title": "Delete Speech Block",
        "dialog.confirm_speech_block_audio_reset_title": "Confirm Speech Block Audio Reset",
        "dialog.confirm_speech_block_sequence_change_title": "Confirm Speech Block Sequence Change",
        "dialog.confirm_audio_blocks_title": "Start Audio Generation",
        "dialog.confirm_scene_ambience_audio_blocks_title": "Enable Scene Ambience Audio",
        "dialog.confirm_audio_blocks_rerun_title": "Confirm Audio Generation Rerun",
        "dialog.confirm_audio_blocks_reset_title": "Confirm Audio Generation Reset",
        "dialog.confirm_audio_blocks_invalidation_title": "Confirm Audio Blocks Reset",
        "dialog.confirm_audio_block_regeneration_title": "Confirm Selected Audio Regeneration",
        "dialog.confirm_audio_block_approval_title": "Confirm Audio Approval Change",
        "dialog.confirm_single_voice_target_invalidation_title": "Confirm Voice Target Audio Reset",
        "dialog.confirm_narrator_voice_invalidation_title": "Confirm Narrator Audio Reset",
        "dialog.confirm_global_voice_settings_invalidation_title": "Confirm Global Voice Audio Reset",
        "dialog.confirm_audio_assembly_title": "Start Audio Assembly",
        "dialog.confirm_audio_assembly_reset_title": "Confirm Audio Assembly Reset",
        "project.confirm_audio_assembly": (
            "Audio Assembly can take a long time for large books. The operation can be interrupted and resumed "
            "later when the inputs and settings have not changed. Continue?"
        ),
        "project.confirm_audio_assembly_reset": (
            "Continuing will delete generated audiobook files and Audio Assembly progress. Continue?"
        ),
        "project.confirm_audio_assembly_settings_change": (
            "Changing Audio Assembly settings will reset only existing audiobook outputs, assembly state, and the "
            "assembly report. Approved Audio Blocks and upstream data will be preserved. Continue?"
        ),
        "status.audio_assembly_generated": "Audio Assembly completed.",
        "status.audio_assembly_reset": "Audio Assembly data was reset.",
        "status.audio_assembly_settings_saved_reset": "Audio Assembly settings saved and existing assembly output reset.",
        "status.audio_assembly_scene_mix_generated": "Scene mix preview generated.",
        "dialog.confirm_audio_assembly_settings_change_title": "Confirm Assembly Settings Change",
        "dialog.character_discovery_info_title": "Character Discovery Information",
        "dialog.character_add_title": "Add Character",
        "dialog.character_add_prompt": "Enter the canonical name for the new character.",
        "dialog.character_add_confirm_title": "Confirm Character Add",
        "dialog.character_add_confirm_message": (
            "Add this character and synchronize the Character Voices target list? "
            "Existing Speech Blocks, Audio Blocks, and assembly outputs will be preserved."
        ),
        "dialog.character_edit_title": "Confirm Character Edit",
        "dialog.character_edit_message": (
            "Save this character edit? Assigned Speech Blocks will become unapproved, "
            "only their Audio Blocks will be reset, and Audio Assembly will be reset."
        ),
        "dialog.character_delete_title": "Delete Character",
        "dialog.character_delete_message": (
            "Delete the selected character? Assigned Speech Blocks will be reassigned to Narrator and unapproved, "
            "only affected Audio Blocks will be reset, and Audio Assembly will be reset."
        ),
        "dialog.character_unsaved_title": "Unsaved Character Changes",
        "dialog.character_unsaved_message": "The current character has unsaved changes. Save them before continuing?",
        "project.repair_step_prefix": "The project is corrupted at step",
        "project.repair_reset_suffix": "This repair will recreate and reset that step and all downstream step folders.",
        "project.repair_metadata_only": "This repair will update the project metadata to the last consistent workflow stage.",
        "project.repair_changes_header": "Metadata updates",
        "project.repair_warnings_header": "Warnings",
        "project.repair_confirm": "Do you want to repair the project now?",
    },
    "ro": {
        "window_title.main": "AudioMancer | Transforma cuvintele scrise intr-o experienta audio reala!",
        "toolbar.new_project": "Proiect Nou",
        "toolbar.open_project": "Deschide Proiect",
        "toolbar.settings": "Setari",
        "toolbar.ai_settings": "Setari AI",
        "toolbar.tts_settings": "Setari TTS",
        "toolbar.help": "Ajutor",
        "toolbar.about": "Despre",
        "dialog.settings_title": "Setari",
        "dialog.theme_name_title": "Nume Tema",
        "dialog.theme_name_prompt": "Introdu numele temei:",
        "dialog.theme_delete_title": "Sterge Tema",
        "dialog.theme_delete_message": "Stergi aceasta tema personalizata? Temele incluse nu pot fi sterse.",
        "dialog.theme_import_title": "Importa Tema",
        "dialog.theme_export_title": "Exporta Tema",
        "dialog.theme_import_error_title": "Eroare Import Tema",
        "dialog.theme_export_error_title": "Eroare Export Tema",
        "dialog.ai_settings_title": "Setari AI",
        "dialog.tts_settings_title": "Setari TTS",
        "dialog.about_title": "Despre",
        "dialog.new_project_title": "Proiect Nou",
        "dialog.open_project_title": "Deschide Proiect",
        "dialog.select_project_parent_title": "Selecteaza Dosarul Parinte Al Proiectului",
        "dialog.select_source_title": "Selecteaza Fisierul Sursa",
        "dialog.select_source_filter": "Fisiere sursa acceptate (*.txt *.pdf *.rtf *.docx *.odt *.md *.epub)",
        "dialog.export_title": "Exporta Artefact Proiect",
        "dialog.export_filter_txt": "Fisiere Text (*.txt)",
        "dialog.export_filter_markdown": "Fisiere Markdown (*.md)",
        "dialog.snapshot_title": "Exporta Snapshot ZIP Proiect",
        "dialog.snapshot_filter_zip": "Arhive ZIP (*.zip)",
        "dialog.project_error_title": "Eroare Proiect",
        "dialog.project_repair_title": "Repara Proiectul",
        "dialog.confirm_extraction_rerun_title": "Confirma Reluarea Extragerii",
        "dialog.confirm_cleanup_rerun_title": "Confirma Reluarea Curatarii",
        "dialog.confirm_cleanup_mode_switch_title": "Schimba Modul de Curatare",
        "dialog.confirm_cleanup_reset_title": "Reseteaza Curatarea",
        "dialog.confirm_chunking_rerun_title": "Confirma Reluarea Segmentarii",
        "dialog.confirm_ai_chunking_rerun_title": "Confirma Reluarea Segmentarii AI",
        "dialog.confirm_cleaned_text_edit_title": "Confirma Editarea Textului Curatat",
        "dialog.confirm_chunk_edit_title": "Confirma Editarea Segmentului",
        "dialog.confirm_chunk_insert_title": "Confirma Inserarea Segmentului",
        "dialog.confirm_chunk_delete_title": "Confirma Stergerea Segmentului",
        "dialog.confirm_ai_cleanup_title": "Porneste Curatarea Asistata de AI",
        "dialog.confirm_ai_cleanup_rerun_title": "Confirma Reluarea Curatarii AI",
        "dialog.ai_cleanup_extra_prompt_title": "Instructiuni Curatare AI",
        "dialog.ai_cleanup_extra_prompt_label": (
            "Reguli suplimentare optionale de curatare de adaugat la promptul AI. Lasa gol pentru promptul standard."
        ),
        "dialog.ai_chunking_extra_prompt_title": "Instructiuni Segmentare AI",
        "dialog.ai_chunking_extra_prompt_label": (
            "Reguli suplimentare optionale de segmentare de adaugat la promptul AI. Lasa gol pentru promptul standard."
        ),
        "dialog.ai_translation_extra_prompt_title": "Instructiuni Traducere AI",
        "dialog.ai_translation_extra_prompt_label": (
            "Reguli suplimentare optionale de traducere de adaugat la promptul AI. Lasa gol pentru promptul standard."
        ),
        "dialog.character_discovery_extra_prompt_title": "Instructiuni Descoperire Personaje",
        "dialog.character_discovery_extra_prompt_label": (
            "Reguli suplimentare optionale pentru Descoperirea Personajelor de adaugat la promptul AI. Lasa gol pentru promptul standard."
        ),
        "dialog.narator_profile_generation_extra_prompt_title": "Instructiuni Profil Narator",
        "dialog.narator_profile_generation_extra_prompt_label": (
            "Reguli suplimentare optionale pentru profilurile Narator de adaugat la promptul AI. Lasa gol pentru promptul standard."
        ),
        "dialog.speech_blocks_extra_prompt_title": "Instructiuni Blocuri de Vorbire",
        "dialog.speech_blocks_extra_prompt_label": (
            "Reguli suplimentare optionale pentru Blocurile de vorbire de adaugat la promptul AI. Lasa gol pentru promptul standard."
        ),
        "dialog.confirm_project_options_title": "Blocheaza Optiunile Proiectului",
        "dialog.operation_progress_title": "{operation_name} In Curs",
        "dialog.operation_progress_cancel": "Anuleaza Operatia",
        "dialog.operation_progress_token_usage": "Tokeni intrare: {input_tokens} | Tokeni iesire: {output_tokens} | Total: {total_tokens}",
        "dialog.operation_progress_token_usage_unavailable": "Utilizarea tokenilor nu a fost raportata de backend.",
        "about.subtitle": "Transforma cuvintele scrise intr-o experienta audio reala!",
        "about.version": "Versiune: {version}",
        "about.license": "Licenta",
        "about.details": "Ing. Dipl. Dan Dumitru Pasare\npasaredan1979@gmail.com",
        "dialog.help_error_title": "Ajutor",
        "help.missing_file": "Fisierul de ajutor offline nu a fost gasit. Reinstaleaza AudioMancer sau deschide dosarul UserGuide din pachetul de documentatie.",
        "help.open_failed": "AudioMancer nu a putut deschide fisierul de ajutor:\n{path}",
        "status.stop_ai": "Opreste AI",
        "status.stage_prefix": "Etapa",
        "status.idle": "inactiva",
        "status.saved_settings": "Setarile au fost salvate.",
        "status.saved_ai_settings": "Setarile AI au fost salvate.",
        "status.saved_tts_settings": "Setarile TTS au fost salvate.",
        "status.project_created": "Proiectul a fost creat.",
        "status.project_opened": "Proiectul a fost deschis.",
        "status.project_repaired": "Proiectul a fost reparat si deschis.",
        "status.project_options_locked": "Optiunile audiobook ale proiectului au fost blocate.",
        "status.source_imported": "Fisierul sursa a fost importat.",
        "status.project_exported": "Exportul a fost salvat.",
        "status.project_snapshot_exported": "Snapshotul ZIP al proiectului a fost salvat.",
        "status.project_snapshot_cancelled": "Exportul snapshotului ZIP al proiectului a fost anulat.",
        "status.text_extracted": "Textul a fost extras.",
        "status.text_cleaned": "Textul a fost curatat.",
        "status.cleaned_text_saved": "Textul curatat a fost salvat.",
        "status.text_ai_cleaned": "Curatarea asistata de AI a fost finalizata.",
        "status.ai_cleanup_spacing_applied": "Spatierea curatarii AI a fost aplicata.",
        "status.cleanup_reset": "Curatarea si toate rezultatele ulterioare au fost resetate.",
        "status.text_chunked": "Textul a fost segmentat.",
        "status.text_ai_chunked": "Textul a fost segmentat cu AI.",
        "status.chunk_saved": "Segmentul a fost salvat.",
        "status.chunk_inserted": "Segmentul a fost inserat.",
        "status.chunk_deleted": "Segmentul a fost sters.",
        "status.text_translated": "Textul a fost tradus.",
        "status.translation_reset": "Traducerea a fost resetata.",
        "status.characters_discovered": "Descoperirea personajelor a fost finalizata.",
        "status.speech_blocks_generated": "Blocurile de vorbire au fost generate.",
        "status.speech_blocks_reset": "Blocurile de vorbire au fost resetate.",
        "status.speech_blocks_approved_all": "Toate blocurile de vorbire au fost aprobate.",
        "status.speech_block_saved": "Blocul de vorbire a fost salvat.",
        "status.speech_block_approved": "Blocul de vorbire a fost aprobat.",
        "status.speech_block_unapproved": "Blocul de vorbire a fost dezaprobat.",
        "status.speech_block_inserted": "Blocul de vorbire a fost inserat.",
        "status.speech_block_deleted": "Blocul de vorbire a fost sters.",
        "status.speech_blocks_resplit": "Resegmentarea segmentului selectat a fost finalizata.",
        "status.audio_blocks_generated": "Blocurile audio au fost generate.",
        "status.audio_blocks_reset": "Blocurile audio au fost resetate.",
        "status.audio_blocks_approved_all": "Toate blocurile audio generate au fost aprobate.",
        "status.audio_block_approved": "Blocul audio a fost aprobat.",
        "status.audio_block_unapproved": "Blocul audio a fost dezaprobat.",
        "status.audio_block_regenerated": "Blocul audio a fost regenerat.",
        "status.character_discovery_reset": "Descoperirea personajelor a fost resetata.",
        "status.character_added": "Personajul a fost adaugat.",
        "status.character_saved": "Modificarile personajului au fost salvate.",
        "status.character_deleted": "Personajul a fost sters.",
        "status.theme_imported": "Tema a fost importata.",
        "status.theme_exported": "Tema a fost exportata.",
        "status.theme_deleted": "Tema a fost stearsa.",
        "status.operation_cancelled": "Operatia a fost anulata.",
        "sidebar.home": "Acasa / Proiect",
        "sidebar.text_cleanup": "Curatare Text",
        "sidebar.text_chunking": "Segmentare Text",
        "sidebar.ai_translation": "Traducere AI",
        "sidebar.characters": "Personaje",
        "sidebar.narator_voice": "Voce Narator",
        "sidebar.character_voices": "Voci Personaje",
        "sidebar.speech_blocks": "Blocuri Vorbire",
        "sidebar.audio_blocks": "Blocuri Audio",
        "sidebar.audio_assembly": "Asamblare Audio",
        "settings.language": "Limba",
        "settings.play_beep": "Reda semnalul sonor la finalizare",
        "settings.scroll_steps": "Pasi derulare",
        "settings.cancel": "Anuleaza",
        "settings.apply": "Aplica",
        "settings.ok": "OK",
        "settings.save": "OK",
        "settings.scale.very_small": "Foarte Mic",
        "settings.scale.small": "Mic",
        "settings.scale.normal": "Normal",
        "settings.scale.large": "Mare",
        "settings.scale.very_large": "Foarte Mare",
        "settings.theme_group": "Tema",
        "settings.theme": "Tema",
        "settings.theme_new": "Noua",
        "settings.theme_duplicate": "Duplica",
        "settings.theme_delete": "Sterge",
        "settings.theme_import": "Importa Tema",
        "settings.theme_export": "Exporta Tema",
        "settings.theme_import_failed": "Importul temei a esuat.",
        "settings.theme_export_failed": "Exportul temei a esuat.",
        "settings.theme_import_too_large": "Fisierul temei este mai mare decat limita de 256 KB.",
        "settings.theme_imported": "Tema importata: {theme_name}.",
        "settings.theme_exported": "Tema exportata in {path}.",
        "settings.theme_name": "Nume",
        "settings.theme_font_family": "Familie font UI",
        "settings.theme_text_font_family": "Familie font text",
        "settings.theme_font_size": "Marime font UI",
        "settings.theme_text_font_size": "Marime font text",
        "settings.theme_colors": "Culori",
        "settings.theme_preview": "Previzualizare",
        "settings.theme_preview_label": "Text exemplu",
        "settings.theme_preview_input": "Fereastra text exemplu",
        "settings.theme_preview_button": "Buton exemplu",
        "settings.theme_preview_status": "Gata",
        "settings.theme_builtin_readonly": "Temele incluse pot fi doar citite.",
        "settings.theme_color_window_background": "Fundal fereastra",
        "settings.theme_color_panel_background": "Fundal panou",
        "settings.theme_color_text_primary": "Text principal",
        "settings.theme_color_text_muted": "Text secundar",
        "settings.theme_color_accent": "Accent",
        "settings.theme_color_border": "Chenar",
        "settings.theme_color_success": "Succes",
        "settings.theme_color_warning": "Avertizare",
        "settings.theme_color_danger": "Pericol",
        "settings.theme_color_disabled": "Dezactivat",
        "settings.theme_color.window_background": "Fundal fereastra",
        "settings.theme_color.panel_background": "Fundal panou",
        "settings.theme_color.text_primary": "Text principal",
        "settings.theme_color.text_muted": "Text secundar",
        "settings.theme_color.accent": "Accent",
        "settings.theme_color.border": "Chenar",
        "settings.theme_color.success": "Succes",
        "settings.theme_color.warning": "Avertizare",
        "settings.theme_color.danger": "Pericol",
        "settings.theme_color.disabled": "Dezactivat",
        "ai_settings.title": "Setari AI",
        "ai_settings.profile_name": "Nume Profil",
        "ai_settings.profile_enabled": "Profil activ",
        "ai_settings.backend_kind": "Tip Backend",
        "ai_settings.base_url": "URL Baza",
        "ai_settings.api_key": "Cheie API",
        "ai_settings.model_name": "Nume Model",
        "ai_settings.context_window": "Fereastra Context",
        "ai_settings.max_output_tokens": "Tokeni Maximi Iesire",
        "ai_settings.timeout": "Timeout (s)",
        "ai_settings.temperature": "Temperatura",
        "ai_settings.structured_output": "Iesire structurata",
        "ai_settings.default_cleanup": "Profil implicit pentru curatare",
        "ai_settings.default_chunking": "Profil implicit pentru segmentare",
        "ai_settings.default_translation": "Profil implicit pentru traducere",
        "ai_settings.default_narrator_generation": "Profil implicit generare narator",
        "ai_settings.default_speech_blocks": "Profil implicit pentru blocuri de vorbire",
        "ai_settings.default_strategy": "Strategie implicita de segmentare AI",
        "ai_settings.default_context_mode": "Mod context segmentare",
        "ai_settings.context_mode_balanced": "Echilibrat",
        "ai_settings.context_mode_wide_scene": "Context scena extins",
        "ai_settings.context_mode_maximum": "Context maxim",
        "ai_settings.default_character": "Profil implicit pentru extragerea personajelor",
        "ai_settings.none": "(niciunul)",
        "ai_settings.add_profile": "Adauga Profil",
        "ai_settings.remove_profile": "Sterge Profil",
        "ai_settings.connect": "Conecteaza",
        "ai_settings.cancel": "Anuleaza",
        "ai_settings.save": "Salveaza",
        "ai_settings.ok": "OK",
        "ai_settings.no_profiles": "(fara profiluri)",
        "ai_settings.not_connected": "Nu este conectat inca.",
        "ai_settings.connection_status": "Stare conexiune",
        "ai_settings.connection_failed": "Conexiune esuata",
        "ai_settings.popup_success_title": "Conectare Reusita",
        "ai_settings.popup_failure_title": "Conectare Esuata",
        "ai_settings.popup_discovered_models": "Modele descoperite",
        "ai_settings.popup_success_message": "Conectare reusita.",
        "ai_settings.popup_failure_message": "Conectarea a esuat.",
        "tts_settings.runtime_group": "Runtime VoiceWeaver",
        "tts_settings.base_url": "URL Baza",
        "tts_settings.api_key": "Cheie API",
        "tts_settings.test_connection": "Testeaza Conexiunea",
        "tts_settings.models_group": "Modele Descoperite",
        "tts_settings.no_models": "Nu au fost descoperite modele inca.",
        "tts_settings.active_model_marker": "activ",
        "tts_settings.not_connected": "Neconectat",
        "tts_settings.connected": "Conectat",
        "tts_settings.connection_failed": "Conectare esuata",
        "tts_settings.plan_group": "Limite Audio Runtime",
        "tts_settings.voice_assignment": "Mod Alocare Voci",
        "tts_settings.voice_assignment_same_narrator": "Acelasi narator pentru toata cartea",
        "tts_settings.voice_assignment_with_characters": "Narator + voci personaje",
        "tts_settings.preview_timeout": "Timeout Preview Audio (s)",
        "tts_settings.generation_timeout": "Timeout Generare Audio (s)",
        "tts_settings.preview_text_limit": "Limita Text Previzualizare (caractere)",
        "tts_settings.scene_ambience_enabled": "Generare Ambienta Scena",
        "tts_settings.scene_ambience_placement": "Pozitionare Ambienta Scena",
        "tts_settings.scene_ambience_duration": "Durata Max Secventa Ambienta (s)",
        "tts_settings.scene_ambience_max_blocks": "Nr. Max Blocuri Ambienta",
        "tts_settings.scene_ambience_guidance": "Ghidaj Ambienta Scena",
        "tts_settings.scene_ambience_steps": "Pasi Ambienta Scena",
        "tts_settings.scene_ambience_seed": "Seed Ambienta Scena",
        "tts_settings.scene_ambience_placement_none": "Fara",
        "tts_settings.scene_ambience_placement_openers_and_closers": "Deschideri si inchideri",
        "tts_settings.scene_ambience_placement_openers_closers_and_scene_changes": (
            "Deschideri, inchideri si schimbari de scena"
        ),
        "tts_settings.plan_no_project": "Limitele audio runtime sunt globale si se aplica la previzualizare si generare.",
        "tts_settings.plan_probe_required": "Testeaza mai intai conexiunea VoiceWeaver pentru ca AudioMancer sa poata verifica modelele Qwen3 TTS necesare.",
        "tts_settings.plan_missing_qwen": "Capabilitatile Qwen3 TTS necesare lipsesc: {missing_capabilities}.",
        "tts_settings.plan_ready": "Capabilitatile Qwen3 base si Voice Designer necesare sunt disponibile.",
        "tts_settings.cancel": "Anuleaza",
        "tts_settings.save": "Salveaza",
        "tts_settings.ok": "OK",
        "tts_settings.popup_success_title": "Conectare Reusita",
        "tts_settings.popup_failure_title": "Conectare Esuata",
        "tts_settings.popup_discovered_models": "Modele descoperite",
        "tts_settings.popup_success_message": "Conectare reusita.",
        "tts_settings.popup_failure_message": "Conectarea a esuat.",
        "text_cleanup.title": "Curatare Text",
        "text_cleanup.extract": "Extrage Textul",
        "text_cleanup.clean": "Curatare Determinista",
        "text_cleanup.ai_profile": "Profil AI",
        "text_cleanup.ai_clean": "Curatare Asistata de AI",
        "text_cleanup.reset": "Reseteaza Curatarea",
        "text_cleanup.edit_cleaned": "Editeaza",
        "text_cleanup.save_cleaned": "Salveaza",
        "text_cleanup.spacing_label": "Insereaza linie noua pentru:",
        "text_cleanup.spacing_heading": "Titlu",
        "text_cleanup.spacing_separator": "Separator",
        "text_cleanup.spacing_noise": "Zgomot",
        "text_cleanup.spacing_header": "Antet",
        "text_cleanup.spacing_footer": "Subsol",
        "text_cleanup.apply_spacing": "Aplica Spatierea",
        "text_cleanup.find": "Cauta",
        "text_cleanup.find_next": "Cauta Urmatorul",
        "text_cleanup.find_title": "Cauta Text",
        "text_cleanup.find_prompt": "Text de cautat:",
        "text_cleanup.find_not_found": "Nu s-a gasit niciun rezultat pentru '{search_text}'.",
        "text_cleanup.extracted_group": "Previzualizare Text Extras",
        "text_cleanup.cleaned_group": "Previzualizare Text Curatat",
        "text_cleanup.status_group": "Stare Curatare",
        "text_cleanup.extracted_note": "Textul extras brut va aparea aici dupa procesarea sursei.",
        "text_cleanup.cleaned_note": "Rezultatul curatarii deterministe sau asistate de AI va aparea aici.",
        "text_cleanup.notes_text": "Importa o sursa pentru a incepe extragerea textului.\nCuratarea determinista si cea asistata de AI nu sunt inca conectate.",
        "text_cleanup.note_no_project": "Creeaza sau deschide un proiect pentru a incepe extragerea textului.",
        "text_cleanup.note_no_source": "Importa un fisier sursa pentru a incepe extragerea.",
        "text_cleanup.note_ready": "Extragerea este pregatita pentru fisierul sursa curent.",
        "text_cleanup.note_resume": "O extragere anterioara nu a fost finalizata. Apasa Extrage Textul pentru a continua de la progresul {progress_current}/{progress_total}.",
        "text_cleanup.note_report_summary": "Au fost extrase {word_count} cuvinte pe {line_count} linii. Pagini: {page_count}.",
        "text_cleanup.note_rerun_warning": "Rularea extragerii din nou va inlocui datele actuale de extragere si va reseta toate datele pasilor urmatori.",
        "text_cleanup.note_extraction_invalid": "Datele extragerii sunt incompatibile. Foloseste Reseteaza Extragerea inainte de a continua.",
        "text_cleanup.note_cleanup_ready": "Curatarea determinista este pregatita pentru textul extras curent.",
        "text_cleanup.note_cleanup_resume": "O curatare anterioara nu a fost finalizata. Apasa Curatare Determinista pentru a continua de la progresul {progress_current}/{progress_total}.",
        "text_cleanup.note_cleanup_summary": "Curatarea a produs {paragraph_count} paragrafe, a eliminat {removed_line_count} linii si a detectat {chapter_count} titluri de capitol sau scena.",
        "text_cleanup.note_page_break_metadata": "Curatarea salturilor de pagina a reparat {page_break_repair_count} continuari si a pastrat {weak_boundary_count} limite cu incredere scazuta.",
        "text_cleanup.note_cleanup_rerun_warning": "Rularea curatarii deterministe din nou va inlocui datele actuale de curatare si va reseta segmentarea plus toti pasii urmatori.",
        "text_cleanup.note_ai_cleanup_ready": "Curatarea asistata de AI este pregatita pentru textul extras curent si profilul AI selectat.",
        "text_cleanup.note_ai_cleanup_continue": "Apasa Curatare Asistata de AI pentru a continua prefixul validat folosind setarile profilului curent.",
        "text_cleanup.note_ai_cleanup_invalid": "Documentul AI Cleanup este invalid sau apartine altei surse. Foloseste Reseteaza Curatarea inainte de o noua pornire.",
        "text_cleanup.note_ai_cleanup_resume": "O curatare asistata de AI anterioara nu a fost finalizata. Apasa Curatare Asistata de AI pentru a continua.",
        "text_cleanup.note_ai_cleanup_summary": "Curatarea asistata de AI a produs {paragraph_count} paragrafe, a eliminat {removed_line_count} unitati si a detectat {chapter_count} titluri de capitol sau scena.",
        "text_cleanup.note_ai_cleanup_profile": "Curatarea AI a folosit profilul: {profile_label}.",
        "text_cleanup.note_ai_cleanup_review_warning": "Curatarea asistata de AI s-a incheiat cu avertizari de validare. Revizuieste textul curatat inainte de segmentare.",
        "text_cleanup.note_ai_cleanup_rerun_warning": "Rularea curatarii asistate de AI din nou va inlocui datele actuale de curatare si va reseta segmentarea plus toti pasii urmatori.",
        "text_chunking.title": "Segmentare Text",
        "text_chunking.ai_profile": "Profil AI",
        "text_chunking.ai_strategy": "Strategie AI",
        "text_chunking.chunk": "Segmentare Determinista",
        "text_chunking.ai_chunk": "Segmentare Asistata de AI",
        "text_chunking.cleaned_group": "Referinta Text Curatat",
        "text_chunking.chunk_list_group": "Lista Segmentelor",
        "text_chunking.selected_group": "Segment Selectat",
        "text_chunking.insert_chunk": "Insereaza",
        "text_chunking.delete_chunk": "Sterge",
        "text_chunking.edit_chunk": "Editeaza",
        "text_chunking.save_chunk": "Salveaza",
        "text_chunking.find": "Cauta",
        "text_chunking.find_next": "Cauta Urmatorul",
        "text_chunking.find_title": "Cauta Text",
        "text_chunking.find_prompt": "Text de cautat:",
        "text_chunking.find_not_found": "Nu s-a gasit niciun rezultat pentru '{search_text}'.",
        "text_chunking.status_group": "Stare Segmentare",
        "text_chunking.cleaned_note": "Textul curatat va aparea aici si va servi drept referinta pentru segmentare.",
        "text_chunking.selected_note": "Textul complet al segmentului selectat va aparea aici.",
        "text_chunking.notes_text": "Ruleaza curatarea inainte de segmentare.\nSegmentarea determinista va popula lista segmentelor si previzualizarea selectiei.",
        "text_chunking.note_no_project": "Creeaza sau deschide un proiect pentru a incepe segmentarea textului.",
        "text_chunking.note_no_source": "Importa un fisier sursa si finalizeaza curatarea inainte de segmentare.",
        "text_chunking.note_missing_cleanup": "Ruleaza curatarea determinista sau asistata de AI inainte de segmentare.",
        "text_chunking.note_ready": "Segmentarea determinista este pregatita pentru textul curatat curent.",
        "text_chunking.note_in_progress": "Segmentarea determinista este in curs la progresul {progress_current}/{progress_total}.",
        "text_chunking.note_resume": "O rulare anterioara de segmentare nu a fost finalizata. Apasa Segmentare Determinista pentru a relua de la punctul salvat.",
        "text_chunking.note_summary": "Segmentarea a produs {chunk_count} segmente si a detectat {chapter_count} titluri de capitol sau scena.",
        "text_chunking.note_rerun_warning": "Rularea segmentarii deterministe din nou va inlocui datele actuale de segmentare si va reseta traducerea plus toti pasii urmatori.",
        "text_chunking.note_no_ai_profile": "Activeaza cel putin un profil AI in Setari AI pentru a rula segmentarea asistata de AI.",
        "text_chunking.note_ai_ready": "Segmentarea asistata de AI este pregatita pentru textul curatat curent si profilul AI selectat.",
        "text_chunking.note_ai_in_progress": "Segmentarea asistata de AI este in curs la progresul {progress_current}/{progress_total} folosind strategia {strategy}.",
        "text_chunking.note_ai_resume": "O rulare anterioara de segmentare asistata de AI nu a fost finalizata. Apasa Segmentare Asistata de AI pentru a relua de la punctul salvat folosind strategia {strategy}.",
        "text_chunking.note_ai_summary": "Segmentarea asistata de AI a produs {chunk_count} segmente, a detectat {chapter_count} titluri de capitol sau scena si a folosit strategia {strategy}.",
        "text_chunking.note_ai_rerun_warning": "Rularea segmentarii asistate de AI din nou va inlocui datele actuale de segmentare si va reseta traducerea plus toti pasii urmatori.",
        "ai_translation.title": "Traducere AI",
        "ai_translation.original_language": "Limba Originala",
        "ai_translation.target_language": "Limba Tinta",
        "ai_translation.ai_profile": "Profil AI",
        "ai_translation.chunk_list_group": "Lista Segmentelor",
        "ai_translation.status_group": "Stare Traducere",
        "ai_translation.start": "Porneste Traducerea",
        "ai_translation.reset": "Reseteaza Traducerea",
        "ai_translation.approve_all": "Aproba Tot",
        "ai_translation.original_group": "Segment Original",
        "ai_translation.translated_group": "Segment Tradus",
        "ai_translation.approved_chunks": "Segmente aprobate: 0/0",
        "ai_translation.retranslate": "Retradu Segmentul Selectat",
        "ai_translation.approve_selected": "Aproba Selectia",
        "ai_translation.source_note": "Segmentul sursa selectat din lista va aparea aici.",
        "ai_translation.translated_note": "Textul tradus pentru segmentul selectat va aparea aici.",
        "ai_translation.note_no_project": "Creeaza sau deschide un proiect pentru a incepe traducerea AI.",
        "ai_translation.note_no_source": "Importa un fisier sursa si finalizeaza segmentarea inainte de traducere.",
        "ai_translation.note_missing_chunking": "Ruleaza segmentarea determinista sau asistata de AI inainte de traducere.",
        "ai_translation.note_no_profile": "Activeaza cel putin un profil AI in Setari AI pentru a rula traducerea AI.",
        "ai_translation.note_ready": "Traducerea AI este pregatita pentru setul curent de segmente si limba tinta selectata.",
        "ai_translation.note_in_progress": "Traducerea AI este in curs la progresul {progress_current}/{progress_total}.",
        "ai_translation.note_resume": "O rulare anterioara de traducere nu a fost finalizata. Apasa Porneste Traducerea pentru a continua de la progresul {progress_current}/{progress_total}.",
        "ai_translation.note_approval_pending": "Traducerea este generata. Revizuieste si aproba fiecare segment inainte de a continua.",
        "ai_translation.note_completed_locked": "Traducerea este complet aprobata. Reseteaza Traducerea pentru a schimba limba sau a porni din nou.",
        "ai_translation.note_summary": "Segmente traduse: {translated_count}/{total_count}. Segmente aprobate: {approved_count}/{total_count}.",
        "ai.note_token_usage_summary": "Tokeni intrare: {input_tokens} | Tokeni iesire: {output_tokens} | Total: {total_tokens}",
        "ai.note_token_usage_unavailable": "Utilizarea tokenilor nu a fost raportata de backend.",
        "characters.title": "Personaje",
        "characters.ai_profile": "Profil AI",
        "characters.start": "Porneste Descoperirea",
        "characters.reset": "Reseteaza Descoperirea",
        "characters.add_character": "Adauga Personaj",
        "characters.edit_character": "Editeaza Personajul",
        "characters.save_character": "Salveaza Personajul",
        "characters.delete_character": "Sterge Personajul",
        "characters.prompt_save": "Salveaza",
        "characters.prompt_discard": "Renunta",
        "characters.prompt_cancel": "Anuleaza",
        "characters.summary": "Ruleaza segmentarea textului inainte de descoperirea personajelor.",
        "characters.list_group": "Lista Personajelor",
        "characters.profile_group": "Profil Personaj",
        "characters.evidence_group": "Dovezi",
        "characters.status_group": "Stare Descoperire Personaje",
        "characters.canonical_name": "Nume Canonic",
        "characters.aliases": "Aliasuri",
        "characters.gender_hint": "Indicatie Gen",
        "characters.gender_confidence": "Incredere Gen",
        "characters.age_hint": "Indicatie Varsta",
        "characters.age_confidence": "Incredere Varsta",
        "characters.voice_definition_prompt": "Prompt Definitie Vocala",
        "characters.confidence": "Incredere",
        "characters.evidence_note": "Fragmentul de dovada selectat din sursa va aparea aici.",
        "characters.find": "Cauta",
        "characters.find_next": "Cauta Urmatorul",
        "characters.find_title": "Cauta Text",
        "characters.find_prompt": "Text de cautat:",
        "characters.find_not_found": "Nu s-a gasit niciun rezultat pentru '{search_text}'.",
        "characters.note_no_project": "Creeaza sau deschide un proiect pentru a incepe descoperirea personajelor.",
        "characters.note_no_source": "Importa un fisier sursa si finalizeaza segmentarea inainte de descoperirea personajelor.",
        "characters.note_missing_chunking": "Ruleaza segmentarea determinista sau asistata de AI inainte de descoperirea personajelor.",
        "characters.note_no_profile": "Activeaza cel putin un profil AI in Setari AI pentru a rula descoperirea personajelor.",
        "characters.note_ready": "Descoperirea personajelor este pregatita pentru setul curent de segmente si profilul AI selectat.",
        "characters.note_in_progress": "Descoperirea personajelor este in curs la progresul {progress_current}/{progress_total}.",
        "characters.note_resume": "O rulare anterioara de descoperire a personajelor nu a fost finalizata. Apasa Porneste Descoperirea pentru a continua de la progresul {progress_current}/{progress_total}.",
        "characters.note_completed_locked": "Descoperirea personajelor este finalizata. Reseteaza Descoperirea pentru a porni din nou cu setul curent de segmente.",
        "characters.note_summary": "Au fost descoperite {character_count} personaje vorbitoare in {analyzed_window_count} ferestre de analiza.",
        "characters.note_rerun_replaces_manual": "O noua rulare de descoperire inlocuieste lista curenta de personaje, inclusiv adaugarile si stergerile manuale.",
        "narator_voice.title": "Voce Narator",
        "narator_voice.profiles_group": "Voci Narator",
        "narator_voice.designer_group": "Prompt Designer Voce",
        "narator_voice.preview_group": "Text Previzualizare",
        "narator_voice.status_group": "Stare Voce Narator",
        "narator_voice.ai_profile": "Profil AI",
        "narator_voice.language_unknown": "Necunoscuta",
        "narator_voice.language_not_translated": "Netradusa",
        "narator_voice.create_profile": "Creeaza",
        "narator_voice.edit_profile": "Editeaza",
        "narator_voice.save_profile": "Salveaza",
        "narator_voice.delete_profile": "Sterge",
        "narator_voice.select_profile": "Selecteaza",
        "narator_voice.generate_sample": "Genereaza Sample",
        "narator_voice.import_sample": "Import Sample",
        "narator_voice.generate_profiles": "Genereaza Naratori",
        "narator_voice.preview": "Reda",
        "narator_voice.stop_preview": "Opreste",
        "narator_voice.custom_profiles_group_header": "Profiluri personalizate",
        "narator_voice.preview_budget": "Buget previzualizare: {word_count}/{safe_word_count} cuvinte sigure",
        "narator_voice.list_selected": "Selectat",
        "narator_voice.profile_kind_preset": "Preset",
        "narator_voice.profile_kind_custom": "Personalizat",
        "narator_voice.note_no_project": "Creeaza sau deschide un proiect inainte de a defini profilurile vocii naratorului.",
        "narator_voice.note_no_source": "Importa un document sursa inainte de a defini vocea naratorului.",
        "narator_voice.note_runtime_not_connected": "Deschide Setari TTS si ruleaza Testeaza Conexiunea pentru a descoperi modelele VoiceWeaver pentru acest proiect.",
        "narator_voice.note_no_profiles": "Nu exista profiluri de voce narator stocate pentru proiectul curent.",
        "narator_voice.note_qwen_capabilities_ready": "Capabilitatile minime Qwen3 TTS sunt disponibile pentru generarea sample-urilor vocii naratorului.",
        "narator_voice.note_qwen_capabilities_missing": "Capabilitatile minime Qwen3 TTS lipsesc: {missing_capabilities}.",
        "narator_voice.note_upstream_not_ready": "Descoperirea personajelor nu este finalizata inca, dar profilurile vocii naratorului pot fi pregatite deja local.",
        "narator_voice.note_no_selected_profile": "Selecteaza un profil de voce narator inainte de a pregati vocile personajelor.",
        "narator_voice.note_selected_profile": "Profil {profile_kind} selectat: {profile_name}.",
        "narator_voice.note_selected_profile_missing_sample": "Naratorul selectat are nevoie de un sample generat inainte sa poata fi previzualizat sau refolosit la naratie.",
        "narator_voice.note_selected_profile_runtime_missing": "Sample-ul naratorului selectat face referire la un model care nu este raportat de runtime-ul VoiceWeaver curent.",
        "narator_voice.note_generate_sample_required": "Genereaza un sample pentru profilul inspectat inainte sa il previzualizezi sau sa il selectezi.",
        "narator_voice.note_profile_runtime_missing": "Acest sample stocat face referire la un model care nu este raportat momentan de VoiceWeaver.",
        "narator_voice.error_invalid_profile_name": "Introdu un nume pentru profilul naratorului inainte de a crea sau salva un profil personalizat.",
        "narator_voice.error_duplicate_profile_name": "Un profil de narator cu acest nume exista deja in proiectul curent.",
        "narator_voice.error_readonly_profile": "Acest profil de narator nu poate fi editat.",
        "narator_voice.error_missing_preview_text": "Introdu un text de previzualizare inainte de a genera sample-ul naratorului.",
        "narator_voice.error_missing_sample": "Genereaza un sample pentru acest profil de narator inainte sa il selectezi sau sa il previzualizezi.",
        "narator_voice.error_runtime_model_missing": "Modelul TTS necesar pentru acest profil de narator nu este raportat de runtime-ul VoiceWeaver curent.",
        "narator_voice.error_qwen_capabilities_missing": "Nu se poate genera sample-ul naratorului deoarece lipsesc capabilitatile Qwen3 TTS necesare: {missing_capabilities}.",
        "narator_voice.error_generation_missing_audio": "VoiceWeaver a terminat cererea, dar nu a raportat niciun fisier audio disponibil pentru descarcare.",
        "narator_voice.error_preview_text_over_budget": "Textul de previzualizare este prea lung pentru limita runtime-ului TTS activ ({word_count} cuvinte, limita sigura {safe_word_count}). Scurteaza textul de previzualizare inainte de a genera un sample.",
        "narator_voice.status_runtime_connected": "Runtime: conectat",
        "narator_voice.status_runtime_not_connected": "Runtime: neconectat",
        "narator_voice.status_active_model": "Model activ: {model_id}",
        "narator_voice.status_active_model_none": "Model activ: niciunul",
        "narator_voice.status_preview_budget": "Buget previzualizare: {word_count}/{safe_word_count} cuvinte sigure",
        "narator_voice.status_profile_count": "Profiluri: {profile_count}",
        "narator_voice.status_sample_count": "Profiluri cu sample: {sample_count}",
        "narator_voice.status_selected_count": "Profiluri selectate: {selected_count}",
        "narator_voice.status_qwen_ready": "Stare Qwen3 TTS: pregatit",
        "narator_voice.status_qwen_missing": "Stare Qwen3 TTS: lipsesc {missing_capabilities}",
        "dialog.narator_voice_create_title": "Creeaza Profil Voce Narator",
        "dialog.narator_voice_create_prompt": "Introdu numele afisat pentru noul profil personalizat de voce narator:",
        "dialog.narator_voice_delete_title": "Sterge Profilul Vocii Naratorului",
        "dialog.narator_voice_delete_message": "Stergi profilul personalizat de voce narator selectat din proiectul curent?",
        "dialog.narator_voice_edit_title": "Editeaza Profilul Vocii Naratorului",
        "dialog.narator_voice_edit_message": "Continuarea va sterge sample-ul audio curent. Va trebui sa generezi un sample nou inainte ca acest profil sa poata fi selectat din nou. Continui?",
        "dialog.narator_voice_generate_sample_title": "Genereaza Sample Voce Narator",
        "dialog.narator_voice_generate_sample_message": "AudioMancer va contacta runtime-ul TTS configurat si conexiunea trebuie testata inainte din Setari TTS. Continui?",
        "dialog.narator_voice_generate_sample_message_replace": "Continuarea va sterge sample-ul audio curent, iar AudioMancer va contacta runtime-ul TTS configurat. Conexiunea trebuie testata inainte din Setari TTS. Continui?",
        "dialog.voice_sample_import_title": "Import Sample",
        "dialog.voice_sample_import_filter": "Fisiere audio WAV (*.wav)",
        "dialog.voice_sample_text_title": "Text Sample",
        "dialog.voice_sample_text_prompt": "Introdu textul exact rostit in sample-ul importat:",
        "dialog.narator_voice_generate_profiles_title": "Genereaza Profiluri Voce Narator",
        "dialog.narator_voice_generate_profiles_message": "AudioMancer va analiza stilul cartii curente cu profilul AI selectat. Operatia poate dura mult si poate consuma tokeni platiti sau credite. Continui?",
        "dialog.narator_voice_generate_profiles_count_prompt": "Cate profiluri de narator trebuie generate?",
        "progress.narator_voice_sample_prepare": "Se pregateste generarea sample-ului pentru narator...",
        "progress.narator_voice_sample_load_model": "Se incarca modelul pentru generarea vocii...",
        "progress.narator_voice_sample_generate": "Se genereaza sample-ul pentru narator...",
        "progress.narator_voice_sample_download": "Se descarca sample-ul pentru narator...",
        "progress.narator_voice_generate_profiles": "Se genereaza profilurile naratorului...",
        "progress.narator_voice_change_prepare": "Se pregateste schimbarea vocii naratorului...",
        "progress.narator_voice_change_profile": "Se salveaza profilul vocii naratorului...",
        "progress.narator_voice_change_audio_blocks": "Se sterge audio-ul generat afectat...",
        "progress.narator_voice_change_audio_assembly": "Se reseteaza Asamblarea Audio...",
        "progress.narator_voice_change_manifest": "Se salveaza starea fluxului proiectului...",
        "progress.narator_voice_change_refresh": "Se reimprospateaza starea proiectului...",
        "status.narator_voice_profile_created": "Profilul naratorului a fost creat.",
        "status.narator_voice_profile_saved": "Profilul naratorului a fost salvat.",
        "status.narator_voice_profile_deleted": "Profilul naratorului a fost sters.",
        "status.narator_voice_preview_cancelled": "Previzualizarea naratorului a fost anulata.",
        "status.narator_voice_profile_selected": "Profilul naratorului a fost selectat.",
        "status.narator_voice_profiles_imported": "Au fost importate {imported_count} profiluri de model si au fost omise {skipped_count} existente.",
        "status.narator_voice_sample_generated": "Sample-ul naratorului a fost generat.",
        "status.narator_voice_sample_imported": "Sample-ul naratorului a fost importat.",
        "status.narator_voice_profiles_generated": "Au fost generate {generated_count} profiluri de voce narator.",
        "status.narator_voice_language_changed": "Limba vocii audiobookului a fost schimbata. Sample-urile generate si datele ulterioare au fost resetate.",
        "status.character_voices_prompt_saved": "Promptul vocal a fost salvat.",
        "status.character_voices_sample_generated": "Sample-ul personajului a fost generat.",
        "status.character_voices_sample_imported": "Sample-ul personajului a fost importat.",
        "status.character_voices_missing_samples_generated": "Sample-urile personajelor au fost regenerate.",
        "voice_sample_import.error_unsupported_file_type": "Importa un fisier audio WAV.",
        "voice_sample_import.error_missing_file": "Fisierul sample selectat nu a fost gasit.",
        "voice_sample_import.error_invalid_wav": "Fisierul selectat nu este un sample WAV citibil.",
        "voice_sample_import.error_sample_too_short": "Sample-ul importat trebuie sa aiba cel putin {min_duration_seconds:.1f} secunde.",
        "voice_sample_import.error_sample_silent": "Sample-ul importat este silentios sau prea aproape de tacere.",
        "voice_sample_import.error_empty_sample_text": "Introdu textul rostit in sample-ul importat.",
        "voice_sample_import.error_readonly_target": "Importa sample-uri doar pentru tintele de personaj pe aceasta pagina.",
        "character_voices.title": "Voci Personaje",
        "character_voices.list_group": "Tintele Vocii",
        "character_voices.setup_group": "Tinta Vocala",
        "character_voices.prompt_group": "Prompt Designer Voce",
        "character_voices.preview_group": "Text Previzualizare",
        "character_voices.status_group": "Stare Voci Personaje",
        "character_voices.original_language": "Limba originala: {language_label}",
        "character_voices.translated_language": "Limba tradusa: {language_label}",
        "character_voices.assignment_mode": "Alocare voci",
        "character_voices.voice_language": "Limba vocii",
        "character_voices.target_name": "Nume Tinta",
        "character_voices.target_kind": "Tip Tinta",
        "character_voices.target_kind_narrator": "Voce Narator",
        "character_voices.target_kind_character": "Personaj",
        "character_voices.assignment_same_narrator": "Acelasi narator pentru toata cartea",
        "character_voices.assignment_narrator_and_characters": "Narator + voci personaje",
        "character_voices.import_sample": "Import Sample",
        "character_voices.edit_prompt": "Editeaza Promptul Vocal",
        "character_voices.save_prompt": "Salveaza Promptul Vocal",
        "character_voices.generate_sample": "Genereaza Sample",
        "character_voices.generate_missing_samples": "Genereaza Sample-uri Personaje",
        "character_voices.preview": "Previzualizare",
        "character_voices.stop_preview": "Opreste Previzualizarea",
        "character_voices.sample_present": "Sample prezent",
        "character_voices.sample_missing": "Sample lipsa",
        "character_voices.note_no_project": "Creeaza sau deschide un proiect inainte de a pregati vocile personajelor.",
        "character_voices.note_no_source": "Importa un document sursa inainte de a pregati vocile personajelor.",
        "character_voices.note_no_characters": "Finalizeaza Descoperirea Personajelor astfel incat aceasta pagina sa poata lista toate personajele.",
        "character_voices.note_no_selected_narrator": (
            "Selecteaza un profil de voce narator in pagina Voce Narator inainte de a pregati vocile personajelor."
        ),
        "character_voices.note_missing_narrator_sample": (
            "Genereaza sample-ul vocii naratorului selectat in pagina Voce Narator inainte de a pregati vocile "
            "personajelor."
        ),
        "character_voices.note_translation_not_fully_approved": "Limba tradusa va deveni selectabila numai dupa aprobarea tuturor segmentelor traduse.",
        "character_voices.note_same_narrator_mode": "Alocarea vocilor este setata sa foloseasca aceeasi voce a naratorului pentru toata cartea, asa ca prompturile si generarea pentru personaje sunt dezactivate.",
        "character_voices.note_runtime_not_connected": "Deschide Setari TTS si ruleaza Testeaza Conexiunea pentru a verifica VoiceWeaver inainte de a genera sample-uri pentru personaje.",
        "character_voices.note_profile_runtime_missing": "Acest sample stocat face referire la un model care nu este raportat momentan de VoiceWeaver.",
        "character_voices.note_qwen_capabilities_ready": "Capabilitatile minime Qwen3 TTS sunt disponibile pentru generarea sample-urilor personajelor.",
        "character_voices.note_qwen_capabilities_missing": "Capabilitatile minime Qwen3 TTS lipsesc: {missing_capabilities}.",
        "character_voices.error_missing_prompt": "Introdu un prompt designer voce inainte de salvare.",
        "character_voices.error_missing_preview_text": "Introdu un text de previzualizare inainte de salvare sau generarea sample-ului.",
        "character_voices.error_missing_sample": "Nu exista niciun sample stocat pentru tinta inspectata.",
        "character_voices.error_qwen_capabilities_missing": "Sample-ul personajului nu poate fi generat deoarece capabilitatile Qwen3 TTS necesare lipsesc: {missing_capabilities}.",
        "character_voices.error_generation_missing_audio": "VoiceWeaver a terminat cererea, dar nu a raportat niciun audio descarcabil.",
        "speech_blocks.title": "Blocuri Vorbire",
        "speech_blocks.ai_profile": "Profil AI",
        "speech_blocks.generate": "Genereaza Tot",
        "speech_blocks.reset_generation": "Reset",
        "speech_blocks.approve_all": "Aproba Tot",
        "speech_blocks.chunk_list_group": "Lista Segmentelor",
        "speech_blocks.selected_group": "Segment Selectat",
        "speech_blocks.blocks_group": "Blocuri Vorbire",
        "speech_blocks.status_group": "Stare Blocuri Vorbire",
        "speech_blocks.note_no_project": "Creeaza sau deschide un proiect pentru a incepe generarea blocurilor de vorbire.",
        "speech_blocks.note_no_source": "Importa o sursa si finalizeaza Vocile Personajelor inainte de a genera blocurile de vorbire.",
        "speech_blocks.note_missing_source": "Ruleaza segmentarea textului, rezolva limba din Vocile Personajelor si aproba traducerea daca este necesar inainte de a genera blocurile de vorbire.",
        "speech_blocks.note_no_profile": "Activeaza cel putin un profil AI in Setari AI pentru a rula generarea blocurilor de vorbire.",
        "speech_blocks.note_ready": "Generarea blocurilor de vorbire este pregatita pentru limba curenta din Vocile Personajelor si profilul AI selectat.",
        "speech_blocks.note_in_progress": "Generarea blocurilor de vorbire este in curs la {progress_current}/{progress_total}.",
        "speech_blocks.note_resume": "O rulare anterioara pentru blocurile de vorbire nu a fost finalizata. Apasa Genereaza Blocuri Vorbire pentru a continua de la progresul {progress_current}/{progress_total}.",
        "speech_blocks.note_summary": "Au fost generate {block_count} blocuri de vorbire din {processed_chunk_count}/{total_chunk_count} segmente.",
        "speech_blocks.note_approval_summary": "Blocuri de vorbire aprobate: {approved_block_count}/{total_block_count}.",
        "speech_blocks.note_waiting_for_approval": "Revizuieste si aproba fiecare bloc de vorbire inainte de Blocurile Audio.",
        "speech_blocks.note_ready_for_audio": "Fiecare bloc de vorbire este aprobat. Fluxul este pregatit pentru Blocurile Audio.",
        "speech_blocks.note_warning_summary": "Blocurile de vorbire au inregistrat {warning_count} avertismente care trebuie revizuite.",
        "speech_blocks.note_warning_entry": "{chunk_id}: {reason}",
        "speech_blocks.note_rerun_warning": "Rularea din nou a blocurilor de vorbire va inlocui datele curente si va reseta Blocurile Audio plus Asamblarea Audio.",
        "speech_blocks.detail_speaker": "Vorbitor",
        "speech_blocks.detail_block_id": "ID Bloc",
        "speech_blocks.detail_content_kind": "Tip Continut",
        "speech_blocks.detail_warning_flags": "Marcaje Avertisment",
        "speech_blocks.detail_none": "(niciunul)",
        "speech_blocks.content_narration": "Naratiune",
        "speech_blocks.content_dialogue": "Dialog",
        "speech_blocks.content_scene_ambience": "Ambienta Scena",
        "speech_blocks.content_pause": "Pauza",
        "speech_blocks.content_indication": "Indicatie",
        "speech_blocks.ambient_prompt": "Prompt",
        "speech_blocks.ambient_negative_prompt": "Prompt Negativ",
        "speech_blocks.ambient_duration": "Durata (s)",
        "speech_blocks.insert_block": "Insereaza",
        "speech_blocks.delete_block": "Sterge",
        "speech_blocks.resplit_selected": "Imparte Segment",
        "speech_blocks.edit_block": "Editeaza",
        "speech_blocks.save_block": "Salveaza",
        "speech_blocks.approve_block": "Aproba",
        "speech_blocks.unapprove_block": "Dezaproba",
        "speech_blocks.generate_audio_selected": "Genereaza Audio",
        "speech_blocks.warning_indicator": "Avertisment: {warning_flags}",
        "audio_blocks.title": "Blocuri Audio",
        "audio_blocks.scene_ambience_audio_selector": "Audio Ambienta Scena",
        "audio_blocks.scene_ambience_audio_disabled": "Oprit",
        "audio_blocks.scene_ambience_audio_enabled": "Pornit",
        "audio_blocks.start_generation": "Porneste Generarea Audio",
        "audio_blocks.play_audiobook": "Reda Audiobook",
        "audio_blocks.stop_audiobook": "Opreste Audiobook",
        "audio_blocks.reset_generation": "Reseteaza Generarea Audio",
        "audio_blocks.approve_all": "Aproba Tot",
        "audio_blocks.source_group": "Text Sursa",
        "audio_blocks.blocks_group": "Blocuri Vorbire",
        "audio_blocks.selected_group": "Bloc Selectat",
        "audio_blocks.status_group": "Stare Blocuri Audio",
        "audio_blocks.regenerate_selected": "Regenereaza Audio",
        "audio_blocks.play_selected": "Reda",
        "audio_blocks.stop_playback": "Opreste",
        "audio_blocks.approve_selected": "Aproba",
        "audio_blocks.unapprove_selected": "Dezaproba",
        "audio_blocks.error_missing_audio": "Blocul Audio selectat nu are un fisier audio generat pentru redare.",
        "audio_blocks.note_no_project": "Creeaza sau deschide un proiect inainte de a genera Blocuri Audio.",
        "audio_blocks.note_no_source": "Importa un document sursa inainte de a genera Blocuri Audio.",
        "audio_blocks.note_missing_speech_blocks": "Genereaza Blocurile de Vorbire inainte de a porni Blocurile Audio.",
        "audio_blocks.note_summary": (
            "Audio generat pentru {generated_count}/{total_count} blocuri de vorbire si aprobat "
            "{approved_count}/{total_count}."
        ),
        "audio_blocks.note_in_progress": ("Generarea audio este in curs la {progress_current}/{progress_total}."),
        "audio_blocks.note_prepare_prompts": (
            "Se pregatesc prompturile vocale reutilizabile. Disponibile: {prompt_count}."
        ),
        "audio_blocks.note_generating_blocks": (
            "Se genereaza blocurile audio din prompturile vocale reutilizabile pregatite."
        ),
        "audio_blocks.note_resume": (
            "O rulare anterioara pentru Blocurile Audio nu a fost finalizata. Apasa Porneste Generarea Audio "
            "pentru a continua de la {progress_current}/{progress_total}."
        ),
        "audio_blocks.note_ready": (
            "Generarea Blocurilor Audio este pregatita pentru Blocurile de Vorbire curente si sample-urile vocale."
        ),
        "audio_blocks.note_waiting_for_approval": (
            "Fiecare bloc de vorbire are audio generat, dar aprobarea este inca necesara inainte de Asamblarea Audio."
        ),
        "audio_blocks.note_ready_for_assembly": (
            "Fiecare bloc de vorbire generat este aprobat. Fluxul este pregatit pentru Asamblarea Audio."
        ),
        "audio_blocks.note_invalidated": (
            "Datele anterioare pentru Blocurile Audio sunt invechite: {invalidation_reason}"
        ),
        "audio_blocks.status_generated": "Audio generat: {generated_count}/{total_count}",
        "audio_blocks.status_approved": "Audio aprobat: {approved_count}/{total_count}",
        "audio_blocks.status_voice_language": "Limba vocii: {language_label}",
        "audio_blocks.status_prompts": "Prompturi reutilizabile: {prompt_count}",
        "audio_blocks.progress_label": "Blocuri generate: {progress_current}/{progress_total}",
        "audio_blocks.detail_speaker": "Vorbitor: {speaker_label}",
        "audio_blocks.detail_approval_status": "Stare: {status_label}",
        "audio_blocks.approval_status_approved": "Aprobat",
        "audio_blocks.approval_status_pending": "In asteptare",
        "audio_blocks.marker_generated": "audio",
        "audio_blocks.marker_missing": "lipsa",
        "audio_blocks.marker_approved": "aprobat",
        "audio_blocks.marker_pending": "in_asteptare",
        "audio_blocks.marker_current": "curent",
        "audio_blocks.duration_seconds": "{duration_seconds:.1f}s",
        "audio_blocks.duration_unknown": "--.-s",
        "character_voices.status_total_targets": "Total tinte: {target_count}",
        "character_voices.status_targets_with_samples": "Tinte cu sample-uri: {sample_count}",
        "character_voices.status_assignment_mode": "Alocare voci: {assignment_mode}",
        "character_voices.status_voice_language": "Limba vocii: {language_label}",
        "character_voices.status_generation_ready": "Pregatire generare: {readiness}",
        "character_voices.readiness_ready": "gata",
        "character_voices.readiness_not_ready": "negata",
        "dialog.character_voices_edit_title": "Editeaza Promptul Vocal",
        "dialog.character_voices_edit_message": "Continuarea va sterge sample-ul curent pentru acest personaj. Va trebui sa generezi un nou sample dupa salvarea promptului editat. Continui?",
        "dialog.character_voices_generate_sample_title": "Genereaza Sample Personaj",
        "dialog.character_voices_generate_sample_message": "AudioMancer va contacta runtime-ul TTS configurat si necesita testarea conexiunii mai intai in Setari TTS. Continui?",
        "dialog.character_voices_generate_sample_message_replace": "Continuarea va sterge sample-ul curent si AudioMancer va contacta runtime-ul TTS configurat. Conexiunea trebuie testata mai intai in Setari TTS. Continui?",
        "dialog.character_voices_generate_missing_samples_title": "Genereaza Sample-uri Personaje",
        "dialog.character_voices_generate_missing_samples_message": "AudioMancer va regenera sample-uri pentru toate cele {sample_count} tinta/tinte curente de personaj. Sample-urile existente ale personajelor vor fi inlocuite. Runtime-ul TTS configurat trebuie sa fie disponibil. Continui?",
        "dialog.character_voices_missing_narrator_sample_title": "Este Necesar Sample-ul Naratorului",
        "dialog.character_voices_missing_narrator_sample_message": (
            "Profilul de voce narator selectat nu are inca un sample generat. Deschide pagina Voce Narator si "
            "genereaza sample-ul vocii naratorului inainte de a pregati vocile personajelor."
        ),
        "progress.character_voices_sample_prepare": "Se pregateste generarea sample-ului personajului...",
        "progress.character_voices_sample_load_model": "Se incarca modelul pentru generarea vocii...",
        "progress.character_voices_sample_generate": "Se genereaza sample-ul personajului...",
        "progress.character_voices_sample_download": "Se descarca sample-ul personajului...",
        "progress.character_voices_batch_prepare": "Se pregateste generarea sample-urilor pentru personaje...",
        "progress.character_voices_batch_target": "Se genereaza sample-ul {current}/{total}: {target_name}",
        "placeholder.character_voices.title": "Voci Personaje",
        "placeholder.character_voices.note": "Pregatirea vocilor personajelor este implementata in aceasta pagina.",
        "placeholder.speech_blocks.title": "Blocuri Vorbire",
        "placeholder.speech_blocks.note": (
            "Acest pas viitor va imparti segmentele fluxului in blocuri TTS atribuite vorbitorilor pe baza "
            "schimbarilor de vorbitor si a limitelor de tokeni TTS."
        ),
        "placeholder.audio_blocks.title": "Blocuri Audio",
        "placeholder.audio_blocks.note": (
            "Acest pas viitor va genera si aproba audio pentru fiecare bloc atribuit vorbitorilor, pastrand "
            "textul original si textul editabil."
        ),
        "placeholder.audio_assembly.title": "Asamblare Audio",
        "placeholder.audio_assembly.note": (
            "Acest pas viitor va asambla blocurile audio aprobate in fisierele finale si va impacheta metadate "
            "precum subtitrari si date despre vorbitori."
        ),
        "audio_assembly.title": "Asamblare Audio",
        "audio_assembly.settings_group": "Setari Iesire",
        "audio_assembly.scene_mix_group": "Previzualizari Mix Scena",
        "audio_assembly.outputs_group": "Fisiere Audiobook Generate",
        "audio_assembly.status_group": "Status Asamblare Audio",
        "audio_assembly.output_mode": "Mod Iesire",
        "audio_assembly.max_duration": "Durata Maxima",
        "audio_assembly.output_format": "Format Iesire",
        "audio_assembly.inter_block_silence": "Pauza Intre Blocuri",
        "audio_assembly.inter_chunk_silence": "Pauza Intre Segmente",
        "audio_assembly.include_scene_ambience": "Include Ambienta Scena",
        "audio_assembly.generate": "Genereaza Audio",
        "audio_assembly.reset": "Reseteaza Asamblarea Audio",
        "audio_assembly.play_audio": "Reda Audio",
        "audio_assembly.generate_scene_mix": "Genereaza / Reimprospateaza Mix Scena",
        "audio_assembly.play_scene_mix": "Reda Mix Scena",
        "audio_assembly.stop_playing": "Opreste Redarea",
        "audio_assembly.rewind_10s": "-10s",
        "audio_assembly.forward_10s": "+10s",
        "audio_assembly.mode.per_chunk": "Pe segment text",
        "audio_assembly.mode.time_limit": "Limita de timp",
        "audio_assembly.mode.whole_book": "Audiobook intreg",
        "audio_assembly.note_no_project": "Creeaza sau deschide un proiect inainte de asamblarea audio.",
        "audio_assembly.note_missing_audio_blocks": "Genereaza si aproba Blocurile Audio inainte de Asamblarea Audio.",
        "audio_assembly.note_missing_approvals": (
            "Aproba fiecare Bloc Audio inainte de Asamblarea Audio. Aprobate: {approved_blocks}/{total_blocks}."
        ),
        "audio_assembly.note_ready": "Asamblarea Audio este gata. Generarea poate fi intrerupta si reluata mai tarziu.",
        "audio_assembly.note_resume": "Asamblarea Audio a fost intrerupta. Apasa Genereaza Audio pentru a continua.",
        "audio_assembly.note_completed": "Asamblarea Audio s-a finalizat. Fisierele generate sunt in dosarul audiobook.",
        "audio_assembly.status_blocks": "Blocuri audio aprobate: {approved_blocks}/{total_blocks}",
        "audio_assembly.status_outputs": "Fisiere de iesire generate: {generated_outputs}/{planned_outputs}",
        "audio_assembly.status_duration": "Durata compusa totala: {duration}",
        "audio_assembly.status_mode": "Mod iesire: {mode}",
        "audio_assembly.error_missing_audio": "Fisierul audiobook selectat lipseste.",
        "audio_assembly.error_missing_scene_mix": "Previzualizarea mixului de scena selectat lipseste.",
        "audio_assembly.output_item": "{file_name} | {duration} | {block_count} blocuri audio",
        "audio_assembly.scene_mix_item": "{label} | {duration} | {block_count} sunete | {status}",
        "audio_assembly.scene_mix_ready": "pregatit",
        "audio_assembly.scene_mix_not_ready": "necesita audio generat",
        "audio_assembly.scene_mix_generated": "previzualizare pregatita",
        "home.title": "Acasa / Proiect",
        "home.summary_group": "Rezumat Proiect",
        "home.exports_group": "Exporturi",
        "home.project": "Proiect",
        "home.path": "Cale",
        "home.stage": "Etapa",
        "home.source": "Sursa",
        "home.audiobook_language": "Limba traducerii: {language_label}",
        "home.narration_mode": "Stil iesire audio: {mode_label}",
        "home.translation_language": "Limba traducerii",
        "home.audio_output_style": "Stil iesire audio",
        "home.options_locked": "Optiunile proiectului sunt blocate. Importul sursei este disponibil.",
        "home.options_unlocked": "Selecteaza fisierul sursa, limba traducerii si stilul audio, apoi apasa Porneste Proiectul.",
        "home.mode_same_narrator": "Acelasi narator pentru toata cartea",
        "home.mode_narrator_and_characters": "Narator + voci de personaje",
        "home.start_project": "Porneste Proiectul",
        "home.none": "niciuna",
        "home.source_import_group": "Import Sursa",
        "home.source_import_note": "Fiecare proiect este legat de exact un fisier sursa. Dupa import, selectia este blocata pentru acel proiect.",
        "home.select_source": "Selecteaza Fisierul Sursa",
        "home.export_project_zip": "Exporta ZIP Proiect",
        "home.no_source": "Nu a fost importata nicio sursa.",
        "home.selected_source_prefix": "Sursa selectata",
        "home.selected_source_suffix": ". Apasa Porneste Proiectul pentru blocare.",
        "home.locked_source_prefix": "Sursa blocata",
        "home.locked_source_suffix": ". Creeaza un proiect nou pentru a folosi alt fisier.",
        "home.export.cleaned_text": "Text Curatat",
        "home.export.text_chunks": "Segmente Text",
        "home.export.ai_translation": "Traducere AI",
        "home.export.characters": "Personaje",
        "home.export.narrator_voice": "Voce Narator",
        "home.export.character_voices": "Voci Personaje",
        "home.export.speech_blocks": "Blocuri Vorbire",
        "home.export.audio_assembly": "Asamblare Audio",
        "home.export_status.available": "Disponibil",
        "home.export_status.not_ready": "Nepregatit",
        "home.export_status.missing_artifact": "Artefact lipsa",
        "home.export_format.txt": "TXT",
        "home.export_format.markdown": "Markdown",
        "home.export_format.zip": "ZIP",
        "home.export_button": "Exporta",
        "home.export_not_ready_message": "Acest export nu este inca disponibil.",
        "home.export_inside_project_message": (
            "Alege o destinatie in afara dosarului proiectului activ pentru a evita suprascrierea fisierelor runtime."
        ),
        "home.snapshot_inside_project_message": (
            "Alege o destinatie ZIP in afara dosarului proiectului activ pentru ca snapshotul sa nu fie arhivat in el insusi."
        ),
        "home.snapshot_active_operation_message": (
            "Exportul ZIP al proiectului este blocat cat timp ruleaza o operatie. Asteapta finalizarea operatiei curente."
        ),
        "home.snapshot_failure_message": "Snapshotul ZIP al proiectului nu a putut fi creat.",
        "home.workflow_group": "Progres Flux de Lucru",
        "home.status.not_started": "Nepornit",
        "home.status.in_progress": "In Curs",
        "home.status.finished": "Finalizat",
        "home.stage_label.source_selected": "Sursa Selectata",
        "home.stage_label.text_cleanup_ready": "Curatare Text",
        "home.stage_label.text_chunking_ready": "Segmentare Text",
        "home.stage_label.translation_ready": "Traducere AI",
        "home.stage_label.character_discovery_ready": "Personaje",
        "home.stage_label.narrator_definition_ready": "Voce Narator",
        "home.stage_label.character_voices_ready": "Voci Personaje",
        "home.stage_label.speech_blocks_ready": "Blocuri Vorbire",
        "home.stage_label.audio_blocks_ready": "Blocuri Audio",
        "home.stage_label.audio_assembly_ready": "Asamblare Audio",
        "home.stage_note.inactive.source_selected": "Creeaza sau deschide mai intai un proiect.",
        "home.stage_note.inactive.text_cleanup_ready": "Creeaza sau deschide mai intai un proiect.",
        "home.stage_note.inactive.text_chunking_ready": "Creeaza sau deschide mai intai un proiect.",
        "home.stage_note.inactive.translation_ready": "Creeaza sau deschide mai intai un proiect.",
        "home.stage_note.inactive.character_discovery_ready": "Creeaza sau deschide mai intai un proiect.",
        "home.stage_note.inactive.narrator_definition_ready": "Creeaza sau deschide mai intai un proiect.",
        "home.stage_note.inactive.character_voices_ready": "Creeaza sau deschide mai intai un proiect.",
        "home.stage_note.inactive.speech_blocks_ready": "Creeaza sau deschide mai intai un proiect.",
        "home.stage_note.inactive.audio_blocks_ready": "Creeaza sau deschide mai intai un proiect.",
        "home.stage_note.inactive.audio_assembly_ready": "Creeaza sau deschide mai intai un proiect.",
        "home.stage_note.active.source_selected": "Selecteaza si importa un singur fisier sursa pentru proiect.",
        "home.stage_note.active.text_cleanup_ready": "Pregateste textul importat pentru segmentare.",
        "home.stage_note.active.text_chunking_ready": "Imparte textul curatat in segmente de lucru.",
        "home.stage_note.active.translation_ready": "Tradu setul de segmente atunci cand este necesar.",
        "home.stage_note.active.character_discovery_ready": "Extrage si revizuieste setul de personaje.",
        "home.stage_note.active.narrator_definition_ready": "Selecteaza si adapteaza profilul vocii naratorului pentru proiect.",
        "home.stage_note.active.character_voices_ready": "Pregateste sample-urile vocale pentru narator si personaje pentru generarea audio ulterioara.",
        "home.stage_note.active.speech_blocks_ready": "Imparte segmentele traduse sau originale in blocuri de vorbire atribuite vorbitorilor.",
        "home.stage_note.active.audio_blocks_ready": "Genereaza si aproba audio pentru fiecare bloc de vorbire.",
        "home.stage_note.active.audio_assembly_ready": "Asambleaza blocurile audio aprobate in livrabilele finale.",
        "project.new_dialog_intro": "Alege dosarul parinte unde va fi creat proiectul si introdu numele exact al proiectului.",
        "project.parent_folder": "Dosar Parinte",
        "project.project_name": "Nume Proiect",
        "project.browse": "Rasfoieste",
        "project.create": "Creeaza",
        "project.cancel": "Anuleaza",
        "project.error_missing_parent": "Selecteaza dosarul parinte in care trebuie creat proiectul.",
        "project.error_missing_name": "Introdu numele exact al proiectului.",
        "project.error_no_active_project": "Creeaza sau deschide un proiect inainte de a importa un fisier sursa.",
        "project.error_missing_source": "Importa un fisier sursa inainte de a rula extragerea textului.",
        "project.error_missing_extracted_text": "Ruleaza mai intai Extrage Textul inainte de a porni curatarea.",
        "project.error_missing_cleaned_text": "Ruleaza curatarea textului inainte de a porni segmentarea.",
        "project.error_missing_chunk_artifact": "Ruleaza segmentarea textului inainte de a porni traducerea AI.",
        "project.error_missing_ai_profile": "Selecteaza un profil AI valid inainte de a porni curatarea asistata de AI.",
        "project.error_missing_ai_chunking_profile": "Selecteaza un profil AI valid inainte de a porni segmentarea asistata de AI.",
        "project.error_missing_ai_translation_profile": "Selecteaza un profil AI valid inainte de a porni traducerea AI.",
        "project.error_missing_character_discovery_profile": "Selecteaza un profil AI valid inainte de a porni descoperirea personajelor.",
        "project.error_missing_narrator_generation_profile": "Selecteaza un profil AI valid inainte de a genera profiluri narator.",
        "project.error_missing_speech_blocks_profile": "Selecteaza un profil AI valid inainte de a porni generarea blocurilor de vorbire.",
        "project.error_project_options_unlocked": "Porneste proiectul inainte de a continua.",
        "project.error_project_already_started": "Acest proiect este deja pornit. Creeaza un proiect nou pentru a folosi alta sursa.",
        "project.error_start_project_missing_source": "Selecteaza un fisier sursa inainte de a porni proiectul.",
        "project.error_duplicate_character_name": "Un personaj cu acest nume exista deja in lista curenta.",
        "project.error_invalid_character_name": "Introdu un nume de personaj care contine litere sau cifre.",
        "project.error_locked_source": "Acest proiect are deja un fisier sursa blocat. Creeaza un proiect nou pentru a folosi alta sursa.",
        "project.confirm_project_options_lock": (
            "Fisierul sursa, limba traducerii si stilul audio selectate vor ramane fixe pentru acest proiect. Continui?"
        ),
        "project.confirm_extraction_rerun": "Continuarea va sterge datele curente de extragere si toate datele pasilor urmatori, va goli folderele operatiilor urmatoare si va reseta progresul fluxului. Continui?",
        "project.confirm_cleanup_rerun": "Continuarea va sterge datele curente de curatare si toate rezultatele ulterioare. Continui?",
        "project.confirm_cleanup_mode_switch": "Schimbarea modului de curatare va sterge rezultatul Cleanup curent si toate rezultatele ulterioare. Continui?",
        "project.confirm_cleanup_reset": "Reset Cleanup va sterge cleanup.json, clean_text.txt, metadatele Cleanup vechi, logurile Cleanup si toate rezultatele ulterioare, inclusiv personajele, vocile si fisierele audio. Continui?",
        "project.ai_cleanup_reset_required_invalid": "AI Cleanup nu poate continua deoarece cleanup.json este invalid, incompatibil sau lipseste pentru o rulare veche. Foloseste mai intai Reseteaza Curatarea.",
        "project.ai_cleanup_reset_required_completed": "AI Cleanup este finalizat. Foloseste Reseteaza Curatarea inainte de o noua rulare.",
        "project.confirm_chunking_rerun": "Continuarea va sterge datele curente de segmentare, va goli traducerea si toate folderele operatiilor urmatoare si va reseta progresul fluxului dupa curatare. Continui?",
        "project.confirm_ai_chunking_rerun": "Continuarea va sterge datele curente de segmentare, va goli traducerea si toate folderele operatiilor urmatoare si va reseta progresul fluxului dupa curatare inainte de a porni o noua segmentare asistata de AI. Continui?",
        "project.confirm_cleaned_text_edit": "Editarea textului curatat poate afecta segmentarea, traducerea, descoperirea personajelor, Blocurile de Vorbire, Blocurile Audio si Asamblarea Audio dupa salvarea schimbarii. Continui?",
        "project.confirm_chunk_edit": "Editarea acestui segment poate reseta Traducerea pentru acest segment, poate elimina Blocurile de Vorbire si Blocurile Audio pentru acest segment si poate reseta Asamblarea Audio dupa salvarea schimbarii. Segmentele neafectate sunt pastrate. Continui?",
        "project.confirm_chunk_insert": "Inserarea unui segment va adauga o inregistrare netradusa, va actualiza metadatele de secventa si va reseta Asamblarea Audio. ID-urile existente si datele downstream neafectate sunt pastrate. Continui?",
        "project.confirm_chunk_delete": "Stergerea acestui segment va elimina Traducerea, Blocurile de Vorbire, Blocurile Audio si fisierele audio generate pentru el, apoi va reseta Asamblarea Audio. Segmentele neafectate sunt pastrate. Continui?",
        "project.confirm_speech_blocks": "Generarea blocurilor de vorbire poate dura deoarece trimite cate o cerere AI pentru fiecare segment si consuma tokeni AI. O rulare reusita va reseta Blocurile Audio si Asamblarea Audio. Continui?",
        "project.confirm_speech_blocks_rerun": "Continuarea va sterge datele curente pentru blocurile de vorbire, va goli Blocurile Audio si Asamblarea Audio si va reseta progresul fluxului dupa Vocile Personajelor inainte de a porni o noua rulare. Continui?",
        "project.confirm_speech_blocks_resplit": (
            "Continuarea va sterge blocurile de vorbire pentru segmentul selectat si va trimite o noua cerere AI. "
            "Operatiile AI pot dura mult si pot consuma tokeni platiti. Continui?"
        ),
        "project.confirm_scene_ambience_speech_blocks": (
            "Analiza Ambienta Scena adauga apeluri LLM suplimentare pentru fiecare segment, poate dura mai mult "
            "si poate fi anulata si reluata de la urmatorul segment neterminat. Continui?"
        ),
        "project.confirm_delete_speech_block": (
            "Continuarea va sterge blocul de vorbire selectat, va elimina doar datele Blocului Audio generat pentru "
            "el, va renumerota secventa segmentului si va reseta Asamblarea Audio. Continui?"
        ),
        "project.confirm_speech_block_audio_reset": (
            "Aceasta schimbare a blocului de vorbire afecteaza audio generat pentru blocul selectat. Continuarea "
            "va sterge doar fisierele WAV generate pentru acel bloc, va reseta metadatele sale audio si va reseta "
            "datele din aval pentru Asamblarea Audio. Continui?"
        ),
        "project.confirm_speech_block_sequence_change": (
            "Continuarea va pastra Blocurile Audio existente, va actualiza secventa Blocurilor de Vorbire si va "
            "reseta Asamblarea Audio deoarece ordinea finala de redare se schimba. Continui?"
        ),
        "project.confirm_audio_blocks": (
            "Generarea audio poate dura mult deoarece pregateste prompturi vocale reutilizabile si apoi "
            "genereaza fiecare bloc de vorbire pe rand. Rularea poate fi intrerupta si reluata mai tarziu. Continui?"
        ),
        "project.confirm_scene_ambience_audio_blocks": (
            "Generarea audio pentru Ambienta Scena poate dura semnificativ si necesita un model VoiceWeaver sanatos "
            "care suporta sound_prompt. Continui?"
        ),
        "project.confirm_audio_blocks_rerun": (
            "Continuarea va sterge blocurile audio generate curent, metadatele prompturilor vocale reutilizabile si datele "
            "Asamblarii Audio inainte de a porni o noua rulare. Continui?"
        ),
        "project.confirm_audio_blocks_reset": (
            "Continuarea va sterge toate blocurile audio generate, prompturile vocale reutilizabile si datele din aval pentru "
            "Asamblarea Audio. Continui?"
        ),
        "project.confirm_audio_blocks_invalidation": (
            "Aceasta schimbare afecteaza intrarile curente pentru Blocurile Audio. Continuarea va reseta blocurile "
            "audio generate, aprobarile lor si datele din aval pentru Asamblarea Audio. Continui?"
        ),
        "project.confirm_audio_block_regeneration": (
            "Continuarea va regenera doar Blocul Audio selectat, ii va elimina aprobarea si va reseta iesirile "
            "Asamblarii Audio din aval. Celelalte Blocuri Audio si datele workflow din amonte vor fi pastrate. "
            "Continui?"
        ),
        "project.confirm_audio_block_approval_change": (
            "Schimbarea aprobarii Blocului Audio afecteaza eligibilitatea Asamblarii Audio. Continuarea va pastra "
            "Blocurile Audio generate si va reseta iesirile Asamblarii Audio din aval. Continui?"
        ),
        "project.confirm_single_voice_target_invalidation": (
            "Aceasta schimbare de tinta vocala pastreaza Blocurile de Vorbire si randurile Blocurilor Audio, si "
            "sterge doar audio-ul generat care foloseste aceasta voce. Prompturile reutilizabile pentru voce si "
            "datele Asamblarii Audio vor fi resetate. Continui?"
        ),
        "project.confirm_narrator_voice_invalidation": (
            "Aceasta schimbare a vocii Naratorului pastreaza Blocurile de Vorbire si randurile Blocurilor Audio, "
            "si sterge doar audio-ul generat care foloseste vocea Naratorului. In proiectele cu acelasi narator, "
            "toate Blocurile Audio vorbite sunt afectate. Datele Asamblarii Audio vor fi resetate. Continui?"
        ),
        "project.confirm_global_voice_settings_invalidation": (
            "Aceasta schimbare globala de voce pastreaza Blocurile de Vorbire, dar reseteaza toate Blocurile Audio "
            "generate, prompturile vocale reutilizabile si datele Asamblarii Audio. Continui?"
        ),
        "project.confirm_translation_reset": (
            "Continuarea va sterge datele curente de traducere plus iesirile downstream pentru personaje, voci, "
            "vorbire, audio si audiobook. Continui?"
        ),
        "project.confirm_ai_cleanup": "Curatarea asistata de AI poate dura mai mult deoarece trimite mai multe cereri catre furnizorul AI selectat. Continui?",
        "project.confirm_ai_cleanup_rerun": "Continuarea va sterge datele curente de curatare, va goli segmentarea si toate folderele operatiilor urmatoare si va reseta progresul fluxului dupa extragere inainte de a porni o noua curatare asistata de AI. Continui?",
        "project.info_character_discovery": "Descoperirea personajelor poate dura mai mult deoarece analizeaza ferestre suprapuse de segmente si apoi sintetizeaza profilurile finale. Poti continua rularea mai tarziu daca este necesar. O noua rulare de descoperire inlocuieste lista curenta de personaje, inclusiv adaugarile si stergerile manuale.",
        "progress.extracting": "Extragerea textului este in curs...",
        "progress.cleaning": "Curatarea determinista este in curs...",
        "progress.ai_cleaning": "Curatarea asistata de AI este in curs...",
        "progress.chunking": "Segmentarea determinista este in curs...",
        "progress.ai_chunking": "Segmentarea asistata de AI este in curs...",
        "progress.ai_translation": "Traducerea AI este in curs...",
        "progress.ai_translation_retranslate": "Retraducerea segmentului selectat este in curs...",
        "progress.character_discovery": "Descoperirea personajelor este in curs...",
        "progress.character_save_prepare": "Se pregateste salvarea personajului...",
        "progress.character_save_profile": "Se salveaza profilul personajului...",
        "progress.character_save_character_voices": "Se sincronizeaza Vocile Personajelor...",
        "progress.character_save_speech_blocks": "Se actualizeaza Blocurile de Vorbire...",
        "progress.character_save_audio_blocks": "Se sterge audio-ul generat afectat...",
        "progress.character_save_manifest": "Se salveaza starea fluxului proiectului...",
        "progress.character_save_refresh": "Se reimprospateaza starea proiectului...",
        "progress.speech_blocks": "Generarea blocurilor de vorbire este in curs...",
        "progress.speech_blocks_resplit": (
            "Resegmentarea blocurilor de vorbire pentru segmentul selectat este in curs..."
        ),
        "progress.audio_blocks": "Generarea blocurilor audio este in curs...",
        "progress.audio_block_regeneration": "Regenerarea blocului audio selectat este in curs...",
        "progress.audio_assembly": "Asamblarea Audio este in curs...",
        "progress.scene_mix_preview": "Generarea previzualizarii Scene Mix este in curs...",
        "progress.project_snapshot": "Exportul ZIP al proiectului este in curs...",
        "dialog.confirm_translation_reset_title": "Confirma Resetarea Traducerii",
        "dialog.confirm_speech_blocks_title": "Porneste Generarea Blocurilor de Vorbire",
        "dialog.confirm_speech_blocks_rerun_title": "Confirma Rerularea Blocurilor de Vorbire",
        "dialog.confirm_speech_blocks_resplit_title": "Confirma Resegmentarea Segmentului Selectat",
        "dialog.confirm_scene_ambience_speech_blocks_title": "Activeaza Analiza Ambienta Scena",
        "dialog.confirm_delete_speech_block_title": "Sterge Bloc Vorbire",
        "dialog.confirm_speech_block_audio_reset_title": "Confirma Resetarea Audio a Blocului de Vorbire",
        "dialog.confirm_speech_block_sequence_change_title": "Confirma Schimbarea Secventei Blocurilor de Vorbire",
        "dialog.confirm_audio_blocks_title": "Porneste Generarea Audio",
        "dialog.confirm_scene_ambience_audio_blocks_title": "Activeaza Audio Ambienta Scena",
        "dialog.confirm_audio_blocks_rerun_title": "Confirma Rerularea Generarii Audio",
        "dialog.confirm_audio_blocks_reset_title": "Confirma Resetarea Generarii Audio",
        "dialog.confirm_audio_blocks_invalidation_title": "Confirma Resetarea Blocurilor Audio",
        "dialog.confirm_audio_block_regeneration_title": "Confirma Regenerarea Audio Selectata",
        "dialog.confirm_audio_block_approval_title": "Confirma Schimbarea Aprobarii Audio",
        "dialog.confirm_single_voice_target_invalidation_title": "Confirma Resetarea Audio a Tintei Vocale",
        "dialog.confirm_narrator_voice_invalidation_title": "Confirma Resetarea Audio a Naratorului",
        "dialog.confirm_global_voice_settings_invalidation_title": "Confirma Resetarea Audio Globala",
        "dialog.confirm_audio_assembly_title": "Porneste Asamblarea Audio",
        "dialog.confirm_audio_assembly_reset_title": "Confirma Resetarea Asamblarii Audio",
        "project.confirm_audio_assembly": (
            "Asamblarea Audio poate dura mult pentru carti mari. Operatia poate fi intrerupta si reluata mai tarziu "
            "cand intrarile si setarile nu s-au schimbat. Continui?"
        ),
        "project.confirm_audio_assembly_reset": (
            "Continuarea va sterge fisierele audiobook generate si progresul Asamblarii Audio. Continui?"
        ),
        "project.confirm_audio_assembly_settings_change": (
            "Schimbarea setarilor Asamblarii Audio va reseta doar iesirile audiobook existente, starea asamblarii "
            "si raportul de asamblare. Blocurile Audio aprobate si datele din amonte vor fi pastrate. Continui?"
        ),
        "status.audio_assembly_generated": "Asamblarea Audio s-a finalizat.",
        "status.audio_assembly_reset": "Datele Asamblarii Audio au fost resetate.",
        "status.audio_assembly_settings_saved_reset": (
            "Setarile Asamblarii Audio au fost salvate si iesirea de asamblare existenta a fost resetata."
        ),
        "status.audio_assembly_scene_mix_generated": "Previzualizarea mixului de scena a fost generata.",
        "dialog.confirm_audio_assembly_settings_change_title": "Confirma Schimbarea Setarilor Asamblarii",
        "dialog.character_discovery_info_title": "Informatii Descoperire Personaje",
        "dialog.character_add_title": "Adauga Personaj",
        "dialog.character_add_prompt": "Introdu numele canonic pentru noul personaj.",
        "dialog.character_add_confirm_title": "Confirma adaugarea personajului",
        "dialog.character_add_confirm_message": (
            "Adaugi acest personaj si sincronizezi lista de tinte Character Voices? "
            "Speech Blocks, Audio Blocks si iesirile Audio Assembly existente vor fi pastrate."
        ),
        "dialog.character_edit_title": "Confirma editarea personajului",
        "dialog.character_edit_message": (
            "Salvezi editarea acestui personaj? Speech Blocks atribuite lui vor deveni neaprobate, "
            "doar Audio Blocks aferente vor fi resetate, iar Audio Assembly va fi resetat."
        ),
        "dialog.character_delete_title": "Sterge Personajul",
        "dialog.character_delete_message": (
            "Stergi personajul selectat? Speech Blocks atribuite lui vor fi mutate pe Narator si neaprobate, "
            "doar Audio Blocks afectate vor fi resetate, iar Audio Assembly va fi resetat."
        ),
        "dialog.character_unsaved_title": "Modificari Nesalvate Ale Personajului",
        "dialog.character_unsaved_message": "Personajul curent are modificari nesalvate. Vrei sa le salvezi inainte de a continua?",
        "project.repair_step_prefix": "Proiectul este corupt la pasul",
        "project.repair_reset_suffix": "Aceasta reparatie va recrea si reseta acel pas si toate folderele pasilor urmatori.",
        "project.repair_metadata_only": "Aceasta reparatie va actualiza metadatele proiectului la ultima etapa coerenta a fluxului.",
        "project.repair_changes_header": "Actualizari metadata",
        "project.repair_warnings_header": "Avertismente",
        "project.repair_confirm": "Vrei sa repari proiectul acum?",
    },
}


def translate(key: str, language: str | None) -> str:
    """
    @brief      Resolve one UI string for one application language.
    @param[in]  key Stable UI string identifier.
    @param[in]  language Target UI language code.
    @return     Translated UI string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.1
    """
    resolved_language = language if language in _UI_STRINGS else _DEFAULT_LANGUAGE
    return _UI_STRINGS[resolved_language].get(
        key,
        _UI_STRINGS[_DEFAULT_LANGUAGE].get(key, key),
    )


def get_ui_strings(language: str | None) -> dict[str, str]:
    """
    @brief      Return a copy of the UI string catalog for one language.
    @param[in]  language Target UI language code.
    @return     Language-specific UI string mapping.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.1
    """
    resolved_language = language if language in _UI_STRINGS else _DEFAULT_LANGUAGE
    return _UI_STRINGS[resolved_language].copy()


def current_language_from_settings(
    settings_payload: dict[str, object] | None,
) -> str:
    """
    @brief      Resolve the current UI language from one settings payload.
    @param[in]  settings_payload Optional persisted settings mapping.
    @return     Current UI language code or the configured default.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if not isinstance(settings_payload, dict):
        return _DEFAULT_LANGUAGE
    return str(settings_payload.get("language", _DEFAULT_LANGUAGE))


def completion_beep_enabled_from_settings(
    settings_payload: dict[str, object] | None,
) -> bool:
    """
    @brief      Resolve the operator completion-beep preference from one settings payload.
    @param[in]  settings_payload Optional persisted settings mapping.
    @return     True when a finished operation should produce an audible beep.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    if not isinstance(settings_payload, dict):
        return False
    return bool(settings_payload.get("play_completion_beep", config.DEFAULT_PLAY_COMPLETION_BEEP))


def operator_status_pane_height(reference_widget: QWidget, line_count: int = 3) -> int:
    """
    @brief      Compute the fixed pixel height for an operator-status pane.
    @details    Sizes the pane to show `line_count` text rows using the reference
                widget font metrics plus the default plain-text document margin and
                frame, so the status pane stays compact and follows the active UI
                font scale instead of a hard-coded pixel band.
    @param[in]  reference_widget Widget whose font metrics drive the row height.
    @param[in]  line_count Number of text rows the pane should display.
    @return     Fixed pane height in pixels.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    line_height = reference_widget.fontMetrics().lineSpacing()
    document_margin = 4
    frame = 2
    return int(line_height * max(line_count, 1) + document_margin * 2 + frame * 2)


# HELPER FUNCTIONS


def _capture_base_font(application: QApplication) -> QFont:
    """
    @brief      Capture the platform baseline font used by text-scale and theme helpers.
    @param[in]  application Running Qt application instance.
    @return     Current application font.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    global _BASE_FONT_FAMILY, _BASE_FONT_POINT_SIZE

    current_font = application.font()
    if _BASE_FONT_FAMILY is None:
        _BASE_FONT_FAMILY = current_font.family()
    if _BASE_FONT_POINT_SIZE is None:
        current_size = current_font.pointSizeF()
        _BASE_FONT_POINT_SIZE = current_size if current_size > 0 else 9.0
    return current_font


def _scaled_point_size(base_point_size: float, ui_text_scale: str | None) -> float:
    """
    @brief      Resolve an effective point size from one base size and scale key.
    @param[in]  base_point_size Unscaled point size.
    @param[in]  ui_text_scale Operator-selected UI text-scale preset.
    @return     Effective scaled point size.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    scale_key = ui_text_scale if ui_text_scale in _UI_SCALE_FACTORS else config.DEFAULT_UI_TEXT_SCALE
    return base_point_size * _UI_SCALE_FACTORS[scale_key]


def _font_stylesheet(font_payload: dict[str, object], base_point_size: float) -> str:
    """
    @brief      Build Qt stylesheet font declarations from one normalized theme font payload.
    @param[in]  font_payload Normalized theme font payload.
    @param[in]  base_point_size Unscaled application point size fallback.
    @return     Font declaration lines for a Qt stylesheet block.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.2.0
    """
    declarations: list[str] = []
    font_family = str(font_payload.get("family", "")).strip()
    if font_family:
        escaped_family = font_family.replace("'", "\\'")
        declarations.append(f"    font-family: '{escaped_family}';")

    point_size = font_payload.get("point_size")
    fallback_point_size = float(point_size) if isinstance(point_size, (int, float)) else base_point_size
    declarations.append(f"    font-size: {fallback_point_size:.1f}pt;")
    return "\n".join(declarations)


def _theme_colors(theme_payload: dict[str, object]) -> dict[str, str]:
    """
    @brief      Extract normalized color roles from one theme payload.
    @param[in]  theme_payload Normalized theme payload.
    @return     Color-role mapping.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    colors = theme_payload.get("colors")
    if isinstance(colors, dict):
        return {str(role_name): str(color_value) for role_name, color_value in colors.items()}
    return {}


def _qcolor(color_value: str) -> QColor:
    """
    @brief      Convert one normalized hex color into a Qt color object.
    @param[in]  color_value Hex RGB color value.
    @return     Qt color object.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    return QColor(color_value)


def _readable_foreground(background: QColor) -> QColor:
    """
    @brief      Choose black or white foreground text for one background color.
    @param[in]  background Background color.
    @return     Readable foreground color.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    luminance = (0.299 * background.red()) + (0.587 * background.green()) + (0.114 * background.blue())
    return QColor("#000000" if luminance > 145 else "#FFFFFF")


def _refresh_top_level_widgets(application: QApplication, font: QFont | None = None) -> None:
    """
    @brief      Refresh visible top-level widgets after a global UI state change.
    @param[in]  application Running Qt application instance.
    @param[in]  font Optional font to apply to each top-level widget.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    for widget in application.topLevelWidgets():
        if isinstance(widget, QWidget):
            if font is not None:
                widget.setFont(QFont(font))
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()


# PUBLIC API


@trace_function(_UI_STATE_LOGGER)
def apply_text_scale(
    application: QApplication | None,
    ui_text_scale: str | None,
) -> None:
    """
    @brief      Apply one UI text-scale preset to the running application.
    @param[in]  application Running Qt application instance.
    @param[in]  ui_text_scale Operator-selected text-scale preset.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    if application is None:
        return

    scale_key = ui_text_scale if ui_text_scale in _UI_SCALE_FACTORS else config.DEFAULT_UI_TEXT_SCALE
    if ui_text_scale not in _UI_SCALE_FACTORS:
        _UI_STATE_LOGGER.warning(
            "Replaced invalid UI text scale with the default value.",
            extra={
                "func_name": "apply_text_scale",
                "event": "ui-settings-repair",
                "result": config.DEFAULT_UI_TEXT_SCALE,
            },
        )
    current_font = _capture_base_font(application)

    scaled_font = QFont(current_font)
    assert _BASE_FONT_POINT_SIZE is not None
    scaled_font.setPointSizeF(_scaled_point_size(_BASE_FONT_POINT_SIZE, scale_key))
    application.setFont(scaled_font)

    _refresh_top_level_widgets(application, scaled_font)

    _UI_STATE_LOGGER.info(
        f"Applied UI text scale '{scale_key}'.",
        extra={
            "func_name": "apply_text_scale",
            "event": "ui-text-scale-applied",
            "result": scale_key,
        },
    )


def build_theme_stylesheet(theme_payload: dict[str, object], base_point_size: float | None = None) -> str:
    """
    @brief      Build a compact application stylesheet for theme roles not covered by QPalette.
    @param[in]  theme_payload Validated theme payload.
    @param[in]  base_point_size Unscaled application point size used for text editor font fallback.
    @return     Qt stylesheet string.
    @exception  ValueError Raised when the theme payload is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.5.0
    """
    normalized_theme = ui_theme_service.validate_theme_payload(theme_payload, allow_built_in=True)
    colors = _theme_colors(normalized_theme)
    ui_font_payload = normalized_theme["font"]
    assert isinstance(ui_font_payload, dict)
    text_font_payload = normalized_theme["text_font"]
    assert isinstance(text_font_payload, dict)
    base_font_point_size = base_point_size or _BASE_FONT_POINT_SIZE or 10.0
    ui_font_stylesheet = _font_stylesheet(ui_font_payload, base_font_point_size)
    text_font_stylesheet = _font_stylesheet(text_font_payload, base_font_point_size)
    accent = colors["accent"]
    panel_background = colors["panel_background"]
    text_primary = colors["text_primary"]
    text_muted = colors["text_muted"]
    border = colors["border"]
    disabled = colors["disabled"]
    focus_text = _readable_foreground(_qcolor(accent)).name().upper()
    hover_background = _qcolor(accent).lighter(128).name().upper()
    accent_qcolor = _qcolor(accent)
    accent_rgb = f"{accent_qcolor.red()}, {accent_qcolor.green()}, {accent_qcolor.blue()}"
    sidebar_hover_background = f"rgba({accent_rgb}, 0.12)"
    sidebar_selected_background = f"rgba({accent_rgb}, 0.20)"

    return f"""
QGroupBox {{
    background-color: {panel_background};
    border: 1px solid {border};
    border-radius: 10px;
    margin-top: 0.9em;
    padding: 10px 10px 8px 10px;
}}
QGroupBox::title {{
    color: {text_muted};
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 2px 4px;
}}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QTableWidget, QListWidget {{
    background-color: {panel_background};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: 8px;
    selection-background-color: {accent};
    selection-color: {focus_text};
}}
QTextEdit, QPlainTextEdit {{
{text_font_stylesheet}
}}
QTextEdit[{CONTROL_TEXT_FONT_ROLE_PROPERTY}="{CONTROL_TEXT_FONT_ROLE_VALUE}"],
QPlainTextEdit[{CONTROL_TEXT_FONT_ROLE_PROPERTY}="{CONTROL_TEXT_FONT_ROLE_VALUE}"] {{
{ui_font_stylesheet}
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus,
QTableWidget:focus, QListWidget:focus {{
    border: 1px solid {accent};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background-color: {panel_background};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {accent};
    selection-color: {focus_text};
    outline: none;
}}
QToolBar {{
    background-color: {panel_background};
    border: none;
    spacing: 2px;
    padding: 2px;
}}
QToolBar::separator {{
    background-color: {border};
    width: 1px;
    margin: 4px 6px;
}}
QToolButton {{
    color: {text_primary};
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 10px;
}}
QToolButton:hover {{
    color: {focus_text};
    background-color: {hover_background};
    border-color: {accent};
}}
QToolButton:pressed, QToolButton:checked {{
    color: {focus_text};
    background-color: {accent};
}}
QToolButton:disabled {{
    color: {disabled};
}}
QPushButton {{
    color: {text_primary};
    background-color: {panel_background};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 4px 10px;
}}
QPushButton:hover {{
    border-color: {accent};
    background-color: {hover_background};
    color: {focus_text};
}}
QPushButton:focus {{
    border-color: {accent};
}}
QPushButton:disabled {{
    color: {disabled};
    border-color: {border};
    background-color: {panel_background};
}}
QScrollBar:vertical {{
    background: {panel_background};
    width: 12px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {border};
    border-radius: 5px;
    min-height: 28px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {accent};
}}
QScrollBar:horizontal {{
    background: {panel_background};
    height: 12px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {border};
    border-radius: 5px;
    min-width: 28px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {accent};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
    background: none;
    border: none;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: none;
}}
QProgressBar {{
    background-color: {panel_background};
    border: 1px solid {border};
    border-radius: 6px;
    text-align: center;
    color: {text_primary};
}}
QProgressBar::chunk {{
    background-color: {accent};
    border-radius: 5px;
}}
QMenu {{
    background-color: {panel_background};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 5px 18px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background-color: {accent};
    color: {focus_text};
}}
QListWidget#navigationSidebar {{
    background-color: {panel_background};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 6px;
    outline: none;
}}
QListWidget#navigationSidebar::item {{
    color: {text_muted};
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 7px 8px;
    margin: 1px 2px;
}}
QListWidget#navigationSidebar::item:hover {{
    color: {text_primary};
    background-color: {sidebar_hover_background};
}}
QListWidget#navigationSidebar::item:selected {{
    color: {text_primary};
    background-color: {sidebar_selected_background};
    border-left: 3px solid {accent};
}}
""".strip()


def font_size_step_factor(step: object) -> float:
    """
    @brief      Return the base-font multiplier for one font-size step.
    @param[in]  step Candidate font-size step name.
    @return     Multiplier for a known step, or the 'normal' multiplier otherwise.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    return FONT_SIZE_STEP_FACTORS.get(str(step), FONT_SIZE_STEP_FACTORS[config.DEFAULT_UI_FONT_SIZE_STEP])


def resolve_font_point_size(step: object, base_point_size: float) -> float:
    """
    @brief      Resolve one font-size step to an absolute point size.
    @param[in]  step Candidate font-size step name.
    @param[in]  base_point_size Unscaled base font point size.
    @return     Base point size multiplied by the step factor.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    return float(base_point_size) * font_size_step_factor(step)


def apply_theme(
    application: QApplication | None,
    theme_payload: dict[str, object],
    ui_text_scale: str | None = None,
    ui_font_size_step: str | None = None,
    text_font_size_step: str | None = None,
) -> None:
    """
    @brief      Apply one validated UI theme plus the operator font-size steps to the application.
    @param[in]  application Running Qt application instance.
    @param[in]  theme_payload Theme payload to apply.
    @param[in]  ui_text_scale Deprecated fallback text-scale preset.
    @param[in]  ui_font_size_step Control/interface font-size step.
    @param[in]  text_font_size_step Text-window (editor) font-size step.
    @return     None.
    @exception  ValueError Raised when the theme payload is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.4.0
    """
    if application is None:
        return

    normalized_theme = ui_theme_service.validate_theme_payload(theme_payload, allow_built_in=True)
    current_font = _capture_base_font(application)

    base_point_size = _BASE_FONT_POINT_SIZE if _BASE_FONT_POINT_SIZE is not None else 10.0
    ui_step = ui_font_size_step if ui_font_size_step is not None else config.DEFAULT_UI_FONT_SIZE_STEP
    text_step = text_font_size_step if text_font_size_step is not None else config.DEFAULT_TEXT_FONT_SIZE_STEP
    minimum_point_size = ui_theme_service.MIN_FONT_POINT_SIZE
    maximum_point_size = ui_theme_service.MAX_FONT_POINT_SIZE
    ui_point_size = max(minimum_point_size, min(maximum_point_size, resolve_font_point_size(ui_step, base_point_size)))
    text_point_size = max(
        minimum_point_size, min(maximum_point_size, resolve_font_point_size(text_step, base_point_size))
    )

    font_payload = normalized_theme["font"]
    assert isinstance(font_payload, dict)
    text_font_payload = normalized_theme["text_font"]
    assert isinstance(text_font_payload, dict)
    font_payload["point_size"] = ui_point_size
    text_font_payload["point_size"] = text_point_size

    theme_font_family = str(font_payload.get("family", "")).strip()
    themed_font = QFont(current_font)
    themed_font.setFamily(theme_font_family or str(_BASE_FONT_FAMILY or current_font.family()))
    themed_font.setPointSizeF(ui_point_size)
    application.setFont(themed_font)

    colors = _theme_colors(normalized_theme)
    palette = QPalette(application.palette())
    window_background = _qcolor(colors["window_background"])
    panel_background = _qcolor(colors["panel_background"])
    text_primary = _qcolor(colors["text_primary"])
    text_muted = _qcolor(colors["text_muted"])
    accent = _qcolor(colors["accent"])
    border = _qcolor(colors["border"])
    disabled = _qcolor(colors["disabled"])
    highlight_text = _readable_foreground(accent)

    palette.setColor(QPalette.ColorRole.Window, window_background)
    palette.setColor(QPalette.ColorRole.Base, panel_background)
    palette.setColor(QPalette.ColorRole.AlternateBase, window_background.lighter(104))
    palette.setColor(QPalette.ColorRole.Text, text_primary)
    palette.setColor(QPalette.ColorRole.WindowText, text_primary)
    palette.setColor(QPalette.ColorRole.Button, panel_background)
    palette.setColor(QPalette.ColorRole.ButtonText, text_primary)
    palette.setColor(QPalette.ColorRole.PlaceholderText, text_muted)
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, highlight_text)
    palette.setColor(QPalette.ColorRole.Link, accent)
    palette.setColor(QPalette.ColorRole.ToolTipBase, panel_background)
    palette.setColor(QPalette.ColorRole.ToolTipText, text_primary)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, border)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, disabled)
    application.setPalette(palette)
    application.setStyleSheet(build_theme_stylesheet(normalized_theme, base_point_size=_BASE_FONT_POINT_SIZE))

    for widget in application.topLevelWidgets():
        if hasattr(widget, "apply_theme"):
            widget.apply_theme(normalized_theme)

    _refresh_top_level_widgets(application, themed_font)
    _UI_STATE_LOGGER.info(
        f"Applied UI theme '{normalized_theme['theme_id']}'.",
        extra={
            "func_name": "apply_theme",
            "event": "ui-theme-applied",
            "result": normalized_theme["theme_id"],
        },
    )


@trace_function(_UI_STATE_LOGGER)
def apply_language(main_window: QWidget, language: str | None) -> None:
    """
    @brief      Apply one UI language to the running shell hierarchy.
    @param[in]  main_window Main window that coordinates the visible shell.
    @param[in]  language Target UI language code.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    resolved_language = language if language in _UI_STRINGS else _DEFAULT_LANGUAGE
    if language not in _UI_STRINGS:
        _UI_STATE_LOGGER.warning(
            "Replaced invalid UI language with the default value.",
            extra={
                "func_name": "apply_language",
                "event": "ui-settings-repair",
                "result": _DEFAULT_LANGUAGE,
            },
        )
    if hasattr(main_window, "apply_language"):
        main_window.apply_language(resolved_language)
        _UI_STATE_LOGGER.info(
            f"Applied UI language '{resolved_language}'.",
            extra={
                "func_name": "apply_language",
                "event": "ui-language-applied",
                "result": resolved_language,
            },
        )


@trace_function(_UI_STATE_LOGGER)
def apply_ui_settings(
    application: QApplication | None,
    main_window: QWidget,
    settings_payload: dict[str, object],
) -> None:
    """
    @brief      Apply persisted UI theme, text scale, and language to the shell.
    @param[in]  application Running Qt application instance.
    @param[in]  main_window Main application window.
    @param[in]  settings_payload Persisted application settings payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.2.0
    """
    selected_theme = ui_theme_service.theme_by_id(
        settings_payload.get("ui_theme_id", config.DEFAULT_UI_THEME_ID),
        settings_payload.get("ui_themes", []),
    )
    apply_theme(
        application,
        selected_theme,
        None,
        ui_font_size_step=str(settings_payload.get("ui_font_size_step", config.DEFAULT_UI_FONT_SIZE_STEP)),
        text_font_size_step=str(settings_payload.get("text_font_size_step", config.DEFAULT_TEXT_FONT_SIZE_STEP)),
    )
    apply_language(
        main_window,
        str(settings_payload.get("language", config.DEFAULT_LANGUAGE)),
    )


# END OF FILE
