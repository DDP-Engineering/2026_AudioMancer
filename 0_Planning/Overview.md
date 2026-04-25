<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Overview

## 1. Purpose

`AudioMancer` is an offline-first desktop application for generating audiobooks
from written books with personalized character voices or real cloned voices.

Its purpose is to take a written book, transform it into clean structured
narration data, and support the operator through the full pipeline required to
generate audiobooks with personalized character voices or real voice-based
narration in a clear, efficient, and maintainable workflow.

The application should also provide offline end-user help for non-technical
book readers. The current English and Romanian help bundles are maintained
under `05_SoftwareDocu/UserGuide/` and `05_SoftwareDocu/UserGuide_ro/`, then
delivered as local HTML.

## 2. Final Product Vision

The final application should be a complete audiobook-preparation workstation,
not only a collection of separate tools.

It should allow an operator to:

- create and manage one project per book
- import source material from supported formats
- extract raw text from the source
- clean and normalize the text into canonical book content
- split the content into meaningful narration chunks
- discover and manage speaking characters and character traits
- translate chunks when needed
- prepare narration-relevant metadata for character voice selection, real voice use, and later generation stages
- review, correct, and approve intermediate results
- preserve all important artifacts inside a deterministic project structure
- reopen a project and continue work without losing state

## 3. Core Product Principles

The final application should follow these principles:

- offline-first by default
- distributable as a zip archive without installer dependency
- runnable on Windows 11 and Ubuntu 22.04 LTS or newer
- deterministic project storage
- clear step-by-step operator workflow
- simple and maintainable code structure
- explicit artifacts and reports for every major processing stage
- safe resume and recovery for long-running operations
- operator review before downstream use of generated data
- modular implementation without unnecessary abstraction

## 4. Intended Workflow

The intended end-to-end workflow is:

1. create or open a project
2. import and lock the source material for that project
3. extract raw text
4. clean and normalize the extracted text
5. split the text into canonical narration chunks
6. run optional AI-assisted processing where useful and justified
7. review and edit chunk, translation, and character outputs
8. prepare downstream narration and generation data
9. generate reviewed speech-block audio with assigned voices
10. assemble and export final audiobook outputs

Each stage must have:

- clear inputs
- clear outputs
- visible state to the operator
- persisted artifacts on disk
- a predictable reset or rerun behavior

## 5. Major Functional Areas

### 5.1 Project Management

The application must support:

- project creation
- project opening and reopening
- deterministic flat project structure
- persisted project manifest and operation state
- safe handling of incomplete or failed operations

### 5.2 Source Import

The application must support:

- importing supported source files
- locking one selected source per project
- preserving imported source artifacts
- validating format and basic integrity

Current implementation supports:

- `TXT`
- `PDF`
- `RTF`
- `DOCX`
- `ODT`
- `Markdown`
- `EPUB`

Other formats should be added only when the import and extraction path remains
simple and reliable.

### 5.3 Text Extraction

The extraction stage must:

- produce canonical raw text from the imported source
- preserve extraction reports and warnings
- make failures understandable to the operator
- avoid hidden state or silent fallback behavior

### 5.4 Text Cleanup

The cleanup stage must:

- normalize line breaks, spacing, and obvious source noise
- preserve meaningful text structure
- avoid destructive cleanup decisions without traceable logic
- support deterministic cleanup and AI-assisted cleanup where useful

The cleaned text must become the canonical base for downstream operations.

### 5.5 Text Chunking

The chunking stage must:

- transform cleaned text into narration-ready chunks
- preserve ordering and source traceability
- support deterministic chunking and AI-assisted chunking
- keep chunk metadata explicit and reviewable

Chunks are the main working unit for later translation, character analysis, and
narration preparation.

### 5.6 Character Discovery And Management

The character workflow must:

- identify relevant speaking characters
- gather evidence from chunks
- build editable character profiles
- preserve operator control over the final character data
- separate discovered data from approved canonical data when useful

Character handling must be practical for audiobook work, not academic.
Only data that helps downstream narration should be kept.

### 5.7 Translation

The translation workflow must:

- translate chunks into a selected target language when needed
- preserve source-to-translation alignment
- support partial progress, edits, approvals, and retranslation
- keep translation state explicit and reviewable

### 5.8 Voice And Narration Preparation

The application should include a dedicated preparation stage for personalized
character voices, real voice use, and downstream audio generation.

This stage should consolidate:

- cleaned and approved chunk text
- approved character profiles
- character-to-voice assignment data
- real-voice assignment data where supported
- pronunciation or style notes where needed
- narration-oriented metadata required by downstream generation

