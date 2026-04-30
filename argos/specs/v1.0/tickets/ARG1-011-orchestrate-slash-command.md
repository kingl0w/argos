# ARG1-011 — `/orchestrate` slash command + queue read entry point

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 2 (Orchestrator)

## Intent

Wire up the `/orchestrate` slash command: register it in `.claude/commands/`, point it at the orchestrator agent (ARG1-010), and provide the entry-point logic that reads STATE.md's Queue section and returns the next batch of ticket IDs to dispatch. No actual dispatch yet — that is ARG1-022. This ticket proves the orchestrator can be invoked from the harness and read the queue.

## Context

ARCHITECTURE.md §System shape places the orchestrator at the top of the dispatch chain, invoked by the operator. PRD §Distribution does not list `/orchestrate` as a CLI command; it is a Claude Code slash command (consistent with v0.5 `/next`, `/steer`, `/ask`).

## Non-goals

- No parallel dispatch (ARG1-022).
- No worktree creation (ARG1-020).
- No independence analysis (ARG1-021).
- No escalation production (ARG1-041).

## Acceptance criteria

- [ ] `test -f .claude/commands/orchestrate.md` exits 0.
- [ ] `argos orchestrate --dry-run` exits 0 and stdout lists the next 1–N ticket IDs from STATE.md's Queue section in order.
- [ ] When STATE.md's Queue section is empty, `argos orchestrate --dry-run; echo $?` prints `0` and stdout contains `queue empty`.
- [ ] When STATE.md is missing, `argos orchestrate --dry-run; echo $?` prints a non-zero number and stderr contains `STATE.md not found`.
- [ ] `grep -F 'orchestrator' .claude/commands/orchestrate.md` exits 0 (slash command references the agent).
- [ ] `argos orchestrate --dry-run --batch-size 2` returns at most 2 ticket IDs.

## Depends on

- ARG1-010 (orchestrator agent — slash command targets it)

## Touches

- `.claude/commands/orchestrate.md` (new)
- `argos/cli/commands/orchestrate.py` (or equivalent — new)
- `argos/cli/queue.py` (or equivalent — Queue-section parser)
- `argos/cli/tests/test_orchestrate.py` (or equivalent)

## Parallelizable with

- ARG1-003 (status)
- ARG1-005 (attend)
- ARG1-012 (dispatch log writer — different module)
- ARG1-020 (worktree spawn)
- ARG1-031 (verifier structured decision — verifier file)
- ARG1-041 (escalation writer)

## Plan

Two surfaces ship together: the Claude Code slash command (markdown only,
no code) and the `argos orchestrate` CLI subcommand that the slash command
hands off to.

**Files:**

- `.claude/commands/orchestrate.md` (new) — slash command body. Frontmatter
  follows the v0.5 precedent (`description:` + `argument-hint:`). Body
  describes the orchestrator handoff and references the agent
  (`.claude/agents/orchestrator.md`) for the full contract. References
  `argos orchestrate --dry-run`, `argos run-session`,
  `argos verifier-writeback`, `argos escalate`, `argos state-append` as
  the orchestrator's tool surface.
- `argos/specs/v1.0/commands/orchestrate.md` (new) — byte-identical
  canonical mirror, following the `.claude/agents/<name>.md` +
  `argos/specs/v1.0/agents/<name>.md` mirror pattern that ARG1-010 / ARG1-030
  established. Verified by a unit test.
