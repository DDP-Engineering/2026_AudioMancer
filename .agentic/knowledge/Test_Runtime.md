<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Test Runtime

## Purpose

The test runtime defines repository-wide pytest dependencies, collection tiers,
local worker execution, and safeguards for AudioMancer verification. It does
not define production operation timeouts or application runtime behavior.

## Public interface

Tests run from `05_Software/AudioMancer` through
`uv run --extra dev python -m pytest`. The default pytest configuration
excludes performance tests and limits each collected test, including fixture
setup and teardown, to 120 seconds.
Service tests may explicitly use local xdist workers with `-n`, while default
and UI-tier execution remains serial.

## Key behaviors

- `REQ-TEST-c40e9791` - an individual pytest test is terminated after 120
  seconds using the Windows-safe thread timeout method.
- `REQ-TEST-d5e21918` - local parallel service-test execution is available but
  is not enabled by repository defaults.

## Files

- `05_Software/AudioMancer/pyproject.toml` - declares pytest development
  dependencies and repository-wide pytest options.
- `05_Software/AudioMancer/uv.lock` - locks the timeout plugin and its resolved
  package metadata.
- `05_Software/AudioMancer/tests/conftest.py` - assigns service and UI tiers
  during collection.
- `05_Software/AudioMancer/tests/test_pytest_runtime_configuration.py` - checks
  that timeout and opt-in local worker safeguards are active.
- `HowToTest.md` - documents serial and parallel test commands and their safety
  boundary.
