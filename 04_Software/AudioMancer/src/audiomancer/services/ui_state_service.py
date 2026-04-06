#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
         application through one centralized string catalog and scale mapping.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.7.0
"""

# IMPORTS

from copy import deepcopy

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget

from .. import config
from .logging_service import get_component_logger, trace_function

# CONSTANTS

_UI_STATE_LOGGER = get_component_logger("ui_state")
_UI_SCALE_FACTORS = {
    "very_small": 0.82,
    "small": 0.91,
    "normal": 1.0,
    "large": 1.12,
    "very_large": 1.24,
}

_DEFAULT_LANGUAGE = config.DEFAULT_LANGUAGE
_BASE_FONT_POINT_SIZE: float | None = None

_UI_STRINGS = {
    "en": {
        "window_title.main": "AudioMancer | Transform written words into real audio experience!",
        "toolbar.new_project": "New Project",
        "toolbar.open_project": "Open Project",
        "toolbar.settings": "Settings",
        "toolbar.ai_settings": "AI Settings",
        "toolbar.help": "Help",
        "toolbar.about": "About",
        "dialog.settings_title": "Settings",
        "dialog.ai_settings_title": "AI Settings",
        "dialog.about_title": "About",
        "dialog.new_project_title": "New Project",
        "dialog.open_project_title": "Open Project",
        "dialog.select_project_parent_title": "Select Project Parent Folder",
        "dialog.select_source_title": "Select Source File",
        "dialog.select_source_filter": "Supported source files (*.txt *.pdf *.rtf *.docx *.odt *.md *.epub)",
        "dialog.project_error_title": "Project Error",
        "dialog.project_repair_title": "Repair Project",
        "about.subtitle": "Transform written words into real audio experience!",
        "about.license": "License",
        "about.details": "Eng. Dipl. Dan Dumitru Pasare\npasaredan1979@gmail.com",
        "help.placeholder": "Use New Project or Open Project to activate one project workspace, then continue through the workflow pages.",
        "status.stop_ai": "Stop AI",
        "status.stage_prefix": "Stage",
        "status.idle": "idle",
        "status.saved_settings": "Settings saved.",
        "status.saved_ai_settings": "AI settings saved.",
        "status.project_created": "Project created.",
        "status.project_opened": "Project opened.",
        "status.project_repaired": "Project repaired and opened.",
        "status.source_imported": "Source file imported.",
        "sidebar.home": "Home / Project",
        "sidebar.text_cleanup": "Text Cleanup",
        "sidebar.text_chunking": "Text Chunking",
        "sidebar.ai_translation": "AI Translation",
        "sidebar.characters": "Characters",
        "sidebar.narrator": "Narrator",
        "sidebar.narration_plan": "Narration Plan",
        "sidebar.generation": "Generation",
        "sidebar.export": "Export",
        "settings.language": "Language",
        "settings.text_size": "Interface Text Size",
        "settings.play_beep": "Play completion beep",
        "settings.cancel": "Cancel",
        "settings.save": "Save Settings",
        "settings.scale.very_small": "Very Small",
        "settings.scale.small": "Small",
        "settings.scale.normal": "Normal",
        "settings.scale.large": "Large",
        "settings.scale.very_large": "Very Large",
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
        "ai_settings.structured_output": "Structured output supported",
        "ai_settings.default_cleanup": "Default Cleanup Profile",
        "ai_settings.default_chunking": "Default Chunking Profile",
        "ai_settings.default_strategy": "Default AI Chunking Strategy",
        "ai_settings.default_character": "Default Character Extraction Profile",
        "ai_settings.none": "(none)",
        "ai_settings.add_profile": "Add Profile",
        "ai_settings.remove_profile": "Remove Profile",
        "ai_settings.connect": "Connect",
        "ai_settings.cancel": "Cancel",
        "ai_settings.save": "Save AI Settings",
        "ai_settings.no_profiles": "(no profiles)",
        "ai_settings.not_connected": "Not connected yet.",
        "ai_settings.connection_status": "Connection status",
        "ai_settings.connection_failed": "Connection failed",
        "ai_settings.popup_success_title": "Connection Successful",
        "ai_settings.popup_failure_title": "Connection Failed",
        "ai_settings.popup_discovered_models": "Discovered models",
        "ai_settings.popup_success_message": "Connection successful.",
        "ai_settings.popup_failure_message": "Connection failed.",
        "text_cleanup.title": "Text Cleanup",
        "text_cleanup.extract": "Extract Text",
        "text_cleanup.clean": "Deterministic Cleanup",
        "text_cleanup.ai_profile": "AI Profile",
        "text_cleanup.ai_clean": "AI-Assisted Cleanup",
        "text_cleanup.extracted_group": "Extracted Text Preview",
        "text_cleanup.cleaned_group": "Cleaned Text Preview",
        "text_cleanup.notes_group": "Cleanup Notes",
        "text_cleanup.extracted_note": "Raw extracted text will appear here after source processing.",
        "text_cleanup.cleaned_note": "Deterministic or AI-assisted cleanup output will appear here.",
        "text_cleanup.notes_text": "Import a source to begin text extraction.\nDeterministic cleanup and AI-assisted cleanup are not wired yet.",
        "text_chunking.title": "Text Chunking",
        "text_chunking.ai_profile": "AI Profile",
        "text_chunking.ai_strategy": "AI Strategy",
        "text_chunking.chunk": "Deterministic Chunking",
        "text_chunking.ai_chunk": "AI-Assisted Chunking",
        "text_chunking.cleaned_group": "Cleaned Text Reference",
        "text_chunking.chunk_list_group": "Chunk List",
        "text_chunking.selected_group": "Selected Chunk",
        "text_chunking.notes_group": "Chunking Notes",
        "text_chunking.cleaned_note": "Cleaned text will appear here and serve as the chunking reference.",
        "text_chunking.selected_note": "The full text of the selected chunk will appear here.",
        "text_chunking.notes_text": "Run cleanup before chunking.\nDeterministic and AI-assisted chunk generation are not wired yet.",
        "ai_translation.title": "AI Translation",
        "ai_translation.target_language": "Target Language",
        "ai_translation.ai_profile": "AI Profile",
        "ai_translation.chunk_list_group": "Chunk List",
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
        "characters.title": "Characters",
        "characters.ai_profile": "AI Profile",
        "characters.start": "Start Discovery",
        "characters.reset": "Reset Discovery",
        "characters.summary": "Run text chunking before Character Discovery.",
        "characters.list_group": "Character List",
        "characters.profile_group": "Character Profile",
        "characters.evidence_group": "Evidence",
        "characters.canonical_name": "Canonical Name",
        "characters.aliases": "Aliases",
        "characters.gender_hint": "Gender Hint",
        "characters.age_band": "Age Band",
        "characters.role_summary": "Role Summary",
        "characters.description": "Description",
        "characters.temperament": "Temperament",
        "characters.social_status": "Social Status",
        "characters.speaking_style": "Speaking Style",
        "characters.accent": "Accent / Dialect",
        "characters.voice_notes": "Voice Notes",
        "characters.relationship_hints": "Relationship Hints",
        "characters.confidence": "Confidence",
        "characters.evidence_note": "Selected source evidence excerpt will appear here.",
        "narrator.title": "Narrator",
        "narrator.language": "Narrator Language",
        "narrator.summary": "Choose a narrator profile, adapt its prompt, or create a new custom narrator profile for the current language.",
        "narrator.profiles_group": "Narrator Profiles",
        "narrator.new_profile": "New Profile",
        "narrator.setup_group": "Profile Setup",
        "narrator.profile_name": "Profile Name",
        "narrator.designer_group": "Voice Designer Prompt",
        "narrator.preview_group": "Preview Text",
        "narrator.create_profile": "Create Profile",
        "narrator.save_profile": "Save Profile",
        "narrator.delete_profile": "Delete Profile",
        "narrator.preview": "Preview",
        "placeholder.narration_plan.title": "Narration Plan",
        "placeholder.narration_plan.note": "Narration planning is not implemented yet.",
        "placeholder.generation.title": "Generation",
        "placeholder.generation.note": "Generation is not implemented yet.",
        "placeholder.export.title": "Export",
        "placeholder.export.note": "Export is not implemented yet.",
        "home.title": "Home / Project",
        "home.summary_group": "Project Summary",
        "home.project": "Project",
        "home.path": "Path",
        "home.stage": "Stage",
        "home.source": "Source",
        "home.none": "none",
        "home.source_import_group": "Source Import",
        "home.source_import_note": "Each project is bound to exactly one source file. After the source is imported, the selection is locked for that project.",
        "home.select_source": "Select Source File",
        "home.no_source": "No source imported yet.",
        "home.locked_source_prefix": "Locked source",
        "home.locked_source_suffix": ". Create a new project to use another file.",
        "home.workflow_group": "Workflow Progress",
        "home.status.not_started": "Not Started",
        "home.status.in_progress": "In Progress",
        "home.status.finished": "Finished",
        "home.stage_label.source_selected": "Source Selected",
        "home.stage_label.text_cleanup_ready": "Text Cleanup",
        "home.stage_label.text_chunking_ready": "Text Chunking",
        "home.stage_label.translation_ready": "AI Translation",
        "home.stage_label.character_discovery_ready": "Characters",
        "home.stage_label.narrator_definition_ready": "Narrator Definition",
        "home.stage_note.inactive.source_selected": "Create or open a project first.",
        "home.stage_note.inactive.text_cleanup_ready": "Create or open a project first.",
        "home.stage_note.inactive.text_chunking_ready": "Create or open a project first.",
        "home.stage_note.inactive.translation_ready": "Create or open a project first.",
        "home.stage_note.inactive.character_discovery_ready": "Create or open a project first.",
        "home.stage_note.inactive.narrator_definition_ready": "Create or open a project first.",
        "home.stage_note.active.source_selected": "Select and import one source file for the project.",
        "home.stage_note.active.text_cleanup_ready": "Prepare the imported source text for chunking.",
        "home.stage_note.active.text_chunking_ready": "Split the cleaned text into workflow chunks.",
        "home.stage_note.active.translation_ready": "Translate the chunk set when needed.",
        "home.stage_note.active.character_discovery_ready": "Extract and review the character set.",
        "home.stage_note.active.narrator_definition_ready": "Select and adapt the narrator definition for the project.",
        "project.new_dialog_intro": "Choose the parent folder where the project will be created and enter the exact project name.",
        "project.parent_folder": "Parent Folder",
        "project.project_name": "Project Name",
        "project.browse": "Browse",
        "project.create": "Create",
        "project.cancel": "Cancel",
        "project.error_missing_parent": "Select the parent folder where the project should be created.",
        "project.error_missing_name": "Enter the exact project name.",
        "project.error_no_active_project": "Create or open a project before importing a source file.",
        "project.error_locked_source": "This project already has a locked source file. Create a new project to use another source.",
        "project.repair_step_prefix": "The project is corrupted at step",
        "project.repair_reset_suffix": "This repair will recreate and reset that step and all downstream step folders.",
        "project.repair_metadata_only": "This repair will update the project metadata to the last consistent workflow stage.",
        "project.repair_confirm": "Do you want to repair the project now?",
    },
    "ro": {
        "window_title.main": "AudioMancer | Transforma cuvintele scrise intr-o experienta audio reala!",
        "toolbar.new_project": "Proiect Nou",
        "toolbar.open_project": "Deschide Proiect",
        "toolbar.settings": "Setari",
        "toolbar.ai_settings": "Setari AI",
        "toolbar.help": "Ajutor",
        "toolbar.about": "Despre",
        "dialog.settings_title": "Setari",
        "dialog.ai_settings_title": "Setari AI",
        "dialog.about_title": "Despre",
        "dialog.new_project_title": "Proiect Nou",
        "dialog.open_project_title": "Deschide Proiect",
        "dialog.select_project_parent_title": "Selecteaza Dosarul Parinte Al Proiectului",
        "dialog.select_source_title": "Selecteaza Fisierul Sursa",
        "dialog.select_source_filter": "Fisiere sursa acceptate (*.txt *.pdf *.rtf *.docx *.odt *.md *.epub)",
        "dialog.project_error_title": "Eroare Proiect",
        "dialog.project_repair_title": "Repara Proiectul",
        "about.subtitle": "Transforma cuvintele scrise intr-o experienta audio reala!",
        "about.license": "Licenta",
        "about.details": "Ing. Dipl. Dan Dumitru Pasare\npasaredan1979@gmail.com",
        "help.placeholder": "Foloseste Proiect Nou sau Deschide Proiect pentru a activa un spatiu de lucru, apoi continua prin paginile fluxului.",
        "status.stop_ai": "Opreste AI",
        "status.stage_prefix": "Etapa",
        "status.idle": "inactiva",
        "status.saved_settings": "Setarile au fost salvate.",
        "status.saved_ai_settings": "Setarile AI au fost salvate.",
        "status.project_created": "Proiectul a fost creat.",
        "status.project_opened": "Proiectul a fost deschis.",
        "status.project_repaired": "Proiectul a fost reparat si deschis.",
        "status.source_imported": "Fisierul sursa a fost importat.",
        "sidebar.home": "Acasa / Proiect",
        "sidebar.text_cleanup": "Curatare Text",
        "sidebar.text_chunking": "Segmentare Text",
        "sidebar.ai_translation": "Traducere AI",
        "sidebar.characters": "Personaje",
        "sidebar.narrator": "Narator",
        "sidebar.narration_plan": "Plan Naratie",
        "sidebar.generation": "Generare",
        "sidebar.export": "Export",
        "settings.language": "Limba",
        "settings.text_size": "Dimensiune Text Interfata",
        "settings.play_beep": "Reda semnalul sonor la finalizare",
        "settings.cancel": "Anuleaza",
        "settings.save": "Salveaza Setarile",
        "settings.scale.very_small": "Foarte Mic",
        "settings.scale.small": "Mic",
        "settings.scale.normal": "Normal",
        "settings.scale.large": "Mare",
        "settings.scale.very_large": "Foarte Mare",
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
        "ai_settings.structured_output": "Suporta iesire structurata",
        "ai_settings.default_cleanup": "Profil implicit pentru curatare",
        "ai_settings.default_chunking": "Profil implicit pentru segmentare",
        "ai_settings.default_strategy": "Strategie implicita de segmentare AI",
        "ai_settings.default_character": "Profil implicit pentru extragerea personajelor",
        "ai_settings.none": "(niciunul)",
        "ai_settings.add_profile": "Adauga Profil",
        "ai_settings.remove_profile": "Sterge Profil",
        "ai_settings.connect": "Conecteaza",
        "ai_settings.cancel": "Anuleaza",
        "ai_settings.save": "Salveaza Setarile AI",
        "ai_settings.no_profiles": "(fara profiluri)",
        "ai_settings.not_connected": "Nu este conectat inca.",
        "ai_settings.connection_status": "Stare conexiune",
        "ai_settings.connection_failed": "Conexiune esuata",
        "ai_settings.popup_success_title": "Conectare Reusita",
        "ai_settings.popup_failure_title": "Conectare Esuata",
        "ai_settings.popup_discovered_models": "Modele descoperite",
        "ai_settings.popup_success_message": "Conectare reusita.",
        "ai_settings.popup_failure_message": "Conectarea a esuat.",
        "text_cleanup.title": "Curatare Text",
        "text_cleanup.extract": "Extrage Textul",
        "text_cleanup.clean": "Curatare Determinista",
        "text_cleanup.ai_profile": "Profil AI",
        "text_cleanup.ai_clean": "Curatare Asistata de AI",
        "text_cleanup.extracted_group": "Previzualizare Text Extras",
        "text_cleanup.cleaned_group": "Previzualizare Text Curatat",
        "text_cleanup.notes_group": "Note Curatare",
        "text_cleanup.extracted_note": "Textul extras brut va aparea aici dupa procesarea sursei.",
        "text_cleanup.cleaned_note": "Rezultatul curatarii deterministe sau asistate de AI va aparea aici.",
        "text_cleanup.notes_text": "Importa o sursa pentru a incepe extragerea textului.\nCuratarea determinista si cea asistata de AI nu sunt inca conectate.",
        "text_chunking.title": "Segmentare Text",
        "text_chunking.ai_profile": "Profil AI",
        "text_chunking.ai_strategy": "Strategie AI",
        "text_chunking.chunk": "Segmentare Determinista",
        "text_chunking.ai_chunk": "Segmentare Asistata de AI",
        "text_chunking.cleaned_group": "Referinta Text Curatat",
        "text_chunking.chunk_list_group": "Lista Segmentelor",
        "text_chunking.selected_group": "Segment Selectat",
        "text_chunking.notes_group": "Note Segmentare",
        "text_chunking.cleaned_note": "Textul curatat va aparea aici si va servi drept referinta pentru segmentare.",
        "text_chunking.selected_note": "Textul complet al segmentului selectat va aparea aici.",
        "text_chunking.notes_text": "Ruleaza curatarea inainte de segmentare.\nGenerarea determinista si asistata de AI a segmentelor nu este inca conectata.",
        "ai_translation.title": "Traducere AI",
        "ai_translation.target_language": "Limba Tinta",
        "ai_translation.ai_profile": "Profil AI",
        "ai_translation.chunk_list_group": "Lista Segmentelor",
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
        "characters.title": "Personaje",
        "characters.ai_profile": "Profil AI",
        "characters.start": "Porneste Descoperirea",
        "characters.reset": "Reseteaza Descoperirea",
        "characters.summary": "Ruleaza segmentarea textului inainte de descoperirea personajelor.",
        "characters.list_group": "Lista Personajelor",
        "characters.profile_group": "Profil Personaj",
        "characters.evidence_group": "Dovezi",
        "characters.canonical_name": "Nume Canonic",
        "characters.aliases": "Aliasuri",
        "characters.gender_hint": "Indicatie Gen",
        "characters.age_band": "Categorie de Varsta",
        "characters.role_summary": "Rezumat Rol",
        "characters.description": "Descriere",
        "characters.temperament": "Temperament",
        "characters.social_status": "Statut Social",
        "characters.speaking_style": "Stil de Vorbire",
        "characters.accent": "Accent / Dialect",
        "characters.voice_notes": "Note Voce",
        "characters.relationship_hints": "Indicii Relatii",
        "characters.confidence": "Incredere",
        "characters.evidence_note": "Fragmentul de dovada selectat din sursa va aparea aici.",
        "narrator.title": "Narator",
        "narrator.language": "Limba Naratorului",
        "narrator.summary": "Alege un profil de narator, adapteaza promptul sau creeaza un profil nou pentru limba curenta.",
        "narrator.profiles_group": "Profiluri Narator",
        "narrator.new_profile": "Profil Nou",
        "narrator.setup_group": "Configurare Profil",
        "narrator.profile_name": "Nume Profil",
        "narrator.designer_group": "Prompt Designer Voce",
        "narrator.preview_group": "Text Previzualizare",
        "narrator.create_profile": "Creeaza Profil",
        "narrator.save_profile": "Salveaza Profil",
        "narrator.delete_profile": "Sterge Profil",
        "narrator.preview": "Previzualizare",
        "placeholder.narration_plan.title": "Plan Naratie",
        "placeholder.narration_plan.note": "Planificarea naratiei nu este implementata inca.",
        "placeholder.generation.title": "Generare",
        "placeholder.generation.note": "Generarea nu este implementata inca.",
        "placeholder.export.title": "Export",
        "placeholder.export.note": "Exportul nu este implementat inca.",
        "home.title": "Acasa / Proiect",
        "home.summary_group": "Rezumat Proiect",
        "home.project": "Proiect",
        "home.path": "Cale",
        "home.stage": "Etapa",
        "home.source": "Sursa",
        "home.none": "niciuna",
        "home.source_import_group": "Import Sursa",
        "home.source_import_note": "Fiecare proiect este legat de exact un fisier sursa. Dupa import, selectia este blocata pentru acel proiect.",
        "home.select_source": "Selecteaza Fisierul Sursa",
        "home.no_source": "Nu a fost importata nicio sursa.",
        "home.locked_source_prefix": "Sursa blocata",
        "home.locked_source_suffix": ". Creeaza un proiect nou pentru a folosi alt fisier.",
        "home.workflow_group": "Progres Flux de Lucru",
        "home.status.not_started": "Nepornit",
        "home.status.in_progress": "In Curs",
        "home.status.finished": "Finalizat",
        "home.stage_label.source_selected": "Sursa Selectata",
        "home.stage_label.text_cleanup_ready": "Curatare Text",
        "home.stage_label.text_chunking_ready": "Segmentare Text",
        "home.stage_label.translation_ready": "Traducere AI",
        "home.stage_label.character_discovery_ready": "Personaje",
        "home.stage_label.narrator_definition_ready": "Definire Narator",
        "home.stage_note.inactive.source_selected": "Creeaza sau deschide mai intai un proiect.",
        "home.stage_note.inactive.text_cleanup_ready": "Creeaza sau deschide mai intai un proiect.",
        "home.stage_note.inactive.text_chunking_ready": "Creeaza sau deschide mai intai un proiect.",
        "home.stage_note.inactive.translation_ready": "Creeaza sau deschide mai intai un proiect.",
        "home.stage_note.inactive.character_discovery_ready": "Creeaza sau deschide mai intai un proiect.",
        "home.stage_note.inactive.narrator_definition_ready": "Creeaza sau deschide mai intai un proiect.",
        "home.stage_note.active.source_selected": "Selecteaza si importa un singur fisier sursa pentru proiect.",
        "home.stage_note.active.text_cleanup_ready": "Pregateste textul importat pentru segmentare.",
        "home.stage_note.active.text_chunking_ready": "Imparte textul curatat in segmente de lucru.",
        "home.stage_note.active.translation_ready": "Tradu setul de segmente atunci cand este necesar.",
        "home.stage_note.active.character_discovery_ready": "Extrage si revizuieste setul de personaje.",
        "home.stage_note.active.narrator_definition_ready": "Selecteaza si adapteaza definitia naratorului pentru proiect.",
        "project.new_dialog_intro": "Alege dosarul parinte unde va fi creat proiectul si introdu numele exact al proiectului.",
        "project.parent_folder": "Dosar Parinte",
        "project.project_name": "Nume Proiect",
        "project.browse": "Rasfoieste",
        "project.create": "Creeaza",
        "project.cancel": "Anuleaza",
        "project.error_missing_parent": "Selecteaza dosarul parinte in care trebuie creat proiectul.",
        "project.error_missing_name": "Introdu numele exact al proiectului.",
        "project.error_no_active_project": "Creeaza sau deschide un proiect inainte de a importa un fisier sursa.",
        "project.error_locked_source": "Acest proiect are deja un fisier sursa blocat. Creeaza un proiect nou pentru a folosi alta sursa.",
        "project.repair_step_prefix": "Proiectul este corupt la pasul",
        "project.repair_reset_suffix": "Aceasta reparatie va recrea si reseta acel pas si toate folderele pasilor urmatori.",
        "project.repair_metadata_only": "Aceasta reparatie va actualiza metadatele proiectului la ultima etapa coerenta a fluxului.",
        "project.repair_confirm": "Vrei sa repari proiectul acum?",
    },
}


@trace_function(_UI_STATE_LOGGER)
def translate(key: str, language: str | None) -> str:
    """
    @brief      Resolve one UI string for one application language.
    @param[in]  key Stable UI string identifier.
    @param[in]  language Target UI language code.
    @return     Translated UI string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    resolved_language = language if language in _UI_STRINGS else _DEFAULT_LANGUAGE
    return _UI_STRINGS[resolved_language].get(
        key,
        _UI_STRINGS[_DEFAULT_LANGUAGE].get(key, key),
    )


