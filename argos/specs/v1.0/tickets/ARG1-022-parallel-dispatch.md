# ARG1-022 — Parallel dispatch with `max_parallel` cap and serial fallback

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 3 (Parallel session manager)

## Intent

The orchestrator's main dispatch loop. Read the next batch from the queue, run independence detection (ARG1-021), partition into independence groups, dispatch up to `max_parallel` (from `argos/config.toml`) sessions in the largest group concurrently using `argos run-session` (ARG1-020). Wait for all to finish, collect results, advance to the next group. If independence detection fails or returns an error, fall back to strict serial dispatch (degraded but correct, per ARCHITECTURE.md §Invariants).

## Context

ARCHITECTURE.md §Components/Parallel Session Manager specifies `max_parallel` (default 3), serial fallback, and per-group barrier semantics. This is the ticket where PRD success criterion #4 (≥2x parallel speedup) is delivered.

## Non-goals

- No dynamic resizing of `max_parallel` mid-run.
- No work-stealing across groups (a finished group does not pull from the next group early).
- No cross-batch parallelism (orchestrator processes one batch at a time).
- Worktree merge is delegated to ARG1-023.

## Acceptance criteria

- [ ] With three synthetic independent tickets and `max_parallel = 3`, `argos orchestrate --batch-size 3` produces three concurrent sessions; verified by three running `claude` processes overlapping in time (`ps -ef | grep claude | wc -l ≥ 3` at peak), captured by a wrapper test script.
- [ ] With `max_parallel = 1`, the same three tickets run serially; total wall-clock is ≥ sum of individual session durations × 0.95 (no parallelism).
- [ ] With three tickets where two share a file in `files_touched`, the orchestrator dispatches the two dependent ones serially and the third one in parallel with the first of the two; verified by the dispatch log timestamps.
- [ ] When ARG1-021 returns an error (e.g., a ticket missing `files_touched:`), the orchestrator falls back to strict serial dispatch and stdout contains `independence detection failed; falling back to serial`.
- [ ] After a parallel batch completes, no orphaned worktrees: `git worktree list | wc -l` equals the count after subtracting expected merged-but-preserved worktrees from ARG1-023.
- [ ] `argos orchestrate --batch-size 5 --dry-run` emits a markdown table on stdout with columns `ticket_id | group | dispatch_order | parallel_with`.

## Depends on

- ARG1-020 (worktree spawn)
- ARG1-021 (independence detection)
- ARG1-053 (config split — reads `orchestrator.max_parallel`)

## Touches

- `argos/cli/orchestrator/dispatch.py` (or equivalent — new)
- `argos/cli/tests/test_parallel_dispatch.py` (or equivalent)

## Parallelizable with

- ARG1-003 (status)
- ARG1-004 (sync)
- ARG1-005 (attend)
- ARG1-012 (dispatch log writer — different module)
- ARG1-023 (worktree merge — different module)
- ARG1-031 (verifier structured decision)
- ARG1-041 (escalation writer)