- `argos/cli/queue.py` (new) — stdlib-only `## Queue` section parser.
  `parse_queue(text) -> list[str]` finds the heading, walks bullets until
  the next `## ` heading, and extracts the leading whitespace-delimited
  token from each bullet body iff it matches `TICKET_ID_RE` (`^[A-Z]+\d*-\d+$`).
  Raises `QueueSectionMissingError` when the heading is absent (distinct
  from "queue empty" which is a successful empty list).
  `parse_queue_file(path)` adds the file-not-found path with a
  `StateFileNotFoundError` whose message contains `STATE.md not found`
  (the AC#4 contract substring).
- `argos/cli/commands/orchestrate.py` (new) — argparse shim. `--dry-run`
  is the only mode wired in v1.0 (real dispatch is ARG1-022); invocation
  without `--dry-run` exits 2 with a stderr message referencing
  ARG1-022. `--batch-size N` caps the printed list (slice on the parsed
  ids); `N < 1` exits 2. `--state-file PATH` defaults to
  `argos/specs/v1.0/STATE.md` (matches `state-append` precedent).
- `argos/cli/__main__.py` (modify, narrow) — register `orchestrate` in
  `PUBLIC_SUBCOMMANDS`, add the `--help` line, add the dispatch branch.
  Three localized edits, "keep both registrations" merge pattern. Sibling
  ARG1-012's `Touches` does not include `__main__.py`, so no actual
  conflict expected.
- `argos/cli/tests/test_orchestrate.py` (new) — 18 tests across three
  classes: `ParseQueueLibraryTests` (6) for the pure parser,
  `OrchestrateCLITests` (9) for the argparse shim end-to-end, and
  `SlashCommandFileTests` (3) for the markdown surface (file presence,
  `orchestrator` reference, mirror byte-equality).

**Out of scope confirmed by ticket Non-goals:**

- No actual dispatch (ARG1-022).
- No worktree creation (ARG1-020 ships that).
- No independence analysis (ARG1-021).
- No escalation file production (ARG1-041 ships that).

**Stdlib-only contract (ADR-001 / ADR-002):** `argos.cli.queue` imports
only `re` and `pathlib`; `argos.cli.commands.orchestrate` imports only
`argparse`, `sys`, plus the project's own `argos.cli.queue`. ACs use only
shell builtins, `grep -F`, and `python3 -m argos.cli` invocations — no
`pyyaml`, no `jq`. `pyproject.toml` is unchanged.

**Sibling-conflict surface:** Only `argos/cli/__main__.py` is shared with
the Layer 2 cohort (ARG1-020, ARG1-031, ARG1-041 — all merged on `main`
already; ARG1-012 in flight, but per its `Touches` will not edit
`__main__.py`). Three localized edits per the established
keep-both-registrations pattern.

## Verification

- ACs: 6/6 met (verified live below).
- AC#1 `test -f .claude/commands/orchestrate.md` → exit 0.
- AC#2 `argos orchestrate --dry-run --state-file <fixture>` against a
  three-ticket Queue → exit 0; stdout is `ARG1-022\nARG1-013\nARG1-023\n`
  in queue order.
- AC#3 `argos orchestrate --dry-run --state-file <empty-queue-fixture>`
  (placeholder italic text only) → exit 0; stdout contains `queue empty`.
- AC#4 `argos orchestrate --dry-run --state-file /nonexistent/STATE.md`
  → exit 1; stderr contains `STATE.md not found`.
- AC#5 `grep -F 'orchestrator' .claude/commands/orchestrate.md` → exit 0
  (multiple matches).
- AC#6 `argos orchestrate --dry-run --batch-size 2 --state-file <fixture>`
  with a four-ticket Queue → exit 0; stdout is two lines (`ARG1-001`,
  `ARG1-002`).
- Tests: `python3 -m unittest argos.cli.tests.test_orchestrate -v` → 18
  tests, all OK (Ran 18 tests in 0.152s).
- Regression: `python3 -m unittest discover -s argos/cli/tests` → 166
  tests, all OK (Ran 166 tests in 4.631s). No collateral breakage.
- Stdlib-only preserved: `argos.cli.queue` imports `re`, `pathlib` plus
  `__future__`; `argos.cli.commands.orchestrate` imports `argparse`,
  `sys`, plus the project module. `pyproject.toml` unchanged.
- Slash command mirror: `diff -q .claude/commands/orchestrate.md
  argos/specs/v1.0/commands/orchestrate.md` → exit 0 (byte-identical).
- `argos --help` lists `orchestrate` under Public subcommands.
- File scope: this branch did not touch `argos/cli/dispatch_log.py`,
  `argos/cli/dispatch.py`, `.claude/agents/orchestrator.md`,
  `argos/specs/v1.0/agents/orchestrator.md`, `argos/verifier/`,
  `argos/escalation/`, or `argos/orchestrator/`.
- Findings: 0 critical, 0 major, 0 minor.
- Decision: pass
