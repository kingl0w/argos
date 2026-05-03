# ARG1-022 — Parallel dispatch with `max_parallel` cap and serial fallback

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 3 (Parallel session manager)

## Intent

The orchestrator's main dispatch loop. Read the next batch from the queue, run independence detection (ARG1-021), partition into independence groups, dispatch up to `max_parallel` (from `argos/config.toml`) sessions in the largest group concurrently using `argos run-session` (ARG1-020). Wait for all to finish, collect results, advance to the next group. If independence detection fails or returns an error, fall back to strict serial dispatch (degraded but correct, per ARCHITECTURE.md §Invariants).

## Context

ARCHITECTURE.md §Components/Parallel Session Manager specifies `max_parallel` (default 3), serial fallback, and per-group barrier semantics. This is the ticket where PRD success criterion #4 (≥2x parallel speedup) is delivered.

## Non-goals

- No dynamic resizing of `max_parallel` mid-run.
- No work-stealing across groups (a finished group does not pull from the next group early).
- No cross-batch parallelism (orchestrator processes one batch at a time).
- Worktree merge is delegated to ARG1-023.

## Acceptance criteria

- [ ] With three synthetic independent tickets and `max_parallel = 3`, `argos orchestrate --batch-size 3` produces three concurrent sessions; verified by three running `claude` processes overlapping in time (`ps -ef | grep claude | wc -l ≥ 3` at peak), captured by a wrapper test script.
- [ ] With `max_parallel = 1`, the same three tickets run serially; total wall-clock is ≥ sum of individual session durations × 0.95 (no parallelism).
- [ ] With three tickets where two share a file in `files_touched`, the orchestrator dispatches the two dependent ones serially and the third one in parallel with the first of the two; verified by the dispatch log timestamps.
- [ ] When ARG1-021 returns an error (e.g., a ticket missing `files_touched:`), the orchestrator falls back to strict serial dispatch and stdout contains `independence detection failed; falling back to serial`.
- [ ] After a parallel batch completes, no orphaned worktrees: `git worktree list | wc -l` equals the count after subtracting expected merged-but-preserved worktrees from ARG1-023.
- [ ] `argos orchestrate --batch-size 5 --dry-run` emits a markdown table on stdout with columns `ticket_id | group | dispatch_order | parallel_with`.

## Depends on

- ARG1-020 (worktree spawn)
- ARG1-021 (independence detection)
- ARG1-053 (config split — reads `orchestrator.max_parallel`)

## Touches

- `argos/cli/orchestrator/dispatch.py` (or equivalent — new)
- `argos/cli/tests/test_parallel_dispatch.py` (or equivalent)

## Parallelizable with

- ARG1-003 (status)
- ARG1-004 (sync)
- ARG1-005 (attend)
- ARG1-012 (dispatch log writer — different module)
- ARG1-023 (worktree merge — different module)
- ARG1-031 (verifier structured decision)
- ARG1-041 (escalation writer)

## Plan

files_touched:
  - argos/cli/orchestrator/dispatch.py
  - argos/cli/commands/orchestrate.py
  - argos/cli/tests/test_parallel_dispatch.py
  - argos/cli/tests/test_orchestrate.py
  - argos/specs/v1.0/tickets/ARG1-022-parallel-dispatch.md

### Architectural choices (from session brief, locked here)

1. **Concurrency model — subprocess-managed.** The dispatcher waits on
   each per-ticket subprocess (`argos run-session ...`) inside a
   `threading.Thread` worker, slotted under a `threading.Semaphore` of
   size `max_parallel`. The orchestrator collects per-session
   exit codes and timestamps before returning. Required by AC#1
   (overlapping `claude` PIDs visible to `ps -ef`), AC#2 (wall-clock
   bound), AC#3 (dispatch-log timestamp ordering), and the orchestrator
   agent doc's §Parallel dispatch ("Wait for all to finish, collect
   results, advance to the next group"). Using `threading` + manual
   `Semaphore` rather than `concurrent.futures` because `concurrent` is
   not in the lint-imports allowlist (ARG1-064); `threading` and `os`
   are.
2. **Partial-batch failure — option (a) (peers continue).** A
   non-zero exit from one session's `run-session` does not affect
   other in-flight sessions in the same group; each outcome is logged
   independently in the dispatch log. Auto-fix retry is ARG1-013's
   territory; this ticket does not signal-kill or re-dispatch.
   Justified by orchestrator-agent doc §Parallel dispatch behavior.
