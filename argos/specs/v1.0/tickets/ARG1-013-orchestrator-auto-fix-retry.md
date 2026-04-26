# ARG1-013 — Orchestrator auto-fix retry (cap: 1) on critical/major verifier fail

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P1
**Epic:** 2 (Orchestrator)

## Intent

When a session's verifier returns `decision: fail` with critical or major findings, the orchestrator re-dispatches the ticket through planner → coder → watchdog → verifier within the same worktree exactly one time. If the second verifier still fails, the orchestrator marks the ticket failed and writes a blocking escalation. No third attempt. Minor findings never trigger retry.

## Context

ARCHITECTURE.md §Components/Severity-Tiered Verifier specifies the cap-1 retry behavior. PRD success criterion #3 (≥80% genuine ambiguity) depends on retries absorbing transient/easily-fixed failures so they don't reach the operator as escalations.

## Non-goals

- No retry budget configuration beyond enabled/disabled. The cap is hard-coded at 1 per ARCHITECTURE.md §Invariants.
- No partial-state retry (e.g., re-running only the verifier). Retry re-dispatches the full inner loop.
- No retry on watchdog failure. The v0.5 planner→coder retry-on-watchdog path is unchanged.

## Acceptance criteria

- [ ] On a synthetic ticket whose verifier returns `decision: fail` with one critical finding, the orchestrator dispatches the inner loop a second time; verified by two distinct `session_id`s appearing in the dispatch log for that ticket.
- [ ] On a synthetic ticket whose verifier returns `fail` then `pass` on retry, the dispatch log final entry contains `decision: pass` and no escalation file is created.
- [ ] On a synthetic ticket whose verifier returns `fail` twice, exactly one escalation file appears under `argos/specs/escalations/` with `severity: blocking` and the ticket ID; no third dispatch occurs (verified by exactly two `session_id`s in the dispatch log).
- [ ] On a synthetic ticket whose verifier returns `pass-with-minors`, no retry occurs (verified by exactly one `session_id` in the dispatch log) and STATE.md gets a `verified-with-minors` block.
- [ ] `argos/config.toml` key `verifier.auto_fix_retries = 0` disables retry; with that setting, a synthetic critical-fail ticket produces an escalation immediately after the first verifier fail (one `session_id` in the dispatch log).

## Depends on

- ARG1-010 (orchestrator agent — modify body for retry logic)
- ARG1-031 (verifier structured decision — orchestrator reads `decision` field)

## Touches

- `.claude/agents/orchestrator.md` (modify — retry logic in agent prompt)
- `argos/specs/v1.0/agents/orchestrator.md` (modify — keep in sync)
- `argos/cli/orchestrator/retry.py` (or equivalent — new)
- `argos/cli/tests/test_retry.py` (or equivalent)

## Parallelizable with

- ARG1-003 (status)
- ARG1-004 (sync)
- ARG1-022 (parallel dispatch — different module)
- ARG1-023 (worktree merge — different module)
- ARG1-041 (escalation writer)
- ARG1-051 (state-append helper)
- ARG1-054 (cycle close)
