<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer — Implementation Review, 2026-08-02

Component-by-component bug review of `04_Software/AudioMancer/src/audiomancer`
(~68,600 lines, 103 modules) against the 15 component pages in
`.agentic/knowledge/`.

## Implementation updates — 2026-08-05

### AI Runtime — AI-1, AI-3, AI-4, and AI-8

Commit `6f75eaa` resolves AI Runtime findings AI-1, AI-3, AI-4, and AI-8
under `REQ-FUNC-8eba808c`, `REQ-FUNC-e9d13e10`, `REQ-FUNC-20817a63`,
`REQ-FUNC-6f8e52c8`, and `REQ-FUNC-6c33e242`.

- **AI-1 resolved:** the settings editor tracks the stable profile ID it
  represents and writes outgoing widget values back before selection, list,
  default-profile, Connect, or save transitions can change the active row.
- **AI-3 resolved:** a failed backend probe updates only failure status and
  message, preserving the profile's last successful model discovery metadata
  and the operator's typed model and configured context window.
- **AI-4 resolved:** probes return a positive context window together with the
  exact model that owns it. Generic OpenAI-compatible, LM Studio, and Ollama
  discovery use provider-specific metadata, while manual context overrides
  remain authoritative.
- **AI-8 resolved:** connect-time HTTP, timeout, socket/read, protocol, decode,
  and JSON failures are converted into safe probe failures without exposing
  credentials, headers, or response bodies and without escaping the Qt slot.

Focused verification passed 69 tests. The full suite passed 1,301 tests with
1 skipped and 1 deselected; the only warning was the existing `audioop`
deprecation warning. Post-suite backend/profile regressions (23 tests), Ruff,
and compile checks also passed.

### AI Translation - TR-1, TR-2, TR-3, and TR-6

Commit `488973a` resolves AI Translation findings TR-1, TR-2, TR-3, and
TR-6 under `REQ-FUNC-9a7e98c9`, `REQ-UX-7e8fb80a`, `REQ-UX-31620904`,
`REQ-UX-1373b3b5`, `REQ-UX-eb55be5b`, `REQ-UX-3dae2eb0`, and
`REQ-FUNC-ee95beb7`.

- same-content refreshes leave both editor documents untouched, preserving the
  selected stable chunk, cursor/anchor, selection, undo/redo history, and
  horizontal/vertical scrolling while real authoritative changes still load;
- Start/Resume persists the exact pending edit before worker dispatch and busy
  state stops the debounce timer, eliminating the delayed UI-write race;
- a live enabled AI profile survives every shared translation refresh, with
  safe default/first-enabled fallback when it is removed or disabled; and
- selected-chunk retranslation remains unavailable before translation starts,
  with a defensive controller boundary that has no worker, prompt, error,
  document, or manifest-stage side effects.

Focused AI Translation verification passed 39 tests. The configured full suite
passed in 1497.4 seconds, and the task-scoped strict AEGIS check reported zero
errors. TR-4 and TR-5 remain open; the original findings table below remains
the 2026-08-02 inventory.

## Implementation updates — 2026-08-04

### PDF reading order — TC-1

Commit `dafd8ed` resolves TC-1 under `REQ-FUNC-6dd114ad` and
`REQ-FUNC-6c977d3b`.

- PDF reconstruction now assigns every physical text line to exactly one
  exclusive column/spanning classification, so centered page numbers, running
  footers, and ornaments cannot be emitted twice or inflate both column counts.
- Top, bottom, and ambiguous spanning material is exclusive as well; clear
  two-column order and existing reason codes remain unchanged, while genuinely
  ambiguous layouts retain the existing uncertainty warning.
- Every single-column return assigns column zero, including sparse pages and
  unusable page widths, preventing false Cleanup page-column transitions.
- Identity-permutation helper coverage and a public PDF Extraction regression
  passed alongside all 40 Extraction tests and the full suite at 1,264 passed,
  1 skipped, and 1 deselected.

### Source-import robustness — PL-2, TC-4, and TC-10

Commit `e7d67a52d4a82d3e658de69b4eed62f900c1d873` completes the source-import robustness bundle under `REQ-UX-da3b47c4`, `REQ-FUNC-c7960ee8`, and `REQ-FUNC-379827ff`.

