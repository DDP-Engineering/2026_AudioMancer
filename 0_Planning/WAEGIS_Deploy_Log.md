<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# WAEGIS Deploy Log — AudioMancer Adoption

Tracks the step-by-step run of the WAEGIS wizard (`waegis adopt`) against this
repository, and the inconsistencies observed while running it, so they can be
fixed upstream in the WAEGIS package
(`D:\TEMP\2026_Agentic_Engineering_Governance_Integrity_System\05_Software\waegis`).

## Context

- Repo already had a legacy `.agentic/` install from an older, unrelated
  "agentic_workflow" tool. Its removal (222 files) was committed separately
  (`Removed the old agentic workflow.`) on branch `feature/add_new_aegis_workflow`
  before starting the wizard, so the adoption commit would not bundle unrelated
  history.
- Wizard invoked without a global install, via:
  ```cmd
  set PYTHONPATH=D:\TEMP\2026_Agentic_Engineering_Governance_Integrity_System\05_Software\waegis\src
  python -m waegis adopt "D:\Temp\2026_AudioMancer"
  ```

## Steps run so far

1. `waegis analyze --repo D:\Temp\2026_AudioMancer` — read-only.
   Result: no manifest, `.agentic` absent, proposals `language: python`,
   `source_roots: 04_Software`, `test_roots: (none)`.
2. `waegis adopt D:\Temp\2026_AudioMancer --dry-run` — plan preview only,
   17 steps listed, no changes made.
3. `waegis adopt D:\Temp\2026_AudioMancer` (real run, interactive):
   - `home.init`, `machine.os`, `machine.disk`, `prereq.python`,
     `prereq.git`, `prereq.git-identity` — all auto-skipped/OK
     (Windows 11, 478.60 GiB free, Python 3.14.6, git 2.55.0,
     identity `Dan Dumitru Pasare <pasaredan1979@gmail.com>`).
   - `repo.validate-existing` — confirmed adoption; reported clean working
     tree on branch `feature/add_new_aegis_workflow`.
   - `repo.prior-install` — `.agentic` absent, routed to fresh adoption
     (correct, since the legacy folder had already been removed and committed).
   - `analyze.repo` — in progress: prompting for `source_roots` /
     `test_roots` confirmation. Repo actually has tests at
     `04_Software/AudioMancer/tests`, so `test_roots` needs to be filled in
     manually rather than accepting the empty default.

   - `analyze.repo` continued: confirmed `source_roots = 04_Software/AudioMancer`,
     `test_roots = 04_Software/AudioMancer/tests`, `language = python`
     (default). Now prompting for `gate_test_cmds` / `gate_lint_cmds`.
     Recommended `gate_test_cmds` value, since this repo's actual `uv`
     project lives at `04_Software/AudioMancer/pyproject.toml` (not at the
     repo root) and gate commands run with `cwd=TARGET` (repo root — see
     inconsistency 3 below):
     ```json
     [["uv", "run", "--project", "04_Software/AudioMancer", "pytest", "-q"]]
     ```

*(To be continued as the run progresses.)*

## Inconsistencies to fix in WAEGIS

1. **[FIXED]** **Confirm-prompt text is not flushed before `readline()` under
   Windows `cmd.exe`.**
   `ConsoleAsker.confirm` (`src/waegis/io/prompts.py`, around line 292) writes
   the prompt with `self._write(f"{prompt} {suffix}: ")` and immediately calls
   `self._stdin.readline()`. Under `cmd.exe` (unlike PowerShell or a real TTY)
   the prompt text visibly appears only *after* the operator types their
   answer and presses Enter, not before. Observed twice in this run:
   - The top-level `Apply this plan? [Y/n]:` gate.
   - The `Adopt AEGIS into this existing repository? [Y/n]:` prompt inside
     `repo.validate-existing`.
   This made the wizard look hung/frozen in `cmd.exe` — the operator had no
   visible cue to type anything.
   Fixed in `src/waegis/io/prompts.py`, `ConsoleAsker._write`: now flushes
   the injected stdout stream (if it exposes `.flush`) right after every
   write, so the prompt always renders before the following blocking
   `readline()`. Verified with `uv run --group dev python -m pytest -q
   tests -k prompts` (13 passed).