3. **Pre-commit hook (ARG1-032) — no interaction.** Dispatcher writes
   only to `argos/specs/dispatch/{epic-id}/{ticket-id}.md` via ARG1-012
   (`write_dispatch_log` / `append_event`). The hook gates STATE.md
   only. Not bypassed; `ARGOS_CYCLE_CLOSE=1` reserved for ARG1-054.
4. **Group granularity — one group at a time, hard barrier.** Spec is
   explicit ("Wait for all to finish, collect results, advance to the
   next group"). Within a group, `max_parallel` is a slot pool — a
   group of K with `max_parallel = M` runs M-at-a-time but does not
   spill into the next group until all K complete. No cross-group
   pipelining. Matches Non-goals: "No work-stealing across groups."
5. **Strict criterion — no workarounds.** Dispatch consumes
   `independence.partition()` verbatim. False-serializations under
   strict (e.g. shared `argos/cli/__main__.py`) are accepted per
   ESC-ARG1-021 and are ARG1-066's scope, not ours.

### Module shape

`argos/cli/orchestrator/dispatch.py` exposes the library:

- `DispatchEntry` (frozen dataclass): `ticket_id`, `group` (1-indexed),
  `dispatch_order` (1-indexed within group), `parallel_with` (tuple of
  other ticket ids in the same group).
- `DispatchPlan` (frozen dataclass): `entries` tuple +
  `serial_fallback: bool`.
- `SessionOutcome` (frozen dataclass): `ticket_id`, `worktree_path`,
  `branch`, `returncode`, `started_at`, `finished_at`.
- `BatchResult` (frozen dataclass): `plan`, `outcomes`.
- `plan_dispatch(ticket_ids, *, ticket_dir)` — runs
  `independence.load_ticket` + `independence.partition`. On any
  `IndependenceError`, returns a plan with each ticket in its own
  group and `serial_fallback=True`.
- `render_dry_run_table(plan) -> str` — renders the AC#6 markdown
  table.
- `dispatch_batch(ticket_ids, *, epic_id, batch_id, max_parallel,
  repo_root, dispatch_root, ticket_dir, base_sha=None, info_stream,
  session_runner=None) -> BatchResult` — the actual dispatcher. The
  `session_runner` callable is the test seam; production default
  spawns `python3 -m argos.cli run-session` as a subprocess.

`argos/cli/commands/orchestrate.py` upgrades:

- `--dry-run` (existing) gains a markdown-table mode: when every queued
  ticket loads cleanly with a `files_touched:` Plan section, emits the
  AC#6 table; otherwise (the ARG1-011 test scenario) falls back to
  one-id-per-line output, preserving ARG1-011's existing tests modulo
  the ones explicitly slated to flip.
- Without `--dry-run`, real dispatch is wired: read queue → call
  `dispatch_batch` → exit 0 if all sessions returned 0, exit 1
  otherwise. Requires `--epic` flag.
- Reads `orchestrator.max_parallel` from `argos.cli.config.load()`,
  defaulting to 3 when the config loader is unavailable (matches the
  schema's documented default).

### Test plan

`argos/cli/tests/test_parallel_dispatch.py`:

- `PlanDispatchTests` — `plan_dispatch` returns expected `DispatchPlan`
  for: three independent tickets (one group of 3), two-share-one-disjoint
  (two groups), missing-Plan-section (`serial_fallback=True`).
- `RenderTableTests` — `render_dry_run_table` produces the canonical
  markdown table with the four required columns in order.
- `DispatchBatchTests` — uses an injected `session_runner` stub that
  records start/finish timestamps and sleeps a configurable duration:
  - `max_parallel=3` with three independent tickets: peak concurrency
    observed equals 3.
  - `max_parallel=1` with three independent tickets: total wall-clock
    ≥ 0.95 × sum of individual durations.
  - dependent pair + one independent: dispatch-log timestamps show the
    dependent two are serialized; the independent one overlaps with
    the first dependent.
  - `IndependenceError`-raising stub for `plan_dispatch`: dispatcher
    writes `independence detection failed; falling back to serial` to
    `info_stream`, then dispatches one-at-a-time.
  - After dispatch, no extra `git worktree list` entries beyond those
    matching dispatched ticket ids (AC#5).
- `WrapperHarnessTests` — invokes the CLI in a tmp git repo with three
  synthetic tickets and a fake `ARGOS_RUN_SESSION_HARNESS_BIN` script
  that sleeps + writes a marker file; samples `ps -ef | grep claude`
  during dispatch and asserts ≥ 3 concurrent. Skipped on platforms
  without `ps` (Windows safety; argos targets POSIX).
- `OrchestrateDryRunTableTests` — extends `test_orchestrate.py`: with
  three real ticket files + Plan sections in tmp ticket-dir, dry-run
  output contains the canonical table header and one row per ticket.

`argos/cli/tests/test_orchestrate.py`:

- Update `test_no_dry_run_rejected` to expect non-zero exit when
  `--epic` is missing (the new failure mode), preserving the original
  intent that bare `argos orchestrate` without flags is a misuse.
- All other existing tests pass unchanged because they use queue
  fixtures whose ticket ids are never resolved on disk → fallback to
  one-id-per-line output kicks in.

### What is NOT in scope

- Auto-fix retry (ARG1-013).
- Worktree merge / preserve / cleanup (ARG1-023).
- Cycle close (ARG1-054).
- ARG1-066's dry-run-merge independence relaxation.
- Webhook firing on session completion.
- Streaming progress; orchestrator polls future completion in-thread.

## Verification

**Branch:** `ticket/ARG1-022` (worktree `argos-v1-arg1-022`).
**Author:** verifier.
**Stdlib-only:** preserved — `argos lint-imports argos/` exits 0.

ACs: 6/6 met.

- **AC#1** (three concurrent `claude` PIDs at peak under
  `max_parallel = 3`). Live harness in a tmp git repo: three
  synthetic tickets with disjoint `files_touched:`, fake
  `claude` binary that sleeps 1.5s, the AC's `ps` poll loop
  sampling at 50 ms while orchestrate runs.

  ```text
  orchestrate exit=0, peak concurrent claude PIDs=3
  ```

  Same condition reproduced under unittest in
  `WrapperHarnessProcessOverlapTests.test_three_concurrent_claude_processes_at_peak`
  (live `ps -eo pid,command` poll asserting peak ≥ 3).

- **AC#2** (`max_parallel = 1` wall-clock ≥ 0.95 × Σ durations).
  Live harness, fake `claude` sleeps 1.0s × 3 tickets,
  `max_parallel = 1`:

  ```text
  wall=3.13613s; threshold (3 * 1 * 0.95) = 2.85s
  ```

  3.136 ≥ 2.85 ⇒ pass. Reproduced under unittest in
  `DispatchBatchTests.test_max_parallel_1_serializes`.

- **AC#3** (dependent pair serialized; independent overlaps with
  first dependent — verified by dispatch-log timestamps). Live
  harness with three tickets, ARG1-911 and ARG1-912 sharing
  `argos/cli/shared.py`, ARG1-913 disjoint:

  ```text
  ARG1-911 dispatched at=2026-05-03T17:22:42Z, verifier-result at=2026-05-03T17:22:43Z
  ARG1-913 dispatched at=2026-05-03T17:22:42Z, verifier-result at=2026-05-03T17:22:43Z
  ARG1-912 dispatched at=2026-05-03T17:22:43Z, verifier-result at=2026-05-03T17:22:44Z
  ```

  ARG1-911 and ARG1-913 dispatched at the same timestamp (group
  1, parallel — they don't share files); ARG1-912's dispatch
  timestamp (17:22:43) is the same second ARG1-911's
  verifier-result was written ⇒ ARG1-912 only started after the
  group barrier closed. Dependent pair (911, 912) is serialized;
  independent (913) overlaps with the first dependent (911).
  Reproduced under unittest in
  `DispatchBatchTests.test_dependent_pair_serialized_independent_overlaps`.

- **AC#4** (serial fallback diagnostic on independence error).
  Live harness with one ticket whose Plan section is missing
  `files_touched:`:

  ```text
  independence detection failed; falling back to serial
  exit=0
  ```

  The literal string `independence detection failed; falling back
  to serial` is present on stdout. Pin source:
  `dispatch.SERIAL_FALLBACK_MESSAGE`. Reproduced under unittest
  in `DispatchBatchTests.test_independence_failure_falls_back_to_serial`
  and `OrchestrateRealDispatchTests.test_real_dispatch_serial_fallback_message_on_missing_plan`.

- **AC#5** (no orphaned worktrees beyond ARG1-023's expected
  set). Live harness after AC#1 dispatch:

  ```text
  /tmp/tmp.TMGEmhLvpA                                    089e08f [main]
  /tmp/tmp.TMGEmhLvpA/.argos/worktrees/ARG1-901-089e08f  089e08f [argos/ARG1-901]
  /tmp/tmp.TMGEmhLvpA/.argos/worktrees/ARG1-902-089e08f  089e08f [argos/ARG1-902]
  /tmp/tmp.TMGEmhLvpA/.argos/worktrees/ARG1-903-089e08f  089e08f [argos/ARG1-903]
  worktree count: 4
  ```

  4 worktrees = 1 (main checkout) + 3 (one per dispatched
  ticket); no orphans. ARG1-023 has not shipped, so no
  merged-but-preserved subtraction is required at this point.
  Reproduced under unittest in
  `OrchestrateRealDispatchTests.test_real_dispatch_three_independent_returns_zero`.

- **AC#6** (`argos orchestrate --batch-size 5 --dry-run` emits a
  markdown table with the four named columns). Live harness:

  ```text
  | ticket_id | group | dispatch_order | parallel_with |
  |-----------|-------|----------------|---------------|
  | ARG1-901 | 1 | 1 | ARG1-902, ARG1-903 |
  | ARG1-902 | 1 | 2 | ARG1-901, ARG1-903 |
  | ARG1-903 | 1 | 3 | ARG1-901, ARG1-902 |
  ```

  Header columns appear in the canonical order (`ticket_id` <
  `group` < `dispatch_order` < `parallel_with`); one body row per
  queued ticket. Reproduced under unittest in
  `OrchestrateDryRunTableTests.test_dry_run_emits_markdown_table`.