- **PL-2 resolved:** Project creation, source import, and confirmed repair contain `OSError` and `ValueError` locally, show a localized warning with the original error, and stop before activation, success notification, or project/manifest mutation.
- **TC-4 resolved:** TXT/RTF decoding now honors BOM and RTF code-page declarations, selects among UTF-8 and supported legacy codecs using deterministic text evidence, supports Windows-1251 Cyrillic, and records the actual encoding used.
- **TC-10 resolved:** EPUB members are decoded from raw bytes using BOM and XML/HTML declarations; invalid declarations identify the affected item, and the ledger reports a uniform encoding or deterministic `mixed(...)` value.
- Focused verification passed 49 tests. The full suite passed 1,256 tests with 1 skipped and 1 deselected.

## Implementation updates — 2026-08-03

### Project Lifecycle — PL-1, PL-3, and PL-5

Commit `2db1297660d200b7101b8b3c59dbba8dbda9439d` resolves Project Lifecycle findings PL-1, PL-3, and PL-5 under `REQ-FUNC-b1f49831`:

- processed-project source replacement now clears Extraction and every downstream artifact, resets all compact operation summaries, and returns the manifest to `source_selected`;
- the new source is copied and atomically promoted before the previous stored source is deleted, while a failed copy leaves the complete previous project state unchanged;
- reserved generated-artifact names are avoided case-insensitively through the centralized operation artifact registry; and
- the new source plus unlocked target-language, selected-voice-language, and voice-assignment options are preserved.

The full delivery suite passed with 1,205 tests, 1 skipped, and 1 deselected.

### Text Cleanup — TC-2

Commit `0e8467f4a56e0fe725d1cc6dbab8a664e2e08ba6` resolves TC-2 under
`REQ-FUNC-2ab78634`:

- automatic Cleanup finalization/rerendering and manual cleaned-text saves now
  share one publication transition;
- Chunking and every downstream artifact are still deleted through the
  centralized operation-reset registry, while Project Lifecycle's shared
  manifest-reset builder defaults the matching compact summaries in the same
  successful transition;
- Cleanup remains completed at `text_chunking_ready`, while the source,
  Extraction state and artifacts, project options, and new Cleanup output are
  preserved;
- manifest or artifact persistence failures propagate before Cleanup returns
  success or reports 100% progress; and
- both paths reopen with coherent state instead of requesting repair for stale
  downstream summaries.

Regression coverage starts both paths with completed downstream summaries and
real downstream artifacts, checks every preservation and reset invariant, and
injects manifest persistence failure into both paths. The focused delivery set
passed 121 tests with 1 skipped; the configured full suite completed
successfully across 1,210 selected tests with 1 skipped and 1 deselected.

### Text Cleanup — TC-3 and TC-12

Commit `362995d` resolves TC-3 under `REQ-FUNC-75d5b274` and
`REQ-REL-43c63d8c`, and TC-12 under `REQ-UX-6fb5efc7` and
`REQ-UX-e1bb52ba`:

- confirmed reruns of completed Cleanup now use the canonical Cleanup reset
  transition before the worker starts, so Cleanup and all later results are
  removed and the worker receives the reset manifest rather than a cached
  completed document;
- running, paused, finalizing, and failed Cleanup documents skip destructive
  rerun handling and retain their checkpoints for the service's established
  resume/rebuild rules;
- active manual cleaned-text edits survive same-project refreshes, suppress
  conflicting Extract, Cleanup, Reset Cleanup, and AI-profile actions, and
  retain Save/Cancel behavior; and
- New Project and Open Project require a localized No-by-default confirmation
  before abandoning a modified draft. Cancelling either project picker keeps
  the original project and draft; a successful activation clears the old edit
  state and loads the new project's authoritative text.

Focused controller, page, state, Home, and localization coverage passed 27
tests; the full delivery suite passed 1,279 tests, with 1 skipped and 1
deselected.

### Text Chunking - CH-2

Commit `e829071` resolves Text Chunking finding CH-2 under
`REQ-FUNC-18dd9ec2`:

- the centralized manual-mutation persistence boundary now loads the
  authoritative Chunking document before any write or downstream invalidation;
- `running`, `cancelled`, and `failed` documents raise `ValueError` directing
  the operator to finish, resume, or reset the current Chunking run before
  editing chunks;
