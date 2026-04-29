# ARG1-012 — Orchestrator dispatch log writer

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P1
**Epic:** 2 (Orchestrator)

## Intent

Implement the dispatch log: every orchestrator decision (which tickets were considered, which were dispatched in this batch, which were deferred and why, parallel batch ID, timestamps) gets written to `argos/specs/dispatch/{epic-id}/{ticket-id}.md`. Markdown-first per ARCHITECTURE.md §Constraints. The orchestrator writes one file per dispatched ticket; updates to that file are append-only.

## Context

ARCHITECTURE.md §Components/Orchestrator names dispatch logs as part of the orchestrator's owned output. Without persistent dispatch logs, post-hoc inspection of "what did the orchestrator decide and why" is impossible — that violates the markdown-first inspectability constraint.

## Non-goals

- No log rotation or archival (cycle close handles its own data; dispatch logs are persistent until manually pruned).
- No structured-query API (logs are markdown for human reading; tooling can grep them).
- No retroactive backfill of dispatch logs for tickets dispatched before this ticket landed.

## Acceptance criteria

- [ ] After a successful dispatch of ticket `ARG1-099` in epic `EPIC-001`, `test -f argos/specs/dispatch/EPIC-001/ARG1-099.md` exits 0.
- [ ] The dispatch log file frontmatter contains required keys `ticket_id`, `epic_id`, `batch_id`, `dispatched_at`, `worktree_path`, `session_id`; verified by `python3 -m argos.cli frontmatter-parse argos/specs/dispatch/EPIC-001/ARG1-099.md | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); assert all(k in d for k in ['ticket_id','epic_id','batch_id','dispatched_at','worktree_path','session_id'])"` exiting 0. _(Retrofitted from a pyyaml-based check per ADR-002; ARG1-059.)_
- [ ] After a second event on the same ticket (e.g., verifier result), the file size strictly increases (`stat -c %s argos/specs/dispatch/EPIC-001/ARG1-099.md` returns a larger number than before); the original frontmatter is unchanged.
- [ ] `argos orchestrate --dry-run` writes nothing to `argos/specs/dispatch/` (verified by `find argos/specs/dispatch -newer /tmp/before-marker` returning empty).
- [ ] Two concurrent dispatches to different tickets produce two separate files; no file is overwritten.

## Depends on

- ARG1-010 (orchestrator agent — emits the events)

## Touches

- `argos/cli/dispatch.py` (or equivalent — new)
- `argos/specs/dispatch/.gitkeep` (new)
- `argos/cli/tests/test_dispatch_log.py` (or equivalent)

## Parallelizable with

- ARG1-003 (status)
- ARG1-011 (orchestrate slash command — different module)
- ARG1-020 (worktree spawn)
- ARG1-031 (verifier structured decision)
- ARG1-041 (escalation writer)
- ARG1-051 (state-append helper)
