# ARG1-032 — Pre-commit hook enforces "verifier-only writes STATE.md"

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P1
**Epic:** 4 (Severity-tiered verifier)

## Intent

Ship a pre-commit hook (`argos/scripts/hooks/pre-commit-state-write.sh`) that rejects any commit modifying `argos/specs/STATE.md` unless the modification consists entirely of new `<!-- argos:entry ... author=verifier ... -->` blocks (or new blocks under the cycle-close `--close-cycle` operation, identified by an env var). Registered by `argos init` (ARG1-002) into the local `.git/hooks/pre-commit` chain. Enforces the ARCHITECTURE.md §Invariants rule that the verifier is the sole writer.

## Context

ARCHITECTURE.md §Invariants names "verifier is the sole writer of STATE.md" and flags the enforcement question as TODO. This ticket answers that TODO by stamping the author in the block frontmatter and validating it at the hook layer. The hook is local (per-clone); CI re-runs the same validation on the PR.

## Non-goals

- No CI-side validation (separate, follow-up — same script can be reused).
- No author-identity verification (we trust the block's `author=` attribute; agent allowed-tools are the actual security boundary).
- No retroactive validation of historical commits.

## Acceptance criteria

- [ ] After `argos init`, `.git/hooks/pre-commit` contains a line invoking `argos/scripts/hooks/pre-commit-state-write.sh`.
- [ ] A commit that adds only `<!-- argos:entry ... author=verifier ... -->` blocks to STATE.md passes: `git commit -m test` exits 0 (in a synthetic test repo).
- [ ] A commit that modifies STATE.md content outside any `<!-- argos:entry -->` block fails: `git commit -m test; echo $?` prints non-zero; stderr contains `STATE.md modified outside append-block`.
- [ ] A commit that adds a block with `author=coder` fails: stderr contains `STATE.md author must be verifier`.
- [ ] A commit with `ARGOS_CYCLE_CLOSE=1` env set bypasses the hook (cycle-close operation): `ARGOS_CYCLE_CLOSE=1 git commit -m close` exits 0 even when STATE.md has block deletions.
- [ ] The hook exits 0 when the commit does not touch STATE.md (no false positives): `git commit -m unrelated` on an unrelated file change exits 0.

## Depends on

- ARG1-051 (state-append helper — defines the block format the hook validates)

## Touches

- `argos/scripts/hooks/pre-commit-state-write.sh` (new)
- `argos/scripts/hooks/tests/test_pre_commit.sh` (or equivalent — new)

## Parallelizable with

- ARG1-003 (status)
- ARG1-004 (sync)
- ARG1-005 (attend)
- ARG1-013 (auto-fix retry)
- ARG1-021 (independence detection)
- ARG1-022 (parallel dispatch)
- ARG1-023 (worktree merge)
- ARG1-041 (escalation writer)
- ARG1-052 (merge driver — different script)
- ARG1-054 (cycle close)

## Plan

### Files touched

| Path | Status | Purpose |
|------|--------|---------|
| `argos/scripts/hooks/pre-commit-state-write.sh` | new | The hook itself: validates staged STATE.md diffs against the verifier-only invariant, bypassing on `ARGOS_CYCLE_CLOSE=1`. POSIX shell + awk, matching `state-merge-driver.sh` precedent. |
| `argos/scripts/install-hooks.sh` | new | Idempotent installer that wires the hook into `.git/hooks/pre-commit`. Parallel to `install-merge-driver.sh`. Picked up by `argos init` (ARG1-002) when that lands; runnable manually after a fresh clone. |
| `argos/scripts/argos-init.sh` | edit | Append a call to `install-hooks.sh` at end of init, mirroring how `argos init` (ARG1-002) will register installers. |
| `argos/scripts/hooks/tests/test_pre_commit.sh` | new | POSIX-shell AC harness, mirroring `argos/scripts/tests/test_merge_driver.sh` style. Six AC scenarios + a `state-append` interop check. |
| `argos/specs/v1.0/tickets/ARG1-032-pre-commit-verifier-only-state.md` | edit | This Plan + Verification appended by the verifier. |

```
files_touched:
  - argos/scripts/hooks/pre-commit-state-write.sh
  - argos/scripts/install-hooks.sh
  - argos/scripts/argos-init.sh
  - argos/scripts/hooks/tests/test_pre_commit.sh
  - argos/specs/v1.0/tickets/ARG1-032-pre-commit-verifier-only-state.md
```

### Changes per file

**`argos/scripts/hooks/pre-commit-state-write.sh`**
- POSIX `#!/bin/sh` + `set -eu` matching `state-merge-driver.sh`.
- Bypass: if `ARGOS_CYCLE_CLOSE=1`, exit 0 immediately.
- For each STATE.md path under enforcement (`argos/specs/STATE.md` and the v1.0 mirror `argos/specs/v1.0/STATE.md`):
  - Skip if path is not in the staged set (`git diff --cached --name-only`).
  - File deletion → `STATE.md modified outside append-block (...): file deletion not permitted` → exit 1.
  - Compute `git diff --cached --no-color -U0 -- <path>`; pipe to a single-pass awk validator.
  - Validator state machine over the `+`/`-` lines:
    - any `-` line → `STATE.md modified outside append-block (...)` → exit 1.
    - `+` blank line → no-op (allowed anywhere; state-append inserts blanks around blocks).
    - `+` line outside an open block:
      - well-formed open tag (`<!-- argos:entry ... -->`) → extract `author=...`; if `!= verifier` → `STATE.md author must be verifier (...)` exit 2; else enter block.
      - anything else → `STATE.md modified outside append-block (...)` exit 1.
    - `+` line inside an open block: accept; close-tag exits the block.
  - Trailing unclosed block at EOF → `STATE.md modified outside append-block (...): unclosed argos:entry block` → exit 1.

**`argos/scripts/install-hooks.sh`**
- POSIX `#!/bin/sh` + `set -eu`. Idempotent.
- Resolve repo root via `cd "$(dirname "$0")/../.." && pwd`.
- Verify `argos/scripts/hooks/pre-commit-state-write.sh` exists; chmod +x if needed.
- Locate `.git/hooks/pre-commit` (honoring `core.hooksPath` if set).
- If no pre-commit hook exists → write a minimal stub that runs the state-write hook.
- If a pre-commit hook exists and already invokes `pre-commit-state-write.sh` → exit 0 silently (idempotent).
- Otherwise → append a sentinel-tagged block (`# >>> argos pre-commit-state-write` … `# <<<`) that invokes the hook. The block re-invokes `$0`'s args so chained hooks survive future re-installs.

**`argos/scripts/argos-init.sh`**
- After the existing template-render step, invoke `argos/scripts/install-hooks.sh` (best-effort: print a warning if not in a git repo, but don't fail init).

**`argos/scripts/hooks/tests/test_pre_commit.sh`**
- Mirror of `test_merge_driver.sh` style (POSIX, tmp-sandbox per test, pass/fail counters).
- Test 1 (AC#1): runs `install-hooks.sh` in a sandbox; greps `.git/hooks/pre-commit` for the invocation line.
- Test 2 (AC#2): seeds STATE.md, installs hook, appends a verifier block (raw text) → `git commit` exits 0.
- Test 3 (AC#3): edits prose outside the blocks (changes "Last updated:") → commit exits non-zero, stderr contains `STATE.md modified outside append-block`.
- Test 4 (AC#4): appends a block with `author=coder` → commit exits non-zero, stderr contains `STATE.md author must be verifier`.
- Test 5 (AC#5): with a block deleted, `ARGOS_CYCLE_CLOSE=1 git commit` exits 0.
- Test 6 (AC#6): unrelated file change with STATE.md untouched → commit exits 0 (no false positive).
- Test 7 (state-append interop): runs `python3 -m argos.cli state-append --suffix done ...` against STATE.md, then `git commit` exits 0. Skipped with a `WARN` if `python3 -m argos.cli` is unavailable, mirroring AC#6 in `test_merge_driver.sh`.

### Acceptance criteria (from ticket)

1. `.git/hooks/pre-commit` invokes `pre-commit-state-write.sh` after init.
2. Verifier-only block append → commit exits 0.
3. Modification outside a block → commit exits non-zero with stderr `STATE.md modified outside append-block`.
4. Coder-authored block → commit exits non-zero with stderr `STATE.md author must be verifier`.
5. `ARGOS_CYCLE_CLOSE=1` → commit exits 0 even with deletions.
6. Unrelated commit → exit 0.

Plus the user-injected requirement: `argos state-append` invocation must succeed under the hook (Test 7).

### Test strategy

```
sh argos/scripts/hooks/tests/test_pre_commit.sh
```

Exit 0 iff every AC test passes.

### Open questions

None. Hook covers both `argos/specs/STATE.md` (literal AC scope) and `argos/specs/v1.0/STATE.md` (matching `install-merge-driver.sh`'s coverage); this is a strict superset of the AC and consistent with project precedent.

## Implementation notes

- Hook script is POSIX `/bin/sh` + awk, mirroring `argos/scripts/state-merge-driver.sh`. ADR-001's stdlib-only mandate is satisfied trivially (no Python at runtime); ADR-002's AC-tooling mandate is satisfied by the harness using `python3 -m argos.cli` only as an optional interop check.
- `install-hooks.sh` honors `core.hooksPath` (Husky-friendly) and is idempotent: a sentinel-tagged block is rewritten in place on re-run. Initial bug: `awk -v close=...` collided with awk's builtin `close()`; renamed to `closetag` / `opentag`.
- `argos-init.sh` calls `install-hooks.sh` near the end (best-effort; non-fatal if not in a git repo). When ARG1-002 lands, the Python `init` will pick up the same script.
- The validator's state machine accepts blank-line additions everywhere (state-append inserts a leading blank before each block and a trailing blank before the next section heading). Author=verifier is enforced on every newly-opened block; deletions are unconditionally rejected (the only deletion path is `ARGOS_CYCLE_CLOSE=1`, handled at the top).

## Verification

### Acceptance Criteria evidence

| AC | Evidence |
|----|----------|
| AC#1 — `.git/hooks/pre-commit` invokes the hook after init | `argos/scripts/hooks/tests/test_pre_commit.sh::test_installer_registers` runs `install-hooks.sh` in a sandbox and greps the result. PASS (and a follow-up idempotency check confirms a second run leaves exactly one invocation line). |
| AC#2 — verifier-only block append passes | `test_verifier_block_passes` writes a complete `<!-- argos:entry ... author=verifier ... -->` block into `## Done this cycle` and runs `git commit`. Exits 0. |
| AC#3 — modification outside a block fails | `test_outside_block_fails` mutates the prose `**Last updated:**` line. Commit exits non-zero, stderr contains the literal `STATE.md modified outside append-block`. |
| AC#4 — `author=coder` block fails | `test_coder_author_fails` appends a coder-authored block. Commit exits non-zero, stderr contains `STATE.md author must be verifier`. |
| AC#5 — `ARGOS_CYCLE_CLOSE=1` bypass | `test_cycle_close_bypass` deletes the seed block. First commit (no env var) fails as the baseline; retry under `ARGOS_CYCLE_CLOSE=1` exits 0. |
| AC#6 — no false positives | `test_unrelated_commit_passes` commits an unrelated file with STATE.md untouched. Exit 0. |
| Plus: `argos state-append` interop | `test_state_append_interop` invokes `python3 -m argos.cli state-append --suffix done ...` and then `git commit`. Block lands and commit succeeds, confirming the sanctioned write path is friendly to the hook. |

### Tests run

```
$ sh argos/scripts/hooks/tests/test_pre_commit.sh
PASS: AC#1 .git/hooks/pre-commit invokes pre-commit-state-write.sh
PASS: AC#1 installer idempotent (1 invocation line after re-run)
PASS: AC#2 verifier-only block append commit succeeds
PASS: AC#3 stderr contains 'STATE.md modified outside append-block'
PASS: AC#4 stderr contains 'STATE.md author must be verifier'
PASS: AC#5 ARGOS_CYCLE_CLOSE=1 bypass: block deletion accepted
PASS: AC#6 unrelated commit (no STATE.md change) succeeds
PASS: interop state-append + commit succeeds under hook

Summary: 8 pass, 0 fail, 0 warn
```

Exit code 0.

### Regression scan

- No edits to existing CLI / parser modules; `state_append.py` and `state_parser.py` untouched.
- `argos-init.sh` gains a tail-end `install-hooks.sh` invocation, gated on `argos/scripts/install-hooks.sh -x` and `git rev-parse --git-dir`. Existing init flow (template render + sentinel) is unchanged for non-git or hook-script-absent invocations.
- No new runtime deps. Hook runs on POSIX `/bin/sh` + GNU/BSD `awk` available on every dev machine the merge driver already targets.

### STATE.md diff proposal

Block to append under `## Done this cycle` (via `argos state-append --suffix verify`):

```
- **[<UTC-ISO>] ARG1-032 — verified** (session local-2026-05-03, worktree `argos-v1-arg1-032`)
  - Files added: `argos/scripts/hooks/pre-commit-state-write.sh`, `argos/scripts/install-hooks.sh`, `argos/scripts/hooks/tests/test_pre_commit.sh`
  - Files edited: `argos/scripts/argos-init.sh`, `argos/specs/v1.0/tickets/ARG1-032-pre-commit-verifier-only-state.md`
  - AC harness: 8 pass, 0 fail, 0 warn
  - Findings: 0 critical, 0 major, 0 minor
  - Decision: pass
```

### Structured decision block

<!-- argos:verifier-output -->
tests_ran: true
findings: []
decision: pass
<!-- /argos:verifier-output -->