- rejected operations preserve byte-for-byte the Chunking document,
  `project.json`, and representative Translation, Character Discovery, Speech
  Blocks, Audio Blocks, and Audio Assembly artifacts; and
- completed-document edit, insertion, and deletion behavior, as well as first
  manual insertion when no document exists, remain unchanged.

The regression parameterizes all three resumable statuses and all three public
manual operations. The delivery suite passed with 1,221 tests, 1 skipped, and
1 deselected.

### Text Chunking - CH-1 and CH-3

Commit `d8a08bd` resolves Text Chunking findings CH-1 and CH-3 under
`REQ-FUNC-bb809764`, `REQ-UX-9501c338`, `REQ-FUNC-56dfec40`, and
`REQ-FUNC-16c16214`. Every no-prefix AI window, including a single or final
window, now uses the shared structural fallback and increments its sole
persisted count exactly once. Progress identifies the absolute paragraph range,
and the terminal warning plus manifest summary report the accumulated count.
The page-state path now derives checkpoint-based running, resumable, completed,
and not-started notes from the authoritative Chunking document without an
invented total-progress value. Focused Chunking descriptor, state,
authoritative-document, and localization tests passed (68 tests).

### Operation Orchestration - OC-1

**Resolved 2026-08-03 in commit `36e3070`** under `REQ-FUNC-ccc76f34` and
`REQ-FUNC-e45d3577`. `workflow_controller_service.sync_manifest_operation_from_disk`
no longer rebuilds and saves `project.json` from the window's stale manifest.
It delegates operation-summary and optional-stage persistence to
`project_workspace_service.sync_manifest_operation_summary`, which reloads the
current manifest from disk and only promotes the workflow stage. The final
window refresh receives the exact reloaded manifest.

The fix preserves manifest fields written after the window snapshot, ignores a
requested lower stage, preserves completed downstream summaries, refreshes the
requested summary from persisted operation state, and still refreshes the
window without writing a replacement manifest when the loader returns `None`
without a stage request. Focused controller and Project Lifecycle regressions
passed (10 tests); the delivery suite passed with 1,212 tests, 1 skipped, and
1 deselected. Any OC-1 text below is retained as historical review evidence and
is superseded by this resolution update.

The original findings table remains the 2026-08-02 review inventory. Applying
the recorded updates, including AI Runtime AI-1, AI-2, AI-3, AI-4, and AI-8
and AI Translation TR-1, TR-2, TR-3, and TR-6, leaves 7 Critical, 30 Major,
and 54 Minor findings open across the review, with
Project Lifecycle at 0 Critical, 0 Major, and 3 Minor, Text Extraction +
Cleanup at 0 Critical, 0 Major, and 7 Minor, Text Chunking at 0 Critical,
1 Major, and 1 Minor, AI Runtime at 0 Critical, 0 Major, and 4 Minor, and AI
Translation at 0 Critical, 1 Major, and 1 Minor.

### AI Runtime — AI-2

**Resolved 2026-08-03 in commit `6a866da`** under `REQ-FUNC-3875ac3b`.
The provider client now rejects a first chat-completion choice whose
`finish_reason` explicitly reports `length` before it can parse, locally repair,
or send the response to a model-based JSON-repair request. It raises a fixed,
non-sensitive `RuntimeError` naming the provider output-token limit, logs the
request as a failure, and sends no additional provider request. Normal `stop`
and omitted finish reasons still parse normally, and non-truncated malformed
JSON retains its existing repair behavior. Focused provider tests, direct
Cleanup/Chunking/Translation caller tests, and the complete suite passed.

**Scope of the review.** Only clear straight-path errors: real implementation
bugs on normal or lightly-abnormal runs, copy-paste defects, and missing
checks that crash the app or corrupt persisted project data. Style, naming,
docstrings, test coverage and micro-performance were deliberately ignored, as
were "an LLM produced a mediocre result the operator can fix" cases — that is
the design, not a defect.