2. **`test_roots` auto-detection misses an existing, conventionally named
   `tests/` folder.**
   `waegis analyze --repo D:\Temp\2026_AudioMancer` reported `test_roots:
   (none)` even though `04_Software/AudioMancer/tests/` exists with real
   test files (`.pytest_cache` present alongside it, so tests have actually
   been run there before). The repo-analysis heuristic
   (`src/waegis/repo/analyze.py`) should be checked for why a `tests/`
   directory one level under a detected `source_root` is not picked up —
   worth confirming whether it only scans the repo root rather than
   recursing into `source_roots` candidates.

3. **`gate_test_cmds`/`gate_lint_cmds` are always executed with `cwd=TARGET`
   (the repo root), never `cwd=source_root`.**
   `src/waegis/commands/new.py` (`_act_gates`, ~line 1499) calls
   `runner.run(tuple(command), timeout=GATE_TIMEOUT_SECONDS, cwd=target)`
   where `target` is always the adoption/new-project root. For a repo like
   this one, where `source_roots` (repo-root-relative, e.g.
   `04_Software/AudioMancer`) does not coincide with the actual Python
   project root (`04_Software/AudioMancer/pyproject.toml`), a naive
   `["uv", "run", "pytest", "-q"]` — matching the field's own example —
   fails, because `uv` can't find a project at the repo root. The operator
   has to know to add `--project <source_root>` (or an equivalent `cd`)
   themselves; the wizard neither detects this mismatch nor warns about it,
   even though `analyze.repo` already knows `source_roots`.

