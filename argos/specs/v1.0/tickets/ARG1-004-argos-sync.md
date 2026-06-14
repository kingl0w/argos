# ARG1-004 — `argos sync` reconciles tickets, issues, STATE, and worktrees

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P1
**Epic:** 1 (CLI installer)

## Intent

Implement `argos sync`. Three reconciliations: (1) ticket files ↔ GitHub Issues (re-render Issue bodies from ticket markdown via the existing v0.5 sync workflow, callable locally); (2) STATE.md "Done this cycle" entries ↔ recent git log (fail loudly if mismatched, do not auto-correct); (3) prune worktrees under `.argos/worktrees/` whose branches have been merged and deleted. The `--close-cycle` flag delegates to ARG1-054.

## Context

PRD §Distribution lists `argos sync` as one of three v1.0 commands. ARCHITECTURE.md §Components/Parallel Session Manager specifies worktree pruning as a `argos sync` responsibility. The ticket↔issue reconciliation already exists as v0.5 CI; this ticket exposes it through the CLI for local invocation and adds STATE↔git and worktree pruning.

## Non-goals

- No re-rendering of Issues that don't already exist (Issue creation is CI's job on ticket file creation).
- No auto-fix of STATE↔git mismatches. Mismatches are reported and the operator decides.
- Cycle close is delegated to ARG1-054; this ticket only wires `--close-cycle` to that handler.

## Acceptance criteria

- [ ] `argos sync --dry-run` exits 0 and stdout lists the three reconciliation phases as `OK` / `WOULD-FIX` / `MISMATCH` with no side effects.
- [ ] After deleting a stale worktree branch on origin and running `argos sync`, the local worktree directory under `.argos/worktrees/` for that branch is gone and `git worktree list` no longer references it.
- [ ] When STATE.md "Done this cycle" lists a ticket whose merge commit is absent from `git log --first-parent main`, `argos sync` exits non-zero; stderr names the ticket ID and the missing commit.
- [ ] `argos sync --close-cycle` invokes the cycle-close handler (ARG1-054) and exits with that handler's exit code.
- [ ] `argos sync --no-issues` skips the GitHub-touching phase; works offline (no network calls observable via `strace -e trace=network` or equivalent — TODO: pick a portable check).

## Depends on

- ARG1-002 (init — sync assumes initialized layout)
- ARG1-054 (cycle close — `--close-cycle` delegates here)

## Touches

- `argos/cli/commands/sync.py` (or equivalent)
- `argos/cli/reconcile.py` (or equivalent — shared reconciliation logic)
- `argos/cli/tests/test_sync.py` (or equivalent)

## Parallelizable with

- ARG1-003 (status — separate command)
- ARG1-005 (attend — separate command)
- ARG1-013 (auto-fix retry — orchestrator module)
- ARG1-022 (parallel dispatch)
- ARG1-032 (pre-commit hook — scripts dir)

## Plan

New module `argos/cli/reconcile.py` holds the three pure reconciliation
functions (so the command body stays thin and the logic is unit-testable
against temp repos, mirroring `clean_queue.py`):

1. `reconcile_state_git(*, state_file, repo_root, main_ref="main")` —
   read-only. Parse STATE.md, collect `ticket=` ids of `argos:entry` blocks
   inside `## Done this cycle`, and for each id check whether its ticket id
   appears (word-boundary) in any subject of `git log --first-parent <main_ref>`.
   Missing → `MISMATCH` carrying the offending ticket ids. Never mutates
   (Non-goal: no auto-fix of STATE↔git).
2. `reconcile_worktrees(*, repo_root, main_ref="main", dry_run)` — enumerate
   `git worktree list --porcelain`, keep those under `.argos/worktrees/`,
   and mark a worktree prunable iff its branch is fully merged into
   `<main_ref>` (`git merge-base --is-ancestor`) **and** the branch is gone
   from `origin` (no `refs/remotes/origin/<branch>`; trivially true when no
   `origin` remote exists). dry-run → `WOULD-FIX` list; real → `git worktree
   remove --force` + `git branch -D` + `git worktree prune`, status `FIXED`.
   Purely local git — no implicit fetch — so the command stays offline-safe.
3. `reconcile_issues(*, tickets_dir, repo_root, dry_run, backend)` — re-render
   existing GitHub Issue bodies from ticket markdown via a `gh`-shelling
   backend (the v0.5 `argos-sync.sh push` semantics, update-only per the
   Non-goal). Skipped (reported `OK` with a "skipped" note) when `--no-issues`
   is passed or `gh` is unavailable/unauthenticated — the only network phase.

`argos/cli/commands/sync.py` (CLI shim):
- `--close-cycle` / `--clean-queue` strip the flag and delegate to
  `cycle_close.main` / `clean_queue.main`, returning their exit code (AC#4).
- otherwise run all three phases, print a one-line-per-phase status table to
  stdout (vocabulary `OK` / `WOULD-FIX` / `MISMATCH` in dry-run; `FIXED`
  replaces `WOULD-FIX` in a real run), then exit non-zero iff state-git is a
  `MISMATCH`, writing the ticket id + missing-commit description to stderr
  (AC#3). `--dry-run` always exits 0 (AC#1). `--no-issues` skips phase 3
  with zero `gh` invocations (AC#5).

`argos/cli/__main__.py`: replace the inline `sync` handling with a single
delegation to `argos.cli.commands.sync.main(rest)`.

Tests in `argos/cli/tests/test_sync.py`: temp git repos (file:// bare origin
for the worktree-prune case) plus a fake issue backend and a PATH-shadow `gh`
sentinel for the offline assertion. Stdlib `unittest` only (ADR-001/002).
