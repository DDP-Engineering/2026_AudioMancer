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
- choose and lock the audiobook language and narration mode for that project
- import source material from supported formats
- extract raw text from the source
- clean and normalize the text into canonical book content
- split the content into meaningful narration chunks
- discover and manage speaking characters and character traits
- translate chunks when needed
- prepare narration-relevant metadata for character voice selection, real voice use, and later generation stages
- batch-regenerate current character voice samples when the operator wants a fresh voice pass
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
- release metadata kept in the package metadata and changelog rather than
  duplicated throughout planning files
- safe resume and recovery for long-running operations
- operator review before downstream use of generated data
- readable review panes that keep practical minimum widths when the operator
  drags splitters on dense workflow pages
- modular implementation without unnecessary abstraction

## 4. Intended Workflow

The intended end-to-end workflow is:

1. create or open a project
2. import or replace the source material before the project is started
3. choose and lock the source, audiobook language, and narration mode
4. extract raw text
5. clean and normalize the extracted text
6. split the text into canonical narration chunks
7. run optional AI-assisted processing where useful and justified
8. review and edit chunk, translation, and character outputs
9. prepare downstream narration and generation data
10. generate reviewed speech-block audio with assigned voices
11. assemble and export final audiobook outputs

Each stage must have:

- clear inputs
- clear outputs
- visible state to the operator
- persisted artifacts on disk
- a predictable reset or rerun behavior
- a preservation-first v2 impact behavior for local manual edits when stable
  IDs make the affected chunk, Speech Block, or voice target unambiguous

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
- persist cleanup output, reports, metadata, and operation state atomically
- tolerate malformed cleanup state by restarting cleanly instead of blocking
  the next run
- keep deterministic resume tied to an input fingerprint and bounded
  checkpoints without changing uninterrupted cleanup output

The cleaned text must become the canonical base for downstream operations.

### 5.5 Text Chunking

The chunking stage must:

- transform cleaned text into narration-ready chunks
- preserve ordering and source traceability
- support deterministic chunking and AI-assisted chunking
- keep chunk metadata explicit and reviewable
- keep long chunking runs resumable through bounded checkpoints and atomic
  artifact persistence

Chunks are the main working unit for later translation, character analysis, and
narration preparation.

### 5.6 Character Discovery And Management

The character workflow must:

- identify relevant speaking characters
- gather evidence from chunks
- build editable character profiles
- keep evidence-backed age-domain hints when they affect voice design
- preserve operator control over the final character data
- separate discovered data from approved canonical data when useful

Character handling must be practical for audiobook work, not academic.
Only data that helps downstream narration should be kept.

### 5.7 Translation

The translation workflow must:

- translate chunks into the project-locked target language when needed
- create pass-through translation state when source and target languages match
- preserve source-to-translation alignment
- support partial progress, edits, approvals, and retranslation
- keep translation state explicit and reviewable
- protect completed translated output with atomic project artifacts and
  recoverable cancel/failure state during interrupted runs

### 5.8 Voice And Narration Preparation

The application should include a dedicated preparation stage for personalized
character voices, real voice use, and downstream audio generation.

This stage should consolidate:

- cleaned and approved chunk text
- approved character profiles
- locked audiobook language and narration mode
- character-to-voice assignment data
- real-voice assignment data where supported
- pronunciation or style notes where needed
- narration-oriented metadata required by downstream generation
- explicit sex/gender and age-domain handoff text for character voice-design
  prompts so TTS voice design has stable vocal anchors

Current narrator preparation also preserves previous usable samples when a new
VoiceWeaver sample run fails or is cancelled, writes narrator metadata and WAV
artifacts atomically, and records failed/cancelled AI narrator-profile
generation checkpoints for compatible resume.

Character Voices applies the same persistence posture for character target
metadata and samples: unchanged same-narrator refreshes stay read-only, failed
or cancelled sample generation preserves the previous sample, and batch
generation continues to regenerate all current character targets.

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
- operation Speech Blocks such as pause, indication, and Scene Ambience markers
  without treating them as narrator or character speech
- use of personalized synthetic voices
- use of real cloned voices where supported
- generation of only the currently approved Speech Blocks so partial review can
  progress without forcing approval of the whole book
- regeneration of selected Speech Blocks without rerunning the whole book
- persisted per-block audio artifacts and generation metadata

The generation stage should support both locked narration modes: one narrator
for the whole book, and narrator plus one or more character voices. Same-narrator
projects should preserve continuous phrases and emotional flow by segmenting
text for the TTS budget instead of forcing dialogue speaker splits.

The current implementation generates WAV files through the Audio Blocks workflow
under `audio_blocks/`, keeps unapproved Speech Blocks pending, stores
pause and indication operation blocks without VoiceWeaver generation, and can
generate approved Scene Ambience prompt blocks through the sound-prompt runtime
path when that setting is enabled. The Speech Blocks review page can invoke
selected-block audio regeneration through a compact `Generate Audio` button and
Play/Stop preview through the same Audio Blocks controller path so operators
can check formatting before moving to the Audio Blocks page.
Audio Blocks and VoiceWeaver runtime calls also write concise diagnostic log
records for generation start, accepted sound-prompt requests, and completed
generated files.

Application-level Settings, AI Settings, and TTS Settings should use consistent
dialog semantics: Cancel discards unsaved edits, Save persists while keeping the
dialog open, and OK persists then closes where the dialog supports Apply-style
workflows.

### 5.10 Export And Assembly

The application supports a first WAV-only assembly stage for final audiobook
outputs.

The current implementation supports these Audio Assembly output modes:

- one audio file for the whole book
- split audio files by configured time limit
- one audio file per source text chunk

The assembly stage supports:

- combining generated Speech Block audio in canonical order
- optionally including generated Scene Ambience sound blocks in canonical order
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
- what expensive downstream work will be preserved after local manual edits
