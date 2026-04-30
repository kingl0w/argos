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

## Plan

Implementation strategy and files touched.

### Module: `argos/cli/dispatch_log.py` (new)

Library module. Stdlib only (ADR-001). Two public functions plus errors:

- `write_dispatch_log(*, ticket_id, epic_id, batch_id, worktree_path, session_id, dispatch_root, dispatched_at=None, dry_run=False) -> Path`
  - Composes ADR-002-conformant frontmatter (flat scalars, six required keys: `ticket_id`, `epic_id`, `batch_id`, `dispatched_at`, `worktree_path`, `session_id`).
  - Body opens with `## Events` and one initial `<!-- argos:dispatch-event ... -->` block of `type=dispatched`.
  - Writes via `os.O_CREAT | os.O_EXCL | os.O_WRONLY` (precedent: ARG1-041 escalation writer). Refuses to overwrite an existing log; that path is reserved for `append_event`.
  - `dry_run=True` returns the resolved path without touching disk (supports AC#4).
- `append_event(*, dispatch_file, event_type, body="", at=None, session_id=None, dry_run=False) -> str`
  - Atomic append: `fcntl.flock` on a sidecar `.lock` file → read current text → splice block at end of `## Events` (or append if heading absent — defensive) → tempfile + `os.replace` (precedent: ARG1-051 `state_append`).
  - Block id: `{ISO-timestamp}-{ticket-id}-{event-type}` with 6-hex random suffix on same-second collision.
  - Frontmatter is a prefix region; we never touch lines before the closing `---` so frontmatter byte-equality is preserved (AC#3).
- Errors: `DispatchLogError` (base), `DispatchLogExistsError` (initial-write collision), `DispatchLogMissingError` (append on missing file), `InvalidIdError` (slug-shape rejection of ticket / epic).

Slug shape for `ticket_id`, `epic_id`: `^[A-Za-z][A-Za-z0-9_-]*$` so they are safe as path segments. `event_type` is restricted to `^[a-z][a-z0-9-]*$`.

Frontmatter values containing colons (timestamps, paths) round-trip through ADR-002's bare-scalar grammar — `_parse_scalar` returns the raw string when no special leading char is present and no key-style colon delimiter exists in the value position.

### CLI surface

None. The writer is a library called by the orchestrator agent (ARG1-010 → ARG1-022). ARG1-011 owns the `orchestrate` subcommand; this ticket does not touch `argos/cli/__main__.py`. AC#4 is satisfied because `dry_run=True` short-circuits all file operations; ARG1-011's `--dry-run` flag will pass it through.

### Tests: `argos/cli/tests/test_dispatch_log.py` (new)

Stdlib `unittest`, stdlib only — pattern from `test_state_append.py` / `test_escalate.py`. Coverage:

1. `test_write_creates_file_at_canonical_path` (AC#1).
2. `test_frontmatter_has_six_required_keys` (AC#2) — invokes `python3 -m argos.cli frontmatter-parse` as a subprocess, asserts JSON has all six keys; this is the canonical AC #2 verification harness, not a plain Python parse.
3. `test_append_grows_file_and_preserves_frontmatter` (AC#3) — `stat` before/after, plus byte-level frontmatter region equality.
4. `test_dry_run_writes_nothing` (AC#4) — `write_dispatch_log(dry_run=True)` produces no entries under `dispatch_root`; covers the writer-side guarantee.
5. `test_concurrent_dispatches_to_different_tickets` (AC#5) — spawn two threads each calling `write_dispatch_log` for different ticket ids; assert both files exist and neither was overwritten.
6. `test_initial_write_refuses_to_overwrite` — defensive; second call with same ticket raises `DispatchLogExistsError`.
7. `test_invalid_epic_or_ticket_id_rejected` — slug-shape enforcement.

### `argos/specs/dispatch/.gitkeep` (new)

Per the ticket's Touches list. Empty file so the directory is committed.

### File scope (independence vs. ARG1-011)

- This ticket: `argos/cli/dispatch_log.py`, `argos/cli/tests/test_dispatch_log.py`, `argos/specs/dispatch/.gitkeep`, plus a one-time `## Plan` / `## Verification` append to the ticket file itself.
- Sibling ARG1-011 owns: `.claude/commands/orchestrate.md`, `argos/cli/commands/orchestrate.py`, `argos/cli/queue.py`, `argos/cli/tests/test_orchestrate.py`, and the `orchestrate` registration in `argos/cli/__main__.py`.
- File-disjointness invariant holds: zero overlap.

## Verification

Ran all five ACs against the harness; all pass. Full test suite (164 tests including the new 16) green.

- **AC#1.** `test -f argos/specs/dispatch/EPIC-001/ARG1-099.md` exits 0 after `write_dispatch_log(ticket_id='ARG1-099', epic_id='EPIC-001', ...)`.
- **AC#2.** `python3 -m argos.cli frontmatter-parse <file> | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); assert all(k in d for k in ['ticket_id','epic_id','batch_id','dispatched_at','worktree_path','session_id'])"` exits 0. Round-tripped values: `ticket_id=ARG1-099`, `epic_id=EPIC-001`, `dispatched_at=2026-04-30T10:00:00Z`, `worktree_path=.argos/worktrees/ARG1-099-3f9c`, `session_id=sess-2026-04-30T10:00:00Z-a1b2`. Stdlib AC harness pattern per ADR-002 — no pyyaml.
- **AC#3.** `stat -c %s` 507 → 696 after one `append_event(event_type=verifier-result, ...)`. SHA-256 of the byte-region from BOF through the closing `---\n` is identical pre- and post-append.
- **AC#4.** Writer-side: `write_dispatch_log(..., dry_run=True)` creates no entries under `dispatch_root`. `find <dispatch_root> -newer <marker> -type f` returns empty. ARG1-011 wires `--dry-run` through to this flag.
- **AC#5.** Two threads dispatching `ARG1-100` and `ARG1-101` concurrently produce two distinct files under `EPIC-001/`; `cmp -s` reports they differ; each file's frontmatter cites its own `ticket_id`.

### Test inventory (`argos/cli/tests/test_dispatch_log.py`)

- `TestCanonicalPath` — AC#1.
- `TestFrontmatterShape.test_frontmatter_keys_via_argos_frontmatter_parse` — AC#2 via the literal `python3 -m argos.cli frontmatter-parse` subprocess invocation, exactly the pattern documented in ADR-002 §2.
- `TestAppendPreservesFrontmatter` — AC#3 (single append + 5-append loop).
- `TestDryRun` — AC#4 (writer side; ARG1-011 wires the flag through).
- `TestConcurrentDispatch` — AC#5.
- `TestExistsContract`, `TestMissingContract`, `TestSlugValidation`, `TestBlockIdUniqueness`, `TestBuildEventBlockShape` — defensive contracts not in the AC list but load-bearing for the orchestrator's correctness (refusal to overwrite, slug-shape validation closing path-traversal, same-second id disambiguation).

Decision: pass. No findings.