4. **[FIXED — same fix as #1]** **Buffering delay affects `ask_field`
   prompts too, not just `confirm`.**
   Same root cause as inconsistency 1, but observed across the whole
   `analyze.repo` field sequence: for each field, the *description* text
   prints, then the operator's already-typed answer appears interleaved
   with the *previous* field's prompt text and the *next* field's
   description, all flushed together only once enough output has
   accumulated. E.g. the `language (e.g. python; default: python):` prompt
   and the following `gate_test_cmds` description both appeared only after
   the operator had already blindly pressed Enter to accept the `python`
   default — they could not actually read the prompt before answering it.
   Same fix as inconsistency 1 (flush after every prompt write) should
   resolve both.

5. **[IMPROVED]** **Conflict-resolution prompts (`keep-local`/`take-payload`/
   `write-new`) required typing the exact word.**
   Encountered live during `deploy.adoption-copy`'s first conflict
   (`.gitignore` already existed and differed from the payload). Typing a
   full literal choice by hand on every conflicted file is slower and more
   error-prone than picking a number, especially across many conflicts.
   Added a `choices` field to `FieldSpec`
   (`src/waegis/io/prompts.py`) — when set, `ConsoleAsker.ask_field` prints
   a numbered menu (marking the default) and accepts either the number or
   the literal value; validation and defaulting are unchanged.
   Wired to all three conflict-decision prompts that previously required
   free-text (`keep-local`/`take-payload`/`write-new`):
   `src/waegis/commands/adopt.py` (`_prompt_conflict`),
   `src/waegis/commands/repair.py`, `src/waegis/commands/upgrade.py`.
   `ScriptedAsker`/`--answers` files are unaffected — they always take the
   literal value, no numbers involved. Verified with the full offline suite
   (`uv run --group dev python -m pytest -q tests -m "not integration"` —
   403 passed, 1 skipped) plus a manual render check showing:
   ```
   .gitignore already exists and differs from the payload. ...
     1) keep-local (default)
     2) take-payload
     3) write-new
   conflict:.gitignore (e.g. keep-local; default: keep-local):
   ```

## Third run — `deploy.adoption-copy` through `deploy.gates`

- `deploy.adoption-copy`: 2 conflicts, resolved via the new numbered-menu
  prompt (inconsistency 5):
  - `.gitignore` → `write-new` (payload version written as `.gitignore.new`;
    still need to manually merge in `node_modules/`, `.vitest/`,
    `.opencode-cache/` from it, then delete the sidecar).
  - `CHANGELOG.md` → `keep-local` (real history kept; payload version is
    just a template).
  - 115 payload files copied total.
- `deploy.workflow-toml`: generated `.agentic/workflow.toml` from the
  confirmed `analyze.repo` answers.
- `deploy.gates`: ran the configured `test` gate
  (`uv run --project 04_Software/AudioMancer pytest -q`), confirming
  inconsistency 3's fix works — `uv` correctly resolved the nested project.
  Result: **917 passed, 5 failed, 1 skipped, 586.35s**. The 5 failures are
  **pre-existing AudioMancer test debt, unrelated to the AEGIS adoption**:
  ```
  FAILED test_atomic_io_contracts.py::test_manual_cleaned_text_edit_uses_atomic_writers
  FAILED test_config_hygiene.py::test_committed_settings_file_contains_only_blank_secret_fields
  FAILED test_config_hygiene.py::test_committed_settings_file_does_not_match_common_secret_tokens
  FAILED test_main_window_project_flow.py::test_main_window_initializes_step_state_only_when_page_is_opened
  FAILED test_traceability.py::test_services_and_controllers_have_test_coverage
  ```
  Notably `test_traceability.py` is AudioMancer's own pre-existing
  requirement-coverage check (independent of AEGIS) and already flags ~20
  services/controllers with `REQ-COVERAGE-MISSING`. Decision: accept the
  failing gate and let the adoption proceed; track fixing these 5 tests as
  a separate follow-up, not part of the AEGIS deploy.

## Fourth run — declining `repo.adoption-commit` and the resulting fix

- After accepting the failing gate, the run reached `repo.adoption-commit`
  (`Proceed with 'Commit the adoption on a branch'? [Y/n]`) and the operator
  answered `n`, intending to commit manually themselves later.
- **[FIXED — new inconsistency]** Declining any `ASSISTED` step's generic
  "Proceed with '<title>'?" gate marks it `DECLINED`, and `runner.run()`
  treats the first non-green step (`FAILED` or `DECLINED`) as a hard stop —
  the whole run halted one step before the end
  (`stopped at step: repo.adoption-commit (declined)`), even though nothing
  about declining a commit should block the already-fully-deployed payload
  from reaching the final `handoff.adoption` step (which is read-only).
  Two options existed: (a) commit manually with the exact branch/message the
  step expects (`git checkout -b chore/aegis-adoption && git add -A && git
  commit -m "Adopt AEGIS via WAEGIS 0.1.0"`), so a re-run's `detect` sees it
  as already done and skips it — no code change needed, works today; or
  (b) make the step genuinely optional. Went with (b) since operators should
  not be forced through git-porcelain-matching gymnastics just to end a run
  cleanly on their own terms.
  Changed in `src/waegis/commands/adopt.py`:
  - `repo.adoption-commit`'s `automation` changed from `Automation.ASSISTED`
    to `Automation.AUTO`, so the generic run-halting gate no longer applies
    to it.
  - `_act_adoption_commit` now asks its own confirmation first
    (`"Commit the adoption now on a new branch? (choose 'n' to commit it
    yourself later)"`); declining sets a new cross-step flag
    (`SHARED_ADOPTION_COMMIT_SKIPPED` in `ctx.shared`) and returns without
    committing, instead of raising.
  - `_verify_adoption_commit` treats that flag as a valid verified outcome
    (returns `True`) instead of failing the git-state re-check.
  - The plan-preview `change_summary` now says "(optional; asks first,
    skipping leaves it for you to commit yourself)".
  Net effect: declining the commit now lets the run finish cleanly through
  `handoff.adoption` instead of stopping one step short. Verified with the
  full offline suite (403 passed, 1 skipped) and a `--dry-run` preview
  showing the step's automation column as `auto`.

## Fifth fix — `deploy.gates` had the same run-halting decline problem

- Follow-up question: if gate commands are slow (this run's `pytest` gate
  took ~10 minutes), what happens on declining to run them? Answer at the
  time: declining the *generic* `ASSISTED` "Proceed with 'Try the quality
  gates once'?" gate halted the whole run (same class of bug as
  inconsistency 6 below / the adoption-commit fix), whereas declining the
  more specific in-`act` "Run the N '<gate>' gate command(s) once now?"
  prompt correctly deferred just that gate and let the run continue. So
  `y` then `n` worked as a workaround, but the outer gate was still a trap.
- **[FIXED — same class as the adoption-commit fix]** Applied the identical
  pattern to `deploy.gates` in `src/waegis/commands/new.py` (shared by both
  `new` and `adopt` — it's the actual `GATES_STEP` instance imported into
  `adopt.py`):
  - `automation` changed from `Automation.ASSISTED` to `Automation.AUTO`.
  - `_act_gates` now asks its own top-level `"Proceed with 'Try the quality
    gates once'?"` confirmation first; declining it defers every configured
    gate command in one shot (and marks any empty gate `accepted-empty`)
    with no further prompts, instead of raising/halting.
  - `_verify_gates` was already outcome-based and needed no change — a
    fully-deferred outcome set was already in its `allowed` set.
  - Updated `tests/test_commands_new_catalog.py`'s plan-automation-kind
    expectation and the two `tests/test_commands_new_steps.py` gate tests
    whose scripted confirm lists assumed the old ordering (now one extra
    leading confirm), plus added a new test asserting the top-level decline
    defers everything with a single `False` and no gate command execution.
  Verified with the full offline suite: 404 passed, 1 skipped (was 403
  before the new test).