This is not the final step. It prepares the canonical generation plan used by
later audio synthesis and assembly stages.

### 5.9 Audio Generation

The application should support generation of audio per approved Speech Block
using the assigned narrator and character voice plan.

This stage should support:

- manual insertion and deletion of Speech Blocks when extraction or AI splitting
  needs operator correction
- narrator voice generation for narration Speech Blocks
- character voice generation for dialogue or character-linked Speech Blocks
- metadata-only Speech Blocks such as pause, indication, and background-noise
  markers without treating them as narrator or character speech
- use of personalized synthetic voices
- use of real cloned voices where supported
- generation of only the currently approved Speech Blocks so partial review can
  progress without forcing approval of the whole book
- regeneration of selected Speech Blocks without rerunning the whole book
- persisted per-block audio artifacts and generation metadata

The generation stage should make it possible to use different voices inside the
same book, for example narrator voice plus one or more character voices.

The current implementation generates WAV files through the Audio Blocks workflow
under `audio_blocks/`, keeps unapproved Speech Blocks pending, stores
metadata-only operation blocks without VoiceWeaver generation, and advances only
after generated audio is explicitly approved.

### 5.10 Export And Assembly

The application supports a first WAV-only assembly stage for final audiobook
outputs.

The current implementation supports these Audio Assembly output modes:

- one audio file for the whole book
- split audio files by configured time limit
- one audio file per source text chunk

The assembly stage supports:

- combining generated Speech Block audio in canonical order
- converting metadata-only pause blocks into silence
- deterministic output naming
- project-local `audiobook/` deliverables
- `audio_assembly_state.json` and `audio_assembly_report.json`
- completed-output resume when the source Audio Blocks and settings fingerprint
  still match
- local generated-output playback from the Audio Assembly page

MP3 encoding, chapter metadata, silence trimming, volume normalization, pitch
changes, and cover-art embedding remain future work.

## 6. Non-Functional Goals

The final application should be:

- fast for common operator tasks
- clearer to read and maintain in the codebase
- easier to test at unit and runtime level
- more resilient when interrupted or reopened
- more consistent in naming, storage, and state handling
- explicit about what is deterministic and what is AI-assisted
- distributable as a simple zip archive
- runnable on Windows 11 and Ubuntu 22.04 LTS or newer without OS-specific redesign

## 7. Architecture Direction

The preferred technical direction is:

- functional-first service layer
- small dataclasses for structured data contracts
- classes only where they are truly justified by UI or runtime ownership
- explicit dependency passing
- deterministic file-based project persistence
- cross-platform packaging and runtime behavior for Windows 11 and Ubuntu 22.04 LTS minimum
- simple logging and tracing
- minimal hidden global state

The application should avoid:

- speculative framework layers
- service wrappers that only forward calls
- hidden runtime mutation behind broad object graphs
- unnecessary backward-compatibility shims

## 8. Technology Baseline

The existing application work establishes a practical technology baseline for
this type of desktop product.

Technologies currently used are:

- `Python 3.12` as the main implementation language
- `uv` for environment and dependency management
- `PySide6` for the desktop UI
- `PyMuPDF` for `PDF` text extraction
- `langdetect` for language detection
- JSON files for manifests, reports, settings, and operation artifacts
- Python standard library concurrency primitives for background work
- Python standard library HTTP/JSON handling for OpenAI-compatible provider integration
- `pytest` for automated tests
- `pytest-qt` for Qt/UI-oriented tests
- `PyInstaller` for packaged desktop builds
- zip archive as the final delivery format

This should be treated as the starting baseline, not as a hard constraint.
The new application may refine or replace parts of this stack, but only when
the result is simpler, clearer, and operationally justified.

## 9. Operator Experience Goals

The operator experience should be:

- clear
- guided
- low-friction
- safe for long-running work
- transparent about what data is generated and where it is stored

The UI should make it easy to understand:

- the current project state
- the current workflow stage
- what input each operation uses
- what output each operation produced
- what can be rerun safely
- what downstream data will be invalidated by rerunning an earlier stage

## 10. Success Criteria For The Final Application

The application can be considered functionally complete when it supports the
full intended workflow with stable persistence and operator review.

That means:

- all major stages exist and are connected coherently
- the project can be reopened at any point without losing meaningful state
- artifacts and reports are written deterministically
- long-running operations can fail or stop without corrupting the project
- operator review and correction is supported where it matters
- the codebase remains simple, readable, and maintainable

## 11. Immediate Planning Implication

The implementation should proceed as a clean, coherent build from explicit product and architecture decisions.

The project should define its own structure, contracts, and implementation details in a simple and coherent way.