Findings: 0 critical, 0 major, 0 minor.

**Tests.**
`python3 -m unittest argos.cli.tests.test_parallel_dispatch -v` →
**Ran 19 tests in 4.114s, OK**. New file
`argos/cli/tests/test_parallel_dispatch.py` covers:
`PlanDispatchTests` (4), `RenderTableTests` (2),
`DispatchBatchTests` (7), `OrchestrateDryRunTableTests` (2),
`OrchestrateRealDispatchTests` (3),
`WrapperHarnessProcessOverlapTests` (1; gated on POSIX `ps`).

Full sweep: `python3 -m unittest discover -s argos/cli/tests` →
**Ran 248 tests in 9.670s, OK**. No regressions in
`test_orchestrate.py` (the one prior placeholder test
`test_no_dry_run_rejected` was renamed to
`test_no_dry_run_without_epic_rejected` to match the new
`--epic` requirement; all 18 tests in that file pass).

Pre-flight: `python3 -m argos.cli lint-imports argos/` → exit 0.
ADR-001 stdlib-only contract preserved (only new top-level
imports introduced are `subprocess`, `threading`, and `os`, all
in the ARG1-064 allowlist).

**Architectural choices locked (per session brief Q1–Q5).**

1. **Concurrency model — subprocess-managed.** One
   `threading.Thread` per ticket, slotted under
   `threading.Semaphore(max_parallel)`; each worker blocks on the
   `argos run-session` subprocess. `concurrent.futures` would
   have been cleaner but is not in the ARG1-064 lint-imports
   allowlist; `threading` is. Required by AC#1 (overlapping PIDs
   visible to `ps`), AC#2 (wall-clock bound), AC#3 (dispatch-log
   timestamp ordering).
2. **Partial-batch failure — peers continue (option a).** A
   non-zero exit from one session does not affect siblings. Each
   outcome is logged independently in the dispatch log; ARG1-013
   reads those logs to drive auto-fix retry. Verified by
   `DispatchBatchTests.test_partial_failure_does_not_kill_peers`.
3. **Pre-commit hook (ARG1-032) — no interaction.** Dispatcher
   writes only to `argos/specs/dispatch/{epic}/{ticket}.md` via
   ARG1-012's writer, never to STATE.md. Hook gates STATE.md
   only.
4. **Group granularity — one group at a time, hard barrier.**
   Spec is explicit ("Wait for all to finish, collect results,
   advance to the next group"). Within a group, `max_parallel`
   is a slot pool. No cross-group pipelining (matches
   Non-goals).
5. **Strict criterion — no workarounds.** `independence.partition`
   consumed verbatim. False-serializations under strict are
   ARG1-066's scope, not ours.

No escalations filed.

Decision: **pass**.
