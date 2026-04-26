# ARG1-030 — Verifier severity rubric (critical / major / minor) + structured output schema

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 4 (Severity-tiered verifier)

## Intent

Replace the v0.5 verifier's binary PASS/FAIL output with a three-tier severity rubric (critical / major / minor) and a structured findings block. Update `.claude/agents/verifier.md`'s system prompt to (a) classify every finding by tier using the criteria in ARCHITECTURE.md §Components/Severity-Tiered Verifier, (b) emit a parseable structured block, (c) refuse to mark a missing test run as anything other than critical, (d) quote real test stdout for any critical finding. Pure prompt change; no consumer logic in this ticket.

## Context

ARCHITECTURE.md §Components/Severity-Tiered Verifier defines tiers and behavior. PRD success criterion #2 (≥95% scope-drift catch rate) depends on critical findings being non-bypassable. This ticket is the foundation for ARG1-031 (which writes the decision into STATE) and ARG1-013 (which retries on critical/major).

## Non-goals

- No consumer changes (orchestrator parsing of the structured block is ARG1-031).
- No retry implementation (ARG1-013).
- No coverage-threshold definition for major (TODO in ARCHITECTURE.md — follow-up).
- No lint-rule rubric for major-vs-minor (TODO in ARCHITECTURE.md — follow-up).

## Acceptance criteria

- [ ] `.claude/agents/verifier.md` body contains the literal strings `critical`, `major`, `minor`, `findings:`, `decision:`, and `pass-with-minors`; verified by `grep -Fc` per string.
- [ ] `.claude/agents/verifier.md` body contains the literal string `MUST quote real test stdout` and `MUST refuse to classify a missing test run as pass`.
- [ ] `argos/specs/v1.0/agents/verifier.md` exists; `diff -q .claude/agents/verifier.md argos/specs/v1.0/agents/verifier.md` exits 0.
- [ ] `argos/specs/v1.0/schemas/verifier-output.md` defines the structured block schema with example; `grep -Fc 'findings:' argos/specs/v1.0/schemas/verifier-output.md` returns ≥1.
- [ ] A reference parser at `argos/cli/verifier_parser.py` (or equivalent) accepts the example from the schema doc; running it via `argos verifier-parse <example.txt>` exits 0 and emits JSON with keys `findings` (list) and `decision` (string).
- [ ] The schema doc explicitly enumerates the three valid `decision` values: `pass`, `pass-with-minors`, `fail`.

## Depends on

_none — root of Epic 4_

## Touches

- `.claude/agents/verifier.md` (modify)
- `argos/specs/v1.0/agents/verifier.md` (new — canonical mirror)
- `argos/specs/v1.0/schemas/verifier-output.md` (new)
- `argos/cli/verifier_parser.py` (or equivalent — new)
- `argos/cli/tests/test_verifier_parser.py` (or equivalent)

## Parallelizable with

- ARG1-001 (CLI scaffold)
- ARG1-002 (init)
- ARG1-010 (orchestrator agent — different agent file)
- ARG1-020 (worktree spawn)
- ARG1-040 (escalation schema)
- ARG1-050 (STATE block schema)
- ARG1-053 (config split)
