# ARG1-021 — Independence detection via file-overlap analysis

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 3 (Parallel session manager)

## Intent

Implement file-overlap independence detection. The planner subagent gains a required `files_touched:` field in its Plan-section output; the orchestrator parses this field across candidate tickets and computes pairwise disjointness. Two tickets are independent iff their `files_touched:` sets are disjoint AND neither lists the other in `depends_on:` frontmatter. Output is a list of independence groups feeding ARG1-022.

## Context

ARCHITECTURE.md §Components/Parallel Session Manager § "Independence detection" specifies file-overlap as the v1.0 strategy. PRD success criterion #4 (≥2x parallel speedup) depends on detection being good enough to find genuinely independent tickets — and conservative enough not to falsely parallelize colliding ones.

## Non-goals

- No directory-prefix overlap heuristics (TODO in ARCHITECTURE.md — left for follow-up).
- No import-graph analysis (a ticket's `files_touched` may transitively conflict via imports; v1.0 accepts this risk).
- No dynamic re-evaluation mid-batch (independence is computed once per batch).
- No dry-plan caching (ARCHITECTURE.md TODO — follow-up).

## Acceptance criteria

- [ ] `argos independence ARG1-099 ARG1-100` (two synthetic tickets with disjoint `files_touched`) exits 0; stdout contains `independent`.
- [ ] `argos independence ARG1-099 ARG1-101` (synthetic tickets sharing one file in `files_touched`) exits 0; stdout contains `dependent` and names the conflicting file path.
- [ ] `argos independence ARG1-099 ARG1-102` (synthetic ticket where ARG1-102 has `depends_on: [ARG1-099]` in frontmatter) exits 0; stdout contains `dependent` and the reason `depends_on`.
- [ ] On a ticket whose Plan section is missing `files_touched:`, `argos independence` exits non-zero; stderr names the ticket ID and contains `missing files_touched`.
- [ ] `argos independence --json ARG1-099 ARG1-100 ARG1-101` emits a JSON object on stdout with key `groups` whose value is a list of lists of ticket IDs (each inner list a maximal independent group).
- [ ] `.claude/agents/planner.md` body contains the literal string `files_touched:` (planner instructed to emit the field).

## Depends on

- ARG1-010 (orchestrator agent — consumer)
- ARG1-020 (worktree spawn — needed to invoke planner in dry mode)

## Touches

- `argos/cli/orchestrator/independence.py` (or equivalent — new)
- `.claude/agents/planner.md` (modify — add `files_touched:` requirement)
- `argos/specs/v1.0/agents/planner.md` (new — canonical mirror)
- `argos/cli/tests/test_independence.py` (or equivalent)

## Parallelizable with

- ARG1-003 (status)
- ARG1-005 (attend)
- ARG1-012 (dispatch log writer — different module)
- ARG1-023 (worktree merge — different module)
- ARG1-031 (verifier structured decision)
- ARG1-041 (escalation writer)
- ARG1-052 (merge driver)
