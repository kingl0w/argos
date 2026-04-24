# ARG-001 — argos-status.sh exits non-zero when ADRs are present

**Status:** Queued
**Created:** 2026-04-24
**Priority:** P2

## Intent

`argos/scripts/argos-status.sh` exits with code 1 whenever one or more Proposed ADRs exist in `argos/specs/decisions/`, even though its output is correct. This makes the script unreliable in CI contexts and in any shell pipeline that checks `$?`. After this ticket, the script always exits 0 on success, matching the contract of every other Argos helper script.

## Context

The bug was surfaced during the v0.5 consolidation smoke test (commit `330ec3f`). The final line of the script is:

```bash
[ "$found" -eq 0 ] && echo "(none)"
```

When `found=1` (i.e. at least one Proposed ADR was listed), the test returns false. Because the script runs under `set -euo pipefail` and this is the last statement, the false exit status propagates as the script's exit code. The bug predates the v0.5 refactor — `git show HEAD~1:scripts/argos-status.sh` (before the move) contains the identical line. It was caught on the fresh-project smoke test in `/tmp/argos-v5-test/` and explicitly deferred here rather than fixing inline.

Pre-existing behavior references: `argos/scripts/argos-status.sh:56` (final line after v0.5 move).

## Non-goals

- No changes to the script's stdout. The human-facing report format is fine as-is.
- No broader hardening pass on the other argos/scripts/*.sh helpers in this ticket — file a separate ticket if a similar audit surfaces more.
- No rewrite into a different language or structure. The fix is one statement.

## Acceptance criteria (draft)

- [ ] `bash argos/scripts/argos-status.sh; echo $?` prints `0` when one or more Proposed ADRs exist in `argos/specs/decisions/`.
- [ ] `bash argos/scripts/argos-status.sh; echo $?` prints `0` when no Proposed ADRs exist (regression guard — already working).
- [ ] When no Proposed ADRs exist, the script still prints `(none)` under the `=== Proposed ADRs ===` header (stdout behavior preserved).
- [ ] When Proposed ADRs exist, their list is still printed under `=== Proposed ADRs ===` (stdout behavior preserved).