**Baseline health.** `ruff check src tests` passes clean. The test suite runs
**1197 passed, 1 failed, 1 skipped** in 21 minutes. The single failure is not a
product bug: `test_chunking_single_document_contract.py:527` reads
`.agentic/knowledge/components/Text_Chunking.md`, but the AEGIS Light adoption
moved the component pages up one level to `.agentic/knowledge/`. It is the only
test in the suite referencing that path, so the fix is deleting `"components" /`
from that one line. Worth doing promptly — a red suite trains people to ignore
red suites. The architecture is
sound and consistently applied: the service/controller/page split holds, atomic
writes are used almost everywhere, path containment is genuinely enforced, and
the localization catalogue is provably complete (977 keys per language, no
placeholder mismatches). This is a well-built codebase. The findings below are
concentrated in a few recurring seams, not spread evenly.

---

## Findings at a glance

| # | Component | Critical | Major | Minor |
|---|---|---|---|---|
| [01](01_Operation_Orchestration_App_Shell.md) | Operation Orchestration + App Shell | 1 | 2 | 2 |
| [02](02_Project_Lifecycle.md) | Project Lifecycle | 1 | 1 | 5 |
| [03](03_Text_Extraction_Cleanup.md) | Text Extraction + Cleanup | – | 0 | 7 |
| [04](04_Text_Chunking.md) | Text Chunking | – | 2 | 1 |
| [05](05_AI_Runtime.md) | AI Runtime | – | 2 | 7 |
| [06](06_AI_Translation.md) | AI Translation | – | 4 | 2 |
| [07](07_Character_Discovery.md) | Character Discovery | 1 | 4 | 5 |
| [08](08_Speech_Blocks_Core.md) | Speech Blocks — core | 1 | 2 | 4 |
| [09](09_Speech_Blocks_Split_UI.md) | Speech Blocks — split + UI | 1 | 2 | 4 |
| [10](10_TTS_Audio_Blocks.md) | TTS Audio Blocks | – | 4 | 2 |
| [11](11_TTS_Runtime_Assembly_PCM.md) | TTS Runtime + Assembly + PCM | – | 2 | 4 |
| [12](12_Character_Voices.md) | Character Voices | 1 | 1 | 2 |
| [13](13_Narrator_Voice_Profiles.md) | Narrator Voice / Voice Profiles | – | 6 | 3 |
| [14](14_Platform_Settings_UI.md) | Platform / Settings / UI infra | 2 | 3 | 4 |
| [15](15_Cross_Cutting.md) | Cross-cutting (duplication, dead code) | – | 2 | 8 |
| | **Total** | **8** | **41** | **62** |

---

## P0 — do these first

### 1. A live OpenAI API key is in git history — rotate it

`04_Software/AudioMancer/settings.json` is gitignored *today*, but it was
tracked before that. **63 reachable commits still contain a real
`sk-proj-…` key**, and the repo has a push remote
(`ssh://…@192.168.1.15:2222/dpasare/2026_AudioMancer.git`), so the secret
exists outside this machine.

Deleting the file from `HEAD` did not close the exposure. **Revoke and reissue
the key in the OpenAI dashboard** — that is the only action that actually fixes
it, and it is yours to perform. History rewriting is optional cleanup
afterwards; rotation is not.

Details: [14 · PS-1](14_Platform_Settings_UI.md).

### 2. A portable build in a top-level folder cannot start

`config.py:348` evaluates `APP_SOURCE_ROOT.parents[1]` unconditionally at
import time. Unzip a frozen build to `D:\AudioMancer` and `parents` has
length 1 → `IndexError`, raised during `from . import config`, i.e. *before*
`initialize_logging()`. No window, no log, just a traceback. `C:\Program
Files\AudioMancer` survives only by accident of nesting depth. Verified at
runtime.

Since "distributable as a zip archive, unzip and run" is a stated product
principle, this is a shipping blocker. Fix is a guarded index.

Details: [14 · PS-2](14_Platform_Settings_UI.md).

### 3. Two remaining ways to silently corrupt `project.json` (PL-1 and TC-2 resolved)

**Update 2026-08-03:** PL-1 was resolved in `2db1297` during source
replacement, and TC-2 was resolved in `0e8467f` by synchronizing Cleanup's
centralized downstream artifact reset with the corresponding compact-summary
reset. Their original bullets remain as historical review evidence; OC-1 and
CV-1 remain open.

