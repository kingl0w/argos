# ARG1-040 — Escalation file schema and `escalations/` directory contract

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 5 (Escalation channel)

## Intent

Commit the canonical escalation file schema (frontmatter fields, body sections) per ARCHITECTURE.md §Components/Escalation Channel. Create the `argos/specs/escalations/` directory with a `.gitkeep` and a README explaining the directory's role. Provide a reference parser/validator. This is the contract every escalation producer (orchestrator, planner, coder, watchdog, verifier) writes against and every consumer (`argos attend`, webhook) reads against.

## Context

ARCHITECTURE.md §Components/Escalation Channel defines the schema inline. This ticket lifts it into a versioned schema document so changes go through the v1.0 → v1.x → v2.0 schema-evolution process rather than ad-hoc edits to ARCHITECTURE.md.

## Non-goals

- No escalation writer implementation (ARG1-041).
- No `argos attend` consumer (ARG1-005).
- No webhook delivery (ARG1-041).
- No retroactive validation of escalations from earlier sessions (none exist).

## Acceptance criteria

- [ ] `test -f argos/specs/v1.0/schemas/escalation.md` exits 0; the file documents required frontmatter fields `ticket_id`, `session_id`, `severity`, `raised_by`, `created` with example values.
- [ ] `test -f argos/specs/escalations/.gitkeep && test -f argos/specs/escalations/README.md` exits 0.
- [ ] `argos escalation-validate argos/specs/v1.0/schemas/examples/escalation-blocking.md` exits 0 (a committed example validates).
- [ ] `argos escalation-validate argos/specs/v1.0/schemas/examples/escalation-malformed.md` exits non-zero; stderr names the missing/invalid field.
- [ ] The schema doc lists the two valid `severity` values `blocking` and `advisory` and the five valid `raised_by` values `orchestrator`, `planner`, `coder`, `watchdog`, `verifier`.
- [ ] The schema doc requires the body to contain the four sections `## Question`, `## Context`, `## Options considered`, `## Why escalated`; the validator enforces presence (`grep -Fc '## Question' <file>` ≥ 1, etc.).

## Depends on

_none — root of Epic 5_

## Touches

- `argos/specs/v1.0/schemas/escalation.md` (new)
- `argos/specs/v1.0/schemas/examples/escalation-blocking.md` (new)
- `argos/specs/v1.0/schemas/examples/escalation-malformed.md` (new)
- `argos/specs/escalations/.gitkeep` (new)
- `argos/specs/escalations/README.md` (new)
- `argos/cli/escalation_validator.py` (or equivalent — new)
- `argos/cli/tests/test_escalation_validator.py` (or equivalent)

## Parallelizable with

- ARG1-001 (CLI scaffold)
- ARG1-002 (init)
- ARG1-020 (worktree spawn)
- ARG1-030 (verifier rubric)
- ARG1-050 (STATE block schema)
- ARG1-053 (config split)
