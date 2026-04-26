# ARG1-011 — `/orchestrate` slash command + queue read entry point

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 2 (Orchestrator)

## Intent

Wire up the `/orchestrate` slash command: register it in `.claude/commands/`, point it at the orchestrator agent (ARG1-010), and provide the entry-point logic that reads STATE.md's Queue section and returns the next batch of ticket IDs to dispatch. No actual dispatch yet — that is ARG1-022. This ticket proves the orchestrator can be invoked from the harness and read the queue.

## Context

ARCHITECTURE.md §System shape places the orchestrator at the top of the dispatch chain, invoked by the operator. PRD §Distribution does not list `/orchestrate` as a CLI command; it is a Claude Code slash command (consistent with v0.5 `/next`, `/steer`, `/ask`).

## Non-goals

- No parallel dispatch (ARG1-022).
- No worktree creation (ARG1-020).
- No independence analysis (ARG1-021).
- No escalation production (ARG1-041).

## Acceptance criteria

- [ ] `test -f .claude/commands/orchestrate.md` exits 0.
- [ ] `argos orchestrate --dry-run` exits 0 and stdout lists the next 1–N ticket IDs from STATE.md's Queue section in order.
- [ ] When STATE.md's Queue section is empty, `argos orchestrate --dry-run; echo $?` prints `0` and stdout contains `queue empty`.
- [ ] When STATE.md is missing, `argos orchestrate --dry-run; echo $?` prints a non-zero number and stderr contains `STATE.md not found`.
- [ ] `grep -F 'orchestrator' .claude/commands/orchestrate.md` exits 0 (slash command references the agent).
- [ ] `argos orchestrate --dry-run --batch-size 2` returns at most 2 ticket IDs.

## Depends on

- ARG1-010 (orchestrator agent — slash command targets it)

## Touches

- `.claude/commands/orchestrate.md` (new)
- `argos/cli/commands/orchestrate.py` (or equivalent — new)
- `argos/cli/queue.py` (or equivalent — Queue-section parser)
- `argos/cli/tests/test_orchestrate.py` (or equivalent)

## Parallelizable with

- ARG1-003 (status)
- ARG1-005 (attend)
- ARG1-012 (dispatch log writer — different module)
- ARG1-020 (worktree spawn)
- ARG1-031 (verifier structured decision — verifier file)
- ARG1-041 (escalation writer)
