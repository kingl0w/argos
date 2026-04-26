# ARG1-023 — Worktree merge-on-pass, preserve-on-fail

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P1
**Epic:** 3 (Parallel session manager)

## Intent

After a session's verifier returns `pass` or `pass-with-minors`, attempt fast-forward merge of the worktree's branch (`argos/{ticket-id}`) back to base; on conflict, halt the merge and write a blocking escalation (the verifier already passed — conflicts are an integration-level concern). On `fail`, leave the worktree and branch in place untouched for operator inspection. Return a structured result so the orchestrator can update the dispatch log.

## Context

ARCHITECTURE.md §Components/Parallel Session Manager specifies fast-forward-or-three-way-merge on pass, preserve-on-fail. Worktree pruning of merged branches is `argos sync`'s job (ARG1-004), not this ticket.

## Non-goals

- No worktree deletion on pass (operator may want to inspect; pruning is `argos sync`).
- No conflict resolution. Conflicts always escalate.
- No rebase strategy. v1.0 uses fast-forward when possible, three-way merge otherwise.
- No revert of merged work on subsequent failures.

## Acceptance criteria

- [ ] With a worktree branch one commit ahead of base, `argos worktree-finalize --ticket ARG1-099 --result pass` exits 0; `git log --oneline base..argos/ARG1-099` is empty after merge (fast-forwarded).
- [ ] With a worktree branch where base has moved but no conflicts exist, `argos worktree-finalize --ticket ARG1-099 --result pass` exits 0; `git log --first-parent base | head -1` shows a merge commit.
- [ ] With a worktree branch that conflicts with base, `argos worktree-finalize --ticket ARG1-099 --result pass` exits non-zero; the merge is aborted (`git status` in base shows clean tree); a file under `argos/specs/escalations/ARG1-099-*.md` exists with `severity: blocking` and body containing `merge conflict`.
- [ ] With result `fail`, `argos worktree-finalize --ticket ARG1-099 --result fail` exits 0; `test -d .argos/worktrees/ARG1-099-*` exits 0 (preserved); the branch `argos/ARG1-099` still exists (`git branch --list 'argos/ARG1-099'` non-empty).
- [ ] With result `pass-with-minors`, behavior is identical to `pass` (merge attempted).
- [ ] `argos worktree-finalize --json --ticket ARG1-099 --result pass` emits a JSON object with keys `merged`, `merge_strategy` (`ff` or `three-way`), `conflicts`, `worktree_preserved`.

## Depends on

- ARG1-020 (worktree spawn — produces the worktrees this ticket finalizes)

## Touches

- `argos/cli/orchestrator/merge.py` (or equivalent — new)
- `argos/cli/commands/worktree_finalize.py` (or equivalent — new)
- `argos/cli/tests/test_worktree_finalize.py` (or equivalent)

## Parallelizable with

- ARG1-003 (status)
- ARG1-004 (sync)
- ARG1-013 (auto-fix retry — different module)
- ARG1-021 (independence — different module)
- ARG1-022 (parallel dispatch — different module)
- ARG1-031 (verifier structured decision)
- ARG1-041 (escalation writer)
- ARG1-054 (cycle close)
