# ARG1-020 — Worktree spawn helper (`argos run-session`)

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 3 (Parallel session manager)

## Intent

Implement `argos run-session --ticket ARG1-NNN --worktree <path> --epic EPIC-NNN`: create a git worktree at the specified path (branched from base as `argos/{ticket-id}`), launch a Claude Code session pinned to that worktree's CWD with the planner subagent loaded, and return when the session exits. Returns the session's exit code. This is the per-ticket primitive the orchestrator dispatches.

## Context

ARCHITECTURE.md §Components/Parallel Session Manager specifies one-worktree-per-ticket as an invariant. v1.0 cannot run parallel tickets without this primitive. The CLI command is invoked by the orchestrator (ARG1-022), not by humans directly, but it must be runnable standalone for testing.

## Non-goals

- No independence detection (ARG1-021).
- No parallel orchestration (ARG1-022).
- No merge-on-pass (ARG1-023).
- No cleanup of the worktree on success — that's ARG1-023's responsibility.

## Acceptance criteria

- [ ] `argos run-session --ticket ARG1-099 --worktree .argos/worktrees/ARG1-099-test --epic EPIC-001 --dry-run` exits 0 and stdout contains the resolved branch name `argos/ARG1-099` and the absolute worktree path.
- [ ] After `argos run-session --ticket ARG1-099 --worktree .argos/worktrees/ARG1-099-test --epic EPIC-001`, `git worktree list | grep -F ARG1-099-test` exits 0.
- [ ] After the session exits, the working tree at `.argos/worktrees/ARG1-099-test` still exists (no auto-cleanup); verified by `test -d .argos/worktrees/ARG1-099-test` exiting 0.
- [ ] Spawning two sessions targeting the same ticket ID at the same time: the second exits non-zero with stderr containing `worktree already exists` (no overlap).
- [ ] Worktree path outside `.argos/worktrees/` is rejected: `argos run-session --ticket ARG1-099 --worktree /tmp/foo --epic EPIC-001; echo $?` prints non-zero with stderr containing `worktree must live under .argos/worktrees/`.
- [ ] The spawned session sees only the worktree CWD: `argos run-session --ticket ARG1-099 --worktree .argos/worktrees/ARG1-099-test --epic EPIC-001 --debug-print-cwd` prints the absolute worktree path (not the repo root).

## Depends on

- ARG1-001 (CLI scaffold)
- ARG1-053 (config split — reads `harness.claude_code_binary`)

## Touches

- `argos/cli/commands/run_session.py` (or equivalent — new)
- `argos/cli/worktree.py` (or equivalent — new)
- `argos/cli/tests/test_run_session.py` (or equivalent)

## Parallelizable with

- ARG1-002 (init)
- ARG1-005 (attend)
- ARG1-010 (orchestrator agent)
- ARG1-011 (/orchestrate slash command)
- ARG1-030 (verifier rubric)
- ARG1-040 (escalation schema)
- ARG1-051 (state-append helper)