The most common defect class in the codebase, found independently by five
reviewers. `project_workspace_service.sync_manifest_operation_summary` is the
correct helper — it reloads from disk and **only ever promotes** the stage,
with a docstring explaining why demotion strands downstream summaries. Several
call sites bypass it and hand-write `current_stage` instead:

- **[01 · OC-1]** `workflow_controller_service.sync_manifest_operation_from_disk`
  assigns `current_stage` unconditionally from a *pre-operation* snapshot.
  Character Discovery's failure and cancel handlers call it with a hard-coded
  `"translation_ready"` — cancel a re-run on a project at `audio_blocks_ready`
  and the manifest is demoted while the audio artifacts still say completed.
  Next open → `repair_required`.
- **[02 · PL-1 — resolved 2026-08-03]** Source replacement now clears
  Extraction and every downstream artifact and summary through the centralized
  reset path, preserves the safely named new source and unlocked options, and
  returns the project to `source_selected`.
- **[03 · TC-2 — resolved 2026-08-03]** Automatic and manual Cleanup
  publication now share a single transition that deletes downstream artifacts
  through the centralized registry, resets the matching compact summaries,
  retains completed Cleanup at `text_chunking_ready`, and surfaces persistence
  failures before reporting success.
- **[12 · CV-1]** *Merely opening* the Character Voices page marks the stage
  complete: `_sync_manifest_stage` runs before the page state exists, so
  `character_voices_is_ready` is vacuously true over an empty list
  (`all([]) is True`). Reproduced. Does not self-heal.

The two remaining findings are small, local fixes. TC-2 established the shared
Project Lifecycle manifest-reset builder as the reusable pattern for
artifact-and-summary invalidation.

### 4. Resume paths that destroy or duplicate work

Resume is the most bug-dense area in the app. Four independent instances:

- **[08 · SB-1] Critical.** Speech Blocks recomputes `processed_chunk_count` as
  the number of *distinct chunk ids among blocks* and then uses it as the
  *index* of the next source chunk. That equivalence only holds if blocks form
  a contiguous prefix — and the design explicitly allows deleting the last row
  of a chunk. Delete a row in chunk 3 of 10, press Generate: resume is
  accepted, the loop starts at index 9, regenerates chunk 10 as duplicates,
  and chunk 3 stays empty.
- **[07 · CD-1] Critical.** Every discovery checkpoint rebuilds the persisted
  `characters` array from a key hard-coded to `[]` during the discovery phase.
  Cancel a long run, add a character you know about, resume — it is gone after
  the first window.
- **[07 · CD-2] Major.** Resume feeds persisted characters in as
  "already synthesized", so the synthesis loop's `range(len(...), ...)` skips
  the earliest-evidence character — usually the protagonist.
- **[10 · AB-3] Major.** Split-part resume is dead: the checkpoint stores the
  *planned* part count while the reader treats it as *parts on disk*. A
  cancelled 8-part block always restarts from part 1.

### 5. Non-English books hit hard-coded English assumptions

The app ships a Romanian UI and documents Russian/CJK support, but several
paths assume ASCII, Latin script, or space-separated words. All verified at
runtime:

| Finding | Effect |
|---|---|
| **[07 · CD-3/CD-4]** `_normalize_identity` is `re.sub(r"[^a-z0-9]+", "", …)` | `"Иван"` and `"李明"` → `""`. For any non-Latin book the operator can neither add a character **nor save any edit** to a discovered one — the correction path the whole design rests on. Accented Latin both splits and false-merges: `René`→`ren`, `Renée`→`rene`, `Rene`→`rene`. |
| **[13 · NV-1/NV-2]** narrator preview validated by whitespace word count | A correct Japanese sentence counts as 1 word against a 15-word minimum, so **AI narrator generation can never succeed for `ja`/`zh`** — and fails only after the whole paid style-analysis pass. The script-aware `estimate_budget_units` already exists in the same codebase. |
| **[03 · TC-4 — resolved 2026-08-04]** deterministic legacy decoder selection | Russian cp1251 TXT/RTF now decodes exactly without mojibake, and the source ledger records the selected encoding. |
| **[09 · SBU-3]** `„Text.“` German quotes never close the stack | Whole paragraph becomes one over-budget block. The sibling split service already has the correct table. |
| **[09 · SBU-2]** dash-dialogue with no space after the opening dash | Spans fail the contiguity check; the chunk loses **all** AI speaker attribution. Common in Romanian/Spanish/French EPUBs. |

