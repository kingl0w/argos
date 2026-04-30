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

## Plan

**Sizing.** Two new code modules + one new test module + a one-line subcommand registration in the unified dispatcher. All Python ≥3.9 stdlib only per ADR-001; subprocess-to-git is the contract per the ticket Intent.

**Library / shim split.** Mirrors ARG1-051's pattern: `argos/cli/worktree.py` exposes the importable primitives (validation, git invocation, harness resolution, spawn) so the orchestrator (ARG1-022) can call them directly without spawning a subprocess; `argos/cli/commands/run_session.py` is the CLI shim that maps argparse to library calls and exit codes.

### Files touched

| Path | Status | Purpose |
|------|--------|---------|
| `argos/cli/worktree.py` | new | Library: `compute_branch_name`, `find_repo_root`, `validate_worktree_path`, `worktree_path_listed`, `add_worktree`, `resolve_harness_binary`, `spawn_session`, plus typed exception classes (`WorktreeError` / `InvalidWorktreePathError` / `WorktreeAlreadyExistsError` / `GitError` / `HarnessNotFoundError`). |
| `argos/cli/commands/run_session.py` | new | CLI shim: argparse for `--ticket`, `--worktree`, `--epic`, `--dry-run`, `--debug-print-cwd`; loads `harness.claude_code_binary` via the ARG1-053 config loader (best-effort; failures are non-fatal so a fresh repo without `argos init` still works); maps the library's exceptions to AC stderr substrings. |
| `argos/cli/__main__.py` | edit | Register `run-session` in `INTERNAL_SUBCOMMANDS`, dispatch branch, help line. |
| `argos/cli/tests/test_run_session.py` | new | unittest tests covering all six ACs plus library-level checks and an env-vars/cwd-pinning regression. |

### Behavior contract

- Worktree path validation: resolves `--worktree` against CWD if relative, then asserts the resolved path is a strict descendant of `<repo_root>/.argos/worktrees/`. Rejects with stderr `worktree must live under .argos/worktrees/` (AC#5). Rejects the worktrees-root directory itself and `..`-traversal escapes.
- Branch name: `argos/{ticket-id}` per ARCHITECTURE.md §Components/Parallel Session Manager.
- Duplicate detection: pre-check via `git worktree list --porcelain` AND on-disk existence; second invocation against the same path exits non-zero with stderr containing `worktree already exists` (AC#4). git's own "already exists" stderr is also reclassified as the same error so concurrent racers see a uniform message.
- Harness resolution order: env override `ARGOS_RUN_SESSION_HARNESS_BIN` → loaded `harness.claude_code_binary` (ARG1-053) → `claude` on PATH. Tests override via env to `/bin/true`.
- `--dry-run`: prints `branch:` and `worktree:` lines to stdout, exits 0, no git or spawn invocation.
- `--debug-print-cwd`: validates inputs, runs `git worktree add`, then prints the absolute worktree path on stdout and exits 0 *without* invoking the harness binary. This satisfies AC#6 ("the spawned session sees only the worktree CWD") by making the cwd-pinning observable from outside an actual session.
- Spawn (default): `subprocess.run([binary], cwd=worktree, env=…)` inheriting stdio so an interactive Claude Code session keeps its tty. Three context env vars exported to the child: `ARGOS_TICKET`, `ARGOS_EPIC`, `ARGOS_WORKTREE`. Returns the child's exit code.

### Non-decisions deferred to later tickets

- Specific argv used to load the planner subagent inside Claude Code (e.g. `--agent planner`). Out of scope here; ARG1-022 wires the orchestrator's spawn args. ARG1-020 commits only to the cwd-pinning + ARGOS_* env-var contract.
- Worktree pruning, merge-on-pass, three-way merge: ARG1-023.
- Independence detection: ARG1-021.
- Parallel orchestration / `max_parallel`: ARG1-022.

## Verification

Run from inside a fresh git repo with `ARGOS_RUN_SESSION_HARNESS_BIN=/bin/true`. The argos worktree itself is not used as the test repo so its `.argos/worktrees/` stays clean.

- AC#1 met. `argos run-session --ticket ARG1-099 --worktree .argos/worktrees/ARG1-099-test --epic EPIC-001 --dry-run` exits 0; stdout contains both `argos/ARG1-099` and `<tmp-repo>/.argos/worktrees/ARG1-099-test`.
- AC#2 met. After the real run, `git worktree list | grep -F ARG1-099-test` exits 0; `git branch --list 'argos/ARG1-099'` shows the branch.
- AC#3 met. `test -d .argos/worktrees/ARG1-099-test` exits 0 after the session exits; no auto-cleanup.
- AC#4 met. Second invocation exits non-zero; stderr contains `worktree already exists`. Threaded concurrent-launch test confirms exactly one of two simultaneous dispatches succeeds and the loser surfaces the same substring.
- AC#5 met. `--worktree /tmp/foo` exits non-zero; stderr contains `worktree must live under .argos/worktrees/`. Same response for relative paths outside `.argos/worktrees/` (e.g. `src/foo`).
- AC#6 met. `--debug-print-cwd` emits exactly the absolute worktree path (not the repo root); a regression test asserts the harness child sees `pwd == <worktree>` and `ARGOS_TICKET` / `ARGOS_EPIC` / `ARGOS_WORKTREE` set correctly.

Tests: `python3 -m unittest argos.cli.tests.test_run_session -v` → 19/19 OK. Regression sweep `test_version test_verifier_parser test_escalation_validator test_state_append test_frontmatter_parser test_config test_run_session` → 108/108 OK. Stdlib-only preserved (no new entries in `pyproject.toml` `[project.dependencies]`); imports inside `worktree.py` and `run_session.py` are `os`, `shutil`, `subprocess`, `argparse`, `sys`, `pathlib`, `typing`, plus `__future__`.

Decision: pass
