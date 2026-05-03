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

## Plan

files_touched:
  - argos/cli/orchestrator/retry.py
  - argos/cli/orchestrator/dispatch.py
  - argos/cli/commands/orchestrate.py
  - argos/cli/tests/test_retry.py
  - argos/specs/v1.0/agents/orchestrator.md
  - .claude/agents/orchestrator.md
  - argos/specs/v1.0/tickets/ARG1-013-orchestrator-auto-fix-retry.md

### Architectural choices

**Q1 — Retry trigger.** The retry fires iff the latest
`<!-- argos:verifier-output -->` block in the worktree's ticket file
parses with `decision: fail`. Per the verifier-output schema, `fail`
already encompasses {≥1 critical finding, ≥1 major finding,
`tests_ran: false`}; piggy-backing on the literal keeps the criterion
in one place rather than re-classifying findings in the orchestrator.
`pass` and `pass-with-minors` never retry. A subprocess returncode != 0
with **no parseable verifier-output** is **not** auto-escalated —
that's a different failure surface (harness crash, missing verifier
phase) and is ARG1-023's concern, not retry's.

**Q2 — Retry budget.** Hard cap 1, configurable enabled/disabled only,
per ARCHITECTURE.md §Invariants and this ticket's Non-goals. Mapping:

- `verifier.auto_fix_retries == 0` → no retry; first `decision: fail`
  produces a blocking escalation immediately (AC#5).
- `verifier.auto_fix_retries >= 1` → exactly one retry; if the retry
  also fails, write a single blocking escalation. No third attempt
  ever, regardless of config value.

The default in `argos/config.toml.template` (`= 0`) is preserved —
this ticket does not change the shipped default. Operators opt in by
setting the value to 1.

**Q3 — Retry input.** The retry re-spawns the harness in the **same
worktree** the first attempt used (orchestrator agent §Auto-fix retry
behavior). The harness picks up the partial state on disk: the prior
`## Plan`, the planner's notes, the prior `<!-- argos:verifier-output -->`
block. The orchestrator does not synthesize an additional prompt or
inject failure context — the structured failure record is already in
the worktree files where the planner can read it.

The first attempt goes through `argos run-session` (which creates the
worktree). The retry attempt **bypasses run-session** because run-session
refuses to reuse an existing worktree. Instead, the retry runner calls
`worktree.spawn_session` directly against the existing path. This keeps
ARG1-020's run-session contract untouched and avoids touching ARG1-023's
post-dispatch merge logic.

### Module surface

`argos/cli/orchestrator/retry.py` (new):

- `RetryConfig` — `enabled`, `escalation_dir`, `ticket_dir_in_worktree`.
- `read_decision(worktree, ticket_id, ticket_dir)` — find the ticket
  file, parse the LAST verifier-output block, return its `decision`
  literal or `None`.
- `compose_retry_session_id(original)` — `<original>-retry-1`.
- `write_retry_event(...)` — append `EVENT_RETRY` to the dispatch log
  via ARG1-012's writer.
- `write_retry_failed_escalation(...)` — call ARG1-041's
  `escalation.write_escalation` with `raised_by: orchestrator`,
  `severity: blocking`, and the four required H2 sections.
- `default_retry_runner(req)` — production retry runner;
  resolves the harness binary and calls `worktree.spawn_session`
  against `req.worktree_path`.
- `maybe_retry(req, initial_returncode, dispatch_file, config,
  retry_runner)` — the decision function. Reads decision; if `fail`
  and disabled, escalates; if `fail` and enabled, runs retry, re-reads
  decision, escalates if still failed. Returns `(final_returncode,
  final_decision)`.

`argos/cli/orchestrator/dispatch.py` (modify):

- `dispatch_batch` accepts new keyword args: `auto_fix_retries: int = 0`,
  `retry_runner: SessionRunner | None = None`,
  `escalation_dir: Path | None = None`,
  `ticket_dir_in_worktree: str | None = None`.
- `_run_one_session` calls `retry.maybe_retry` after the inner runner
  returns and uses the returned `(final_rc, final_decision)` when
  composing the `verifier-result` event body. The body grows a
  `- decision: <literal>` line when a decision was readable.

`argos/cli/commands/orchestrate.py` (modify):

- New `--auto-fix-retries` int flag (default: read from config).
- New `_resolve_auto_fix_retries(override)` mirrors
  `_resolve_max_parallel`: explicit flag → `verifier.auto_fix_retries`
  → 0 fallback.
- The resolved value is passed through to `dispatch_batch`.

### Files NOT touched (scope guard)

- `argos/cli/commands/run_session.py` and `argos/cli/worktree.py` are
  read-only; the retry runner composes them, never modifies them.
- `argos/cli/dispatch_log.py` is read-only; `EVENT_RETRY` is already
  exported.
- `argos/cli/escalation.py` and `argos/cli/escalation_validator.py` are
  read-only; the escalation writer is reused as-is.
- ARG1-023's worktree merge / preserve logic — out of scope.
- `argos/specs/v1.0/STATE.md` — verifier-only writes; the orchestrator
  retry path never touches STATE.md (per orchestrator agent §Auto-fix
  retry: "the verifier inside the session is still the sole STATE.md
  writer").
- `argos/config.toml.template` — the existing default of `0` is
  preserved; the ticket spec is silent on changing it.
- `argos/cli/_config_schema.py` and `argos/specs/v1.0/schemas/config.md`
  — `verifier.auto_fix_retries: int` is already declared.

### Risks

- **Verifier-output absent.** A session that crashes before reaching
  the verifier leaves no block. `read_decision` returns `None`;
  `maybe_retry` treats it as "no decision" and does not retry or
  escalate. The subprocess returncode propagates through the dispatch
  log untouched. This is the conservative choice and matches the
  orchestrator's contract (it only acts on verifier signals).
- **Schema doc references this ticket for `verifier.minor_lint_rules`
  array support.** That reference is wrong-scope: the ticket text and
  Touches list cover retry only. Array support stays open as an
  unscoped follow-up; this ticket does not silently expand into
  config-parser territory.
- **Worktree reuse on retry.** If the harness left the worktree in a
  half-edited state (uncommitted changes), the retry inherits it. That
  is by design — the partial state is "informative for the retry" per
  the orchestrator agent definition.

### Verification

- `argos lint-imports argos/` exits 0 (stdlib-only mandate per ADR-001
  + ADR-002 §1).
- `python3 -m unittest argos.cli.tests.test_retry -v` exits 0 with
  every AC covered.
- `python3 -m unittest argos.cli.tests.test_parallel_dispatch -v` still
  exits 0 (no regression in ARG1-022).
