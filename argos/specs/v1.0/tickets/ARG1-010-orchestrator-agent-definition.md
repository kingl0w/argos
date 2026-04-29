# ARG1-010 — Orchestrator agent definition (allowed-tools, denied-paths, prompt)

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 2 (Orchestrator)

## Intent

Define the orchestrator subagent: system prompt that encodes its scope (read-only on PRD/ARCHITECTURE/STATE; read-write on tickets, dispatch logs, escalations), `allowed_tools` whitelist, `denied_paths` blacklist, and the dispatcher-and-reconciler authority model. The orchestrator's behavior is fully specified by this file plus the contracts it reads.

## Context

ARCHITECTURE.md §Components/Orchestrator names every authority boundary the agent must respect. This ticket commits the agent definition file and a mirrored canonical copy under `argos/specs/v1.0/agents/` so the spec and the runtime config stay tied. Without this, no other Epic-2 ticket has an agent to invoke.

## Non-goals

- No CLI command for invocation (that is ARG1-011).
- No dispatch log writing (that is ARG1-012).
- No retry loop logic (that is ARG1-013).
- No actual session spawning (that is Epic 3).

## Acceptance criteria

- [ ] `test -f .claude/agents/orchestrator.md` exits 0.
- [ ] `test -f argos/specs/v1.0/agents/orchestrator.md` exits 0; the two files have identical content (`diff -q .claude/agents/orchestrator.md argos/specs/v1.0/agents/orchestrator.md` exits 0).
- [ ] The frontmatter of `.claude/agents/orchestrator.md` parses cleanly and contains both `allowed_tools` and `denied_paths` keys; verified by `python3 -m argos.cli frontmatter-parse .claude/agents/orchestrator.md | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); sys.exit(0 if 'allowed_tools' in d and 'denied_paths' in d else 1)"` exiting 0. _(Retrofitted from a pyyaml-based check per ADR-002; ARG1-059.)_
- [ ] `denied_paths` includes the literal strings `argos/specs/PRD.md`, `argos/specs/ARCHITECTURE.md`, `argos/specs/STATE.md`; verified by `grep -Fc 'argos/specs/STATE.md' .claude/agents/orchestrator.md` returning ≥1 for each.
- [ ] The agent body contains the strings `dispatcher`, `reconciler`, `escalation`, and `cannot mutate code`; verified by `grep -Fc` per string.

## Depends on

- ARG1-040 (escalation schema — orchestrator routes to it)
- ARG1-050 (STATE.md schema — orchestrator reads it to pick work)
- ARG1-053 (config split — orchestrator reads `max_parallel`)

## Touches

- `.claude/agents/orchestrator.md` (new)
- `argos/specs/v1.0/agents/orchestrator.md` (new)

## Parallelizable with

- ARG1-002 (init)
- ARG1-020 (worktree spawn — separate file tree)
- ARG1-030 (verifier rubric — separate agent file)
- ARG1-041 (escalation writer)
- ARG1-051 (state-append helper)
- ARG1-052 (merge driver)