@trace_function(_UI_STATE_LOGGER)
def get_ui_strings(language: str | None) -> dict[str, str]:
    """
    @brief      Return a copy of the UI string catalog for one language.
    @param[in]  language Target UI language code.
    @return     Language-specific UI string mapping.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    resolved_language = language if language in _UI_STRINGS else _DEFAULT_LANGUAGE
    return deepcopy(_UI_STRINGS[resolved_language])


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
    global _BASE_FONT_POINT_SIZE

    if application is None:
        return

    scale_key = (
        ui_text_scale if ui_text_scale in _UI_SCALE_FACTORS
        else config.DEFAULT_UI_TEXT_SCALE
    )
    if ui_text_scale not in _UI_SCALE_FACTORS:
        _UI_STATE_LOGGER.warning(
            "Replaced invalid UI text scale with the default value.",
            extra={
                "func_name": "apply_text_scale",
                "event": "ui-settings-repair",
                "result": config.DEFAULT_UI_TEXT_SCALE,
            },
        )
    current_font = application.font()
    if _BASE_FONT_POINT_SIZE is None:
        current_size = current_font.pointSizeF()
        _BASE_FONT_POINT_SIZE = current_size if current_size > 0 else 9.0

    scaled_font = QFont(current_font)
    scaled_font.setPointSizeF(_BASE_FONT_POINT_SIZE * _UI_SCALE_FACTORS[scale_key])
    application.setFont(scaled_font)

    for widget in application.topLevelWidgets():
        if isinstance(widget, QWidget):
            widget.setFont(QFont(scaled_font))
            widget.update()


    _UI_STATE_LOGGER.info(
        f"Applied UI text scale '{scale_key}'.",
        extra={
            "func_name": "apply_text_scale",
            "event": "ui-text-scale-applied",
            "result": scale_key,
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
    @brief      Apply persisted UI language and text scale to the shell.
    @param[in]  application Running Qt application instance.
    @param[in]  main_window Main application window.
    @param[in]  settings_payload Persisted application settings payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    apply_text_scale(
        application,
        str(settings_payload.get("ui_text_scale", config.DEFAULT_UI_TEXT_SCALE)),
    )
    apply_language(
        main_window,
        str(settings_payload.get("language", config.DEFAULT_LANGUAGE)),
    )


# END OF FILE
