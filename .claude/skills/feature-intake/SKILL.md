---
name: feature-intake
description: Classify an incoming AudioMancer change, map its requirement and test impact before coding, and drive the requirements-first feature lifecycle. Use at the start of any new feature, feature update, or bug fix to decide which requirements and tests must be added or updated.
---

# Feature Intake

Run this workflow before writing implementation code for any new feature,
feature change, or bug fix.

## 1. Classify the change

Pick exactly one class:

- **new-no-impact** - new feature that does not change existing files or
  contracts. Outcome: new requirements, new tests only.
- **new-with-impact** - new feature that changes existing files or contracts.
  Outcome: new requirements, updated impacted requirements, new tests, updated
  impacted tests.
- **correction** - bug fix or feature correction. Outcome: update the existing
  requirements and tests; add a new requirement or test only when the fix
  reveals an uncovered contract.

## 2. Map the impact

Identify the files the change will touch. Then run:

```powershell
python 02_Tools/audits/req_impact.py <changed_or_planned_files>
```

Omit file arguments to analyze the current Git working set. Add `--json` for a
machine-readable payload. The report lists, per file:

- impacted requirement IDs
- the linked tests that guard them
- `uncovered` flags for service or controller modules with no requirement

Treat every `uncovered` service or `ui/controllers` module as a missing
requirement to author in step 3.

## 3. Produce a Change Plan

Before coding, write a short plan, for example:

```
Change class: new-with-impact
New requirements:     REQ-AUDIO-FUNC-039
Updated requirements: REQ-AUDIO-FUNC-007
New tests:            tests/test_<feature>_service.py (unit),
                      tests/integration/test_<feature>_pipeline.py
Updated tests:        tests/test_audio_assembly_service.py
System test impact:   extend tests/system pipeline smoke if a stage contract changed
```

## 4. Requirements first

Apply the `requirements-traceability` workflow to add or update register rows
under `0_Planning/Requirements/`:

- New rows start with status `Planned` until a real linked test exists.
- For `new-with-impact` and `correction`, update the `Related Components`,
  `Linked Tests`, and `Last Updated` of each impacted row.
- Preserve `Created On`. Only set it for a newly introduced requirement ID.

## 5. Tests across levels

Author or update tests at the right level and cite requirement IDs in each test
docstring:

- **unit** (`service` / `ui` markers) - one service or controller in isolation.
- **integration** (`integration` marker, `tests/integration/`) - cross-service
  hand-off, such as one stage output being valid input to the next stage.
- **system** (`system` marker, `tests/system/`) - the deterministic offline
  pipeline from import through assembly.

Flip a requirement from `Planned` to `Active` once its linked test exists and
passes.

## 6. Implement, then validate

After implementation, run the focused checks and the gates:

```powershell
uv run python -m py_compile <changed_file.py>
uv run ruff check <changed_python_files> --fix
uv run ruff format <changed_python_files>
uv run pytest <targeted_tests>
python 02_Tools/audits/audit_traceability.py
python 02_Tools/audits/audit_documentation.py --changed-only
```

## 7. Report

State the change class, the requirement IDs added or updated, the tests added or
updated, and any requirement still left `Planned` without coverage.
