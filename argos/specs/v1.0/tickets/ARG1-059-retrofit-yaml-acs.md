# ARG1-059 — Retrofit `import yaml` ACs to use `argos frontmatter-parse`

**Status:** Queued
**Created:** 2026-04-29
**Priority:** P0
**Epic:** 1 (CLI scaffold) — closes the foot-gun surfaced by ARG1-057

## Intent

Rewrite every AC across `argos/specs/v1.0/tickets/` that uses `python -c "import yaml; ..."` so it invokes `argos frontmatter-parse` (per ADR-002) instead. AC-text-only change: do not modify any shipped output file (no edits to `.claude/agents/orchestrator.md`, `argos/specs/v1.0/agents/orchestrator.md`, future dispatch logs, or any other consumer of frontmatter). After this ticket, `grep -rn "import yaml" argos/specs/v1.0/tickets/` returns empty.

## Context

ARG1-057 surfaced that ARG1-010 AC#3 and ARG1-012 AC#1 used third-party `pyyaml` despite ADR-001's stdlib-only mandate, with the AC harness silently picking up a system `pyyaml` for ARG1-010 and that being interpreter-luck rather than design. ADR-002 ratified the resolution: AC tooling is stdlib-only, frontmatter validation goes through `argos frontmatter-parse`. ARG1-060 lands the subcommand. This ticket retrofits the AC text in shipped tickets so the foot-gun cannot recur and so Layer 2 tickets copying the established pattern see the new shape.

## Non-goals

- No changes to ARG1-010 / ARG1-012 / any other ticket's shipped output files. The frontmatter and the agent-def files those ACs validate already conform to the ADR-002 §3 subset; this ticket's retrofit does not require any output-file change.
- No changes to `.claude/agents/*.md`, `argos/specs/v1.0/agents/*.md`, or anything those ACs originally produced.
- No new ACs. The retrofit replaces the *invocation* of validation; the *semantics* (which keys must be present) is preserved.
- No changes to ADR-001 or ADR-002.
- No implementation of `argos frontmatter-parse` (ARG1-060).
- No retrofit of legacy v0.5 tickets at `argos/specs/tickets/`. v0.5 ACs are out of scope; only `argos/specs/v1.0/tickets/` is in scope.

## Acceptance criteria

- [ ] No AC verification command across `argos/specs/v1.0/tickets/` (other than self-references inside this retrofit ticket itself) invokes pyyaml at runtime; verified by `grep -nE '^- \[[ x]\] .*yaml\.safe_load' argos/specs/v1.0/tickets/*.md | grep -v 'ARG1-059-retrofit-yaml-acs'` returning no matches (exits 1). _(The `yaml.safe_load(` function call is the precise runtime foot-gun ADR-002 closes; bare-substring `import yaml` mentions in non-AC prose — historical context paragraphs, plan-section discussion — are out of scope for this AC.)_
- [ ] ARG1-010 AC#3 (line 27 of `argos/specs/v1.0/tickets/ARG1-010-orchestrator-agent-definition.md` as shipped, or its replacement) is rewritten to invoke `python3 -m argos.cli frontmatter-parse .claude/agents/orchestrator.md`, parse the JSON output via `python3 -c "import json,sys; d=json.loads(sys.stdin.read()); sys.exit(0 if 'allowed_tools' in d and 'denied_paths' in d else 1)"` (or equivalent stdlib-only one-liner), and exit 0.
- [ ] ARG1-010 retrofitted AC#3 still passes when run against the current `.claude/agents/orchestrator.md` and `argos/specs/v1.0/agents/orchestrator.md`. Verified by running the rewritten AC command end-to-end on this branch.
- [ ] ARG1-012 AC#1 (the legacy yaml-based dispatch-log validation line in `argos/specs/v1.0/tickets/ARG1-012-dispatch-log-writer.md`) is rewritten to invoke `argos frontmatter-parse` against the dispatch log path and assert the same six required keys (`ticket_id`, `epic_id`, `batch_id`, `dispatched_at`, `worktree_path`, `session_id`).
- [ ] ARG1-012's retrofitted AC still passes when ARG1-012 itself eventually lands and writes a dispatch log file (no end-to-end run required by this ticket — ARG1-012 is queued, not shipped — but the AC's *shape* must be invocable as written; verified by dry-running the command against a synthetic fixture file conforming to the dispatch log frontmatter shape, asserting exit 0 and the six keys).
- [ ] Pre-flight audit recorded in this ticket's Implementation notes: list every file under `argos/specs/v1.0/tickets/` that contained `import yaml` before the retrofit, the AC number per file, and whether the retrofit was applied.
- [ ] No file under `.claude/agents/`, `argos/specs/v1.0/agents/`, `argos/cli/`, `argos/specs/v1.0/schemas/`, or any directory other than `argos/specs/v1.0/tickets/` is modified by this ticket.
- [ ] `git diff --stat main..HEAD -- 'argos/specs/v1.0/tickets/'` shows changes only to ticket files containing the retrofit; no other directories.

## Depends on

- ARG1-060 (`argos frontmatter-parse` subcommand) — the AC text invokes it; cannot retrofit before the subcommand exists.
- ADR-002 — the rationale.

## Touches

- `argos/specs/v1.0/tickets/ARG1-010-orchestrator-agent-definition.md` (modify — AC#3 only)
- `argos/specs/v1.0/tickets/ARG1-012-dispatch-log-writer.md` (modify — AC#1 only)
- _any other v1.0 ticket file the audit step finds containing `import yaml` (modify — affected AC only)_

## Parallelizable with

_none — sequenced after ARG1-060, sequenced before any Layer 2 ticket (ARG1-020, ARG1-031, ARG1-041) is dispatched, so Layer 2 tickets cannot copy the old `import yaml` pattern by reading shipped neighbors._

## Out of scope

- Adding new ACs to ARG1-010 or ARG1-012 (this is a rewrite of existing ACs, not an extension).
- Modifying any frontmatter that the retrofitted ACs validate. If `argos frontmatter-parse` cannot parse `.claude/agents/orchestrator.md` or `argos/specs/v1.0/agents/orchestrator.md`, the fix per ADR-002 §5 is to adjust the *frontmatter*, not the parser — but that adjustment is a separate ticket, not this one. This ticket assumes the existing frontmatter conforms (informally verified during ADR-002 drafting; ARG1-060's AC#2 / AC#3 verify formally).
- Changes to legacy tickets under `argos/specs/tickets/`. v0.5 surface, out of scope.
- Updates to agent prompts to mention `frontmatter-parse`. Agents read schemas and ADRs, not ticket ACs.
