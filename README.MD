<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# 2026_AudioMancer

Repository for the AudioMancer desktop application and its planning,
documentation, tooling, delivery, and support material.

## Top-Level Structure

- `0_Planning/`
- `01_Documentation/`
- `02_Tools/`
- `04_Software/`
- `05_SoftwareDocu/`
- `07_Delivery/`
- `09_Others/`

## Software Locations

The software subtrees currently live under:

- `04_Software/AudioMancer/`

## Current Implementation

`04_Software/AudioMancer/` contains the Python 3.12/PySide6 application. The
current app supports project creation with locked audiobook language and
narration mode, source import, extraction, deterministic and AI cleanup,
optional operator rules for AI cleanup, chunking, translation, character
discovery, Narator profile, and Speech Blocks prompts, resumable AI cleanup with current model settings,
deterministic and AI chunking, locked-target AI translation, character
discovery with explicit age-domain voice handoff, narrator and character voice preparation, mode-aware Speech Blocks,
Audio Blocks, WAV Audio Assembly deliverables, Home-page TXT/Markdown exports
for completed text artifacts, ZIP exports for available narrator/character
voice samples and Audio Assembly outputs, and external full-project ZIP
snapshots.
Manual Text Chunking edits, inserts, and deletes now use the selective
impact path to preserve unaffected Translation, Speech Blocks, and Audio
Blocks work while resetting only affected chunks plus Audio Assembly.
Text Cleanup reruns, manual cleaned-text edits, and full Text Chunking
regeneration now preserve completed Character Discovery, Narator Voice, and
Character Voices artifacts while resetting regenerated text, Speech Blocks,
Audio Blocks, and Audio Assembly data.
Manual Character Discovery add/edit/delete actions now also use the selective
impact path: character add preserves generated downstream work,
character edit unapproves only assigned Speech Blocks and resets only affected
Audio Blocks, and character delete moves assigned Speech Blocks to Narrator
instead of deleting them.
Narrator and Character Voices changes now preserve Speech Blocks and reset only
Audio Blocks that use the affected voice target, while global voice-language or
runtime-model changes reset all generated Audio Blocks and Audio Assembly.
Character Voices readiness now writes the Home workflow operation summary from
the selected narrator sample plus every character sample, so reopened projects
do not show generated character voices as `Not Started`.
Manual Speech Blocks insert-after/delete/edit/reset/approval actions now
preserve stable Speech Block IDs, reset only affected Audio Blocks when audio
input changes, and reset Audio Assembly whenever final order, approval, or
audio inputs change. Speech Blocks review also exposes selected-block audio
regeneration plus Play/Stop preview controls mirrored from Audio Blocks.
Same-narrator Speech Blocks now ask the AI for compact boundary IDs only and
construct exact narrator spans deterministically, reducing malformed JSON and
source-copy mismatches from local models.
Audio Blocks selected reset, selected regeneration, approval, and unapproval
now preserve unrelated generated audio and reset only Audio Assembly outputs.
Audio Assembly settings changes and reruns now preserve upstream Audio Blocks
while replacing only assembly outputs/state/report.
Current package version is `1.1.0`; Settings now supports built-in and custom
runtime UI themes with separate UI-control and text-window font controls,
theme color roles, and portable JSON import/export. Text Chunking now allows
operators to start a fully manual chunking pass from cleaned text before
generated chunks exist. Narator Voice and Character Voices now accept validated
WAV imports with operator-entered sample text for Qwen TTS Base voice cloning.
Character Discovery now hands off explicit age guidance to Qwen voice-designer
prompts, and AI Settings plus TTS Settings now share the `Cancel`, `Save`, and
`OK` flow used by the Settings dialog.

Focused implementation documentation is maintained in `05_SoftwareDocu/`.
The end-user help bundles are maintained in `05_SoftwareDocu/UserGuide/` and
`05_SoftwareDocu/UserGuide_ro/`, then packaged as offline HTML.
Validation commands and targeted test groups are listed in
`04_Software/AudioMancer/README.MD`; the current full regression baseline is
also summarized in `HowToTest.md`.