## Sixth/seventh fixes — handoff text lied about the commit, and the recap looked like a duplicate

Run completed end to end (declined both `deploy.gates`'s top-level confirm
and `repo.adoption-commit`), surfacing two more issues in the final output.

6. **[FIXED]** `handoff.adoption`'s notes always said `"Changes are
   committed on branch 'chore/aegis-adoption'."` and `"...WAEGIS's job ends
   here with a verified, committed adoption branch."` — even when the
   operator had just declined the commit (inconsistency 6's fix). Stale
   text left over from before the optional-commit feature existed.
   Fixed in `src/waegis/commands/adopt.py`, `_act_handoff_adoption`: both
   notes now branch on `ctx.shared.get(SHARED_ADOPTION_COMMIT_SKIPPED)`,
   saying `"Changes are on disk but NOT committed - commit them yourself
   when ready."` / `"...a verified adoption, left uncommitted for you to
   commit yourself."` when skipped.
7. **[CLARIFIED, not a bug]** The full handoff message block appeared to
   print twice: once live (bullet-prefixed, step by step) during the run,
   and once again unprefixed at the very end. This is `_render_human_outcome`
   in `src/waegis/commands/new.py` by design — a final, copy-pasteable
   recap without the live-log bullet noise — but with no visual marker it
   read as an accidental duplicate. Added a
   `=== Summary (recap of the handoff notes above) ===` header before the
   recap so the boundary is explicit. (Function is shared by `new` and
   `adopt`, so the header stays generic rather than adoption-specific.)

Verified with the full offline suite (404 passed, 1 skipped, unchanged) plus
a direct call to `_act_handoff_adoption` with the skip flag set, confirming
the corrected wording end to end.

## Eighth improvement — console output formatting/layout

Requested after seeing the full run's log as one dense, hard-to-scan wall of
text (no vertical alignment, no visual grouping). Changed in
`src/waegis/io/console.py` and `src/waegis/commands/new.py`:

- **Marker alignment**: `[..]`/`[OK]`/`[SKIP]`/`[FAIL]` (and the glyph
  equivalents, when opted into) are now left-padded to the widest marker in
  their set, so every step title starts in the same column regardless of
  status. New `_ASCII_MARKER_WIDTH`/`_GLYPH_MARKER_WIDTH` constants.
- **Phase section banners**: `LiveStatusRenderer` now tracks the active
  `Phase` and prints a centered `=== P0-machine ===`-style banner whenever
  the run enters a new phase, so the log reads as grouped sections
  (machine checks, prereqs, repo, deploy, handoff) instead of one
  undifferentiated stream of lines.
- **Note indentation**: step notes/messages (the `- ...` bullets under each
  step) are now indented to align under the title text (7 spaces, matching
  the padded-marker width) instead of a flat 4-space indent that didn't
  line up with anything.
- **Inter-step spacing**: `_ConsoleRunSink` (the real CLI event sink) now
  writes a blank line after each finished step's notes, so steps read as
  distinct blocks instead of a dense wall of text. `LiveStatusRenderer`'s
  own banner no longer adds a second leading blank line on top of that (it
  did briefly during development; removed once the double-gap was spotted
  in a manual render check).
- **Plan preview**: trailing blank line added after "N step(s) planned."
  so there is breathing room before the "Apply this plan?" approval prompt.

Updated 3 existing tests whose exact-string assertions assumed the old
unpadded/unbannered format
(`tests/test_io_console.py::test_live_status_renderer_uses_ascii_markers_by_default`,
`::test_forced_glyph_flag_switches_markers_not_data`,
`tests/test_engine_end_to_end.py::test_toy_catalog_runs_to_completion_interactively_via_console_renderer`).
Verified with the full offline suite (404 passed, 1 skipped, unchanged
count), `ruff check` (clean), and a manual render simulating a
multi-phase step sequence through the real `_ConsoleRunSink`.

## Ninth pass — Code_Style.md compliance and versioning discipline

Requested: bring every file touched today in line with
`01_Documentation/Code_Style.md`'s Doxygen-like documentation style, and
apply its `@version` rule precisely: bump a **callable's** `@version` on
every change to that callable; bump a **file's** `@version` only when the
file's API surface changes (function/field added or removed, signature or
contract changed) — never bulk-synced to the release version.

