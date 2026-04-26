# ARG1-031 — Verifier writes structured decision into STATE.md block

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 4 (Severity-tiered verifier)

## Intent

Wire the verifier's structured output (ARG1-030) into a STATE.md append. On `pass`, write a `verified` block. On `pass-with-minors`, write a `verified-with-minors` block listing the minor findings. On `fail`, write a `verification-failed` block summarizing the critical/major findings. All writes go through `argos state-append` (ARG1-051) so the merge driver and block-id generator stay in one place. Update `.claude/agents/verifier.md` to invoke this command.

## Context

ARCHITECTURE.md §Components/Severity-Tiered Verifier specifies that the verifier remains the sole writer of STATE.md and that minor findings are logged-and-continued. ARCHITECTURE.md §Contracts/Session→STATE.md mandates writes go through the helper, not direct edits.

## Non-goals

- No retry triggering (ARG1-013).
- No alteration of existing STATE.md sections (writes go to "In progress" on start, "Done this cycle" on finish — already-defined).
- No human-readable summary block beyond what the schema requires.

## Acceptance criteria

- [ ] On a synthetic verifier run with `decision: pass`, `argos/specs/STATE.md` gains exactly one new block matching `<!-- argos:entry .* author=verifier .* -->` containing the literal `verified` and the ticket ID.
- [ ] On a synthetic verifier run with `decision: pass-with-minors` and two minor findings, the new STATE.md block contains the literal `verified-with-minors`, both finding `file:line` references, and counts `0 critical, 0 major, 2 minor`.
- [ ] On a synthetic verifier run with `decision: fail` and one critical finding, the new STATE.md block contains the literal `verification-failed` and the verbatim test stdout (verified by `grep -Fc` of a known stdout fragment ≥ 1).
- [ ] The verifier never invokes a write tool other than `argos state-append`; verified by absence of `Edit`/`Write` tool calls targeting `argos/specs/STATE.md` in a test session transcript.
- [ ] `.claude/agents/verifier.md` body contains the literal command `argos state-append`.
- [ ] Two concurrent verifier runs (different tickets, different sessions) both successfully append blocks; final STATE.md contains both block `id`s; no block is overwritten.

## Depends on

- ARG1-030 (verifier severity rubric — produces the structured output)
- ARG1-051 (state-append helper — write path)

## Touches

- `.claude/agents/verifier.md` (modify — invoke `argos state-append`)
- `argos/specs/v1.0/agents/verifier.md` (modify — keep in sync)
- `argos/cli/verifier_writeback.py` (or equivalent — formats the block from structured output)
- `argos/cli/tests/test_verifier_writeback.py` (or equivalent)

## Parallelizable with

- ARG1-003 (status)
- ARG1-005 (attend)
- ARG1-011 (orchestrate slash command)
- ARG1-012 (dispatch log writer)
- ARG1-021 (independence detection)
- ARG1-022 (parallel dispatch)
- ARG1-023 (worktree merge)
- ARG1-041 (escalation writer)
- ARG1-052 (merge driver)