TC-4 is now resolved. The remaining entries are one-line to one-function fixes with disproportionate payoff.

---

## Other themes worth naming

**Resolution update:** CH-1's copied final-window fallback branch was removed
in `d8a08bd`; it is no longer an open example in the bookkeeping-loss theme.
All no-prefix windows now use the same counted and disclosed fallback path.

**Copy-paste branches that dropped their bookkeeping.** `ai_chunking_service.py:280`
has an `elif is_final_window:` arm that is a verbatim copy of the `else:`
fallback minus the `context_window_fallback_count += 1` and the warning
message. Result: for a book that fits one window, *total* AI failure commits
the whole book as one deterministic chunk and reports "AI-assisted chunking
completed." with zero warnings. Deleting the branch is the fix. Same shape in
[06 · TR-5] (byte-identical if/else arms) and [15 · X-1] (a forked model
normalizer that drops a field, making a whole TTS-budget branch unreachable).

**`OSError` escaping Qt slots kills the app.** PL-2 was resolved in commit
`e7d67a5` with local filesystem-error containment and regression coverage. No
`sys.excepthook` is installed anywhere, and under PySide6 ≥6.8 an exception
leaving a slot terminates the process. Two confirmed call sites remain around
real file I/O ([12 · CV-2] and [14 · PS-4]); a non-writable folder, disconnected
USB drive, or file open in another program can still raise an unhandled
filesystem exception there.

**Resolution update 2026-08-05:** AI Translation TR-1 and TR-2 were resolved
in `488973a`: identical editor content is no longer reset, and Start/Resume
flushes pending text before worker dispatch while busy state stops the timer.
TR-3 was resolved in the same commit by threading the page's live enabled
profile through both translation state builders. The historical paragraph
below remains accurate only for Narrator Voice and Character Discovery.

**Historical page-refresh finding.** The translation editor
calls `setPlainText` unconditionally on a 750 ms debounce, so the caret snaps
to offset 0 while you type and the mangled text is auto-persisted — two sibling
pages already guard this with a `!=` check ([06 · TR-1]). The same debounce
races the background worker over the same file ([06 · TR-2]). Separately,
`build_narrator_definition_state` — a *state builder*, run on every refresh —
overwrites every profile's `preview_text` with the localized default whenever
the voice language changes, which happens normally the moment translation
completes ([13 · NV-6]). And three pages fail to thread the operator's AI
profile selection back in, so the combo silently reverts to the default
([06 · TR-3], [13 · NV-5], [07 · CD-10]).

**The audiobook can fail to assemble at the last step.** Found independently
from both sides ([10 · AB-1] and [11 · AS-1]): with ambience *placement* on but
the ambience *audio* checkbox off, a Scene Ambience block is persisted
`generated=True` with an `audio_relative_path` pointing at a WAV that was never
written. Assembly admits the block on the strength of that path and then
`wave.open()`s a missing file — aborting the whole run after all the expensive
generation is done. Also here: a whole-book WAV past ~4 GiB dies mid-write with
a raw `struct.error` (≈6.8 h at 44.1 kHz stereo) leaving a multi-GB `.tmp`
([11 · AS-2]).

**Truncated LLM responses were silently repaired into smaller valid payloads
(AI-2 — resolved 2026-08-03).** Before the resolution, `finish_reason` appeared
nowhere in `src/`; when a response was cut at `max_tokens`, the repair path
could close the brackets, drop the tail, log `parsed_success_after_repair`, and
return success — e.g. 17 of 24 chunks persisted with nothing marking the loss.
The provider boundary now rejects explicit `finish_reason: "length"` before
parsing or repair ([05 · AI-2]).

---

## What is demonstrably healthy

Worth recording, because reviewers chased these specifically and found them
correct:

- **`pcm_codec`** is bit-exact against `audioop` — differentially tested across
  all 16 width pairs, mono/stereo, five rate pairs and a chunked stream.
- **Atomic writes** (mkstemp + fsync + `os.replace`, cleanup on error) with no
  truncation path, in settings and in the speech-blocks document.
- **Path containment** — no traversal escape found in artifact resolution,
  deletion, or snapshotting; symlinks are skipped.
