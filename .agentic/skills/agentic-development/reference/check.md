<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->

# Stage: Check

Run `stage prepare`, then `stage add` for every additional focused deterministic
check. AEGIS generates check IDs. Cite exact requirement IDs and record commands
that assert observable contracts and state transitions.

Cover applicable success, rejection, error, boundary, stale-state cleanup,
rollback, concurrency, and idempotency behavior. Identify production/mock/
sandbox, feature-flag, role, platform, and persistence-adapter variants; add
parity checks where variants promise the same contract.

Apply the whole collection atomically. For a fix, record reproducing red evidence
before closing:

- External mode: `check prepare`, run the commands, edit `evidence.toml`, then
  `check record`.
- Managed mode: `check run [<check-id>...]`.

Stop before source implementation.
