# ARG1-052 — STATE.md custom git merge driver (concatenation + dedupe-by-id)

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 6 (STATE.md migration + config split)

## Intent

Ship `argos/scripts/state-merge-driver.sh`: a git custom merge driver that resolves STATE.md conflicts by concatenating both sides' new blocks within each section and deduplicating by `id` attribute. Plus `argos/scripts/install-merge-driver.sh`: registers the driver with git (called by `argos init`). Result: concurrent verifiers writing different blocks to the same section produce no conflict markers — only true content conflicts (which should not happen given the append-only invariant) escalate to the operator.

## Context

ARCHITECTURE.md §Contracts/STATE.md format specifies that merge conflicts must be trivially resolvable by concatenation. PRD success criterion #4 (parallel speedup) breaks if every parallel batch produces hand-resolved STATE.md conflicts.

## Non-goals

- No conflict resolution outside STATE.md (this driver is registered via `.gitattributes` for STATE.md only).
- No interactive merge UI.
- No three-way merge of block bodies (blocks are immutable; conflicts on body content indicate someone violated the append-only rule and must be surfaced).
- No automatic registration in `.git/config` outside of `argos init` (operator running `git clone` after init must re-run `argos init` or the install script — TODO: document this gotcha).

## Acceptance criteria

- [ ] `bash argos/scripts/install-merge-driver.sh` exits 0; `git config --get merge.argos-state.driver` prints a non-empty value containing `state-merge-driver.sh`.
- [ ] `.gitattributes` (created or appended by the install script) contains a line matching `argos/specs/STATE.md merge=argos-state`.
- [ ] In a synthetic test repo with two branches each appending one new block to the same STATE.md section, `git merge` exits 0; the merged file contains both blocks (verified by `grep -c '<!-- argos:entry'` increasing by 2 from the base) and no `<<<<<<<` conflict markers.
- [ ] In a synthetic conflict where both branches add a block with the same `id` (impossible in normal operation but possible if hand-crafted), the driver keeps one copy and exits 0; merged file contains exactly one block with that `id`.
- [ ] In a synthetic conflict where one branch modifies an existing block's body (violating append-only), the driver exits non-zero; `git status` shows a conflict; stderr from the driver names the offending `id` and contains `block body modified — append-only violated`.
- [ ] After merge, `argos state-parse argos/specs/STATE.md` exits 0 (merged file is valid).
- [ ] The driver runs in under 1 second on a STATE.md with 1000 blocks (`time bash argos/scripts/state-merge-driver.sh ...` real < 1.0).

## Depends on

- ARG1-050 (block schema — driver parses blocks)

## Touches

- `argos/scripts/state-merge-driver.sh` (new)
- `argos/scripts/install-merge-driver.sh` (new)
- `argos/scripts/tests/test_merge_driver.sh` (or equivalent — new)
- `.gitattributes` (modify or create — single-line append)

## Parallelizable with

- ARG1-003 (status)
- ARG1-005 (attend)
- ARG1-010 (orchestrator agent)
- ARG1-021 (independence detection)
- ARG1-031 (verifier writeback)
- ARG1-032 (pre-commit hook — different script)
- ARG1-041 (escalation writer)
- ARG1-051 (state-append helper — different module)
- ARG1-053 (config split)