- **Localization** — 977 keys per language, no missing/extra/duplicate keys, no
  placeholder mismatches, no untranslated Romanian leftovers; `translate()`
  cannot `KeyError`.
- **API-key redaction in logs** is genuinely sound: keys live only in headers,
  never in the logged payload, and the recursive redactor covers nested fields.
- **QThread lifecycle**, signal marshalling, progress clamping and reset
  ordering vs `WORKFLOW_OPERATION_ORDER`.
- **Chunking math** — exact coverage, no gaps, overlaps or duplication; no loop
  can stall.
- **Cross-cutting hygiene** — one LLM JSON parser (not five), explicit
  `encoding=` on every file access, zero mutable default arguments, zero
  mutated module-level state.

---

## Suggested order of work

**Update 2026-08-03:** In item 3, PL-1 and TC-2 are complete; the remaining
manifest-stage work is OC-1 and CV-1.

**Resolution update:** CH-1 and CH-3 are complete in `d8a08bd`; suggested
work item 7 applies only to the remaining non-Chunking copy-paste findings.

1. **Rotate the API key.** Independent of everything else.
2. **`config.py:348` guarded index** — one line, unblocks portable builds.
3. **Finish the manifest-stage cluster** (OC-1, CV-1); PL-1 and TC-2 are
   complete through the centralized artifact-and-summary reset helpers.
4. **`_normalize_identity` + the CJK word count** — two one-line fixes that
   restore non-English books.
5. **The resume cluster** (SB-1, CD-1, CD-2, AB-3) — largest effort here, but
   this is where silent data corruption lives.
6. **`except OSError` at the three call sites**, plus a `sys.excepthook`.
7. **Delete the dead copy-paste branches** (CH-1, TR-5) — pure removal, and
   CH-1 currently hides total AI failure behind a success message.
8. Everything else, by severity, from the component reports.

Items 2, 4, 6 and 7 are roughly a day's work combined and remove two Criticals,
several Majors, and the worst silent-failure paths.

---

## Report index

| File | Component |
|---|---|
| [01_Operation_Orchestration_App_Shell.md](01_Operation_Orchestration_App_Shell.md) | Operation runtime, workflow impact, progress dialog, runner controller, app shell, main window, sidebar |
| [02_Project_Lifecycle.md](02_Project_Lifecycle.md) | Workspace, export, snapshot, persistence, import, source ledger, Home |
| [03_Text_Extraction_Cleanup.md](03_Text_Extraction_Cleanup.md) | Extraction service + adapters, cleanup service, analysis, adjudication, renderer, metadata |
| [04_Text_Chunking.md](04_Text_Chunking.md) | Deterministic + AI chunking, chunk document, chunking state |
| [05_AI_Runtime.md](05_AI_Runtime.md) | LLM provider transport, AI backend, budget, token usage, prompt templates, AI settings |
| [06_AI_Translation.md](06_AI_Translation.md) | Translation service, state, page, controller |
| [07_Character_Discovery.md](07_Character_Discovery.md) | Discovery service, state, characters page + controller |
| [08_Speech_Blocks_Core.md](08_Speech_Blocks_Core.md) | Speech-blocks document service, state, report state |
| [09_Speech_Blocks_Split_UI.md](09_Speech_Blocks_Split_UI.md) | Normalization, text split, narrator split, page + controller |
| [10_TTS_Audio_Blocks.md](10_TTS_Audio_Blocks.md) | Audio blocks service, state, artifacts, page + controller |
| [11_TTS_Runtime_Assembly_PCM.md](11_TTS_Runtime_Assembly_PCM.md) | VoiceWeaver runtime, TTS budget, PCM codec, assembly, TTS settings |
| [12_Character_Voices.md](12_Character_Voices.md) | Character-voice assignment, sample import, page + controller |
| [13_Narrator_Voice_Profiles.md](13_Narrator_Voice_Profiles.md) | Narrator definition, profile generation, page + controller |
| [14_Platform_Settings_UI.md](14_Platform_Settings_UI.md) | Config, settings, UI state/theme/scroll, URL, logging, time, settings page |
| [15_Cross_Cutting.md](15_Cross_Cutting.md) | Diverged duplicates, swallowed failures, config drift, dead code |