Updated `@version`/`@date`/`@details` across every file/function actually
modified today:

- `src/waegis/io/prompts.py`: file 0.1.0 -> 0.2.0 (new `FieldSpec.choices`
  field); `FieldSpec` class, `ConsoleAsker._write`, `ConsoleAsker.ask_field`
  each 0.1.0 -> 0.2.0.
- `src/waegis/io/console.py`: file 0.1.0 -> 0.2.0 (marker padding + phase
  banners); `render_plan_preview`, `LiveStatusRenderer` (class docstring,
  `__init__`, `_marker`, `emit`) each 0.1.0 -> 0.2.0; `_phase_banner` is a
  new method, kept at 0.1.0 with today's date (docstring corrected — it had
  described a leading-blank-line behavior that was removed once a manual
  render check showed a doubled gap when combined with `_ConsoleRunSink`).
- `src/waegis/commands/adopt.py`: file 0.1.0 -> 0.2.0 (`repo.adoption-commit`
  automation contract change); `_prompt_conflict`, `_act_adoption_commit`,
  `_verify_adoption_commit`, `_act_handoff_adoption` each 0.1.0 -> 0.2.0.
- `src/waegis/commands/new.py`: file 0.3.0 -> 0.4.0 (`deploy.gates`
  automation contract change, shared with `adopt.py` via `GATES_STEP`);
  `_act_gates` 0.1.0 -> 0.2.0; `_ConsoleRunSink` (class + `emit`) 0.1.0 ->
  0.2.0; `_render_human_outcome` 0.2.0 -> 0.3.0.
- `src/waegis/commands/repair.py`, `src/waegis/commands/upgrade.py`: file
  version left unchanged (no function added/removed/resignatured, just an
  existing `FieldSpec` gaining `choices=...`); `run_repair` 0.1.0 -> 0.1.1,
  the `upgrade.py` interactive-conflict `hook` closure 0.1.0 -> 0.1.1.
- Four touched test files: bumped both file- and function-level versions
  the same way (test files follow the same style-doc rule).

Verified with the full offline suite (404 passed, 1 skipped, unchanged) and
`ruff check src tests` (clean). A scripted audit of every other file in
`src/waegis` (42 files) and `tests/` (37 files) confirmed the required
prologue elements (shebang, encoding line, license banner, `@file`/
`@brief`/`@author`/`@version`) were already present everywhere else — no
further changes needed outside what was touched today.

## Tenth pass — architecture review + `prereq.node` implementation

A senior-level, read-only architecture review of the WAEGIS/AEGIS
implementation was requested, focused on (1) Windows/Ubuntu portability and
(2) multi-language project support (C/C++/embedded/Java, not just Python).
Full findings not reproduced here; the one item acted on immediately:

**Implemented recommendation 1**: `prereq.node`, a new warn-not-block probe
step (mirrors `machine.os`, not the blocking `prereq.python`/`prereq.git`
pattern) — every AEGIS hook is dispatched through Node
(`node .agentic/tools/run_hook.mjs ...`, per `.claude/settings.json` /
`.codex/hooks.json`), but nothing ever checked for it before, so a machine
without Node silently had every hook fail with no warning at setup time.

- `src/waegis/probes/tools.py`: new `probe_node()` (+ `_NODE_VERSION_RE`, a
  `"node"` entry in `_install_guidance`'s table). Missing/unparseable Node is
  `"warn"`, never `"fail"` — no minimum version enforced, presence only.
- `src/waegis/commands/new.py`: new step `prereq.node` in `P1_PREREQ`,
  between `prereq.git` and `prereq.git-identity`; inserted into both
  `NEW_STEP_IDS` and `_COMMON_PREFIX_IDS` (so it flows into Wizard E
  automatically via the shared `COMMON_PREFIX_STEPS`), `AUTO` automation,
  `verify=lambda ctx: True` (report-only, exactly like `machine.os`).
- `src/waegis/commands/adopt.py`: `ADOPT_STEP_IDS` updated to match (no new
  code needed — the step object itself is reused).
- Tests: `tests/test_probes_tools.py` gained a node-probe section (ok/warn
  variants); `tests/test_commands_new_catalog.py`'s step-count (17 -> 18) and
  `_EXPECTED_AUTOMATION` dict updated.
- Verified: full offline suite 408 passed (was 404), `ruff check` clean, a
  `--dry-run` preview on both `waegis new` and `waegis adopt` showing the
  step in the right slot, and a live `probe_node()` call against this
  machine's real Node install (`ok node 24.18.0`).

Remaining review findings (not yet acted on): missing execute bit on
`run.sh`/`install.sh` when copied to Ubuntu; case-insensitive write-zone
path matching on a case-sensitive filesystem; `prereq.python`/`prereq.node`
being WAEGIS-tooling requirements that every target project inherits
regardless of its own language; no per-language codestyle-audit skill beyond
Python.

## Eleventh pass — architecture review recommendations 2-5

**Recommendation 2 (execute bit on run.sh/install.sh)**:
- Fixed at the source: `git update-index --chmod=+x` on
  `05_Software/aegis/template/.agentic/tools/{run,install}.sh` (mode
  100644 -> 100755), so any Linux checkout/clone of this repo now
  correctly propagates the bit.
- Added a defensive backstop independent of git mode propagation:
  `ensure_executable()` (new public function,
  `src/waegis/payload/copier.py` 0.2.0 -> 0.3.0) grants POSIX
  owner/group/other execute bits on every copied `.sh` file, no-op on
  Windows. Wired into all three payload-writing code paths:
  `copier.copy_payload`, `commands/repair.py::run_repair`,
  `commands/upgrade.py::_copy_file`.
- Tests: `tests/test_payload_copier.py` gained a dedicated section
  (mocked-chmod unit tests + one real-filesystem proof skipped on Windows).
  waegis suite: 411 passed (was 408), 2 skipped (was 1).

**Recommendation 3 (case-insensitive write-zone matching on Linux)**:
- `aegis.paths.matches_pattern` and its standalone duplicate
  `guard_write_zone.matches` now case-fold only when `os.name == "nt"`,
  matching each OS's real filesystem semantics.
- Deeper fix needed mid-way: `fnmatch.fnmatch()` does its own OS-tied
  `os.path.normcase` internally, which silently reintroduced
  Windows-only case-insensitivity regardless of the new `os.name` check
  (caught by the new tests failing on this Windows dev machine when
  simulating "posix" via monkeypatch). Switched both functions to
  `fnmatch.fnmatchcase()`, which never normalizes case on its own.
- Tests: `aegis/tests/test_paths.py` and `aegis/tests/test_hooks.py` gained
  Windows/non-Windows case-sensitivity tests. `aegis` suite: 144 passed
  (full suite, separate from the `waegis` one).

**Recommendations 4 & 5 (documentation)**: both landed in
`05_Software/aegis/template/.agentic/documents/How_To_Start_A_New_Project.md`:
- New explicit callout: Python and Node are AEGIS/WAEGIS **tooling**
  requirements, independent of the target project's own language (C,
  C++, embedded, Java, ...) — a machine that can already build the
  project may still need both installed just to run AEGIS's own workflow
  tool and hooks.
- Node.js added to the prerequisites table, quick checklist, and a new
  troubleshooting row (hook errors -> check Node).
- opencode and Qwen Code adapters (`.opencode/`, `.qwen/`) — fully shipped
  and already covered by `aegis/tests/test_opencode_adapter.py` /
  `test_qwen_adapter.py` — now named alongside Codex/Claude Code/Pi in the
  intro paragraph, the architecture diagram, the post-copy file listing,
  Step 5's adapter list, Step 6, and the quick checklist, instead of being
  shipped but undocumented.

All four verified together: `aegis` suite 144 passed, `waegis` suite 411
passed/2 skipped, `ruff check` clean on both packages.

## Restart note (second run)

The in-progress `waegis adopt` run reached `deploy.adoption-copy` and hit its
first conflict (`.gitignore`) before inconsistency 5 was fixed. That run was
aborted (still pre-file-write for every step except the payload copy itself,
which had not started writing yet) so the wizard could be re-run against the
fixed code and produce the numbered-menu prompts end to end.

*(Add further findings below as the remaining steps — `deploy.adoption-copy`,
`deploy.workflow-toml`, `deploy.gates`, `verify.*`, `repo.adoption-commit`,
`handoff.adoption` — are run.)*
