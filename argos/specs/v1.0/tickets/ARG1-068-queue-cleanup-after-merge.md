---
id: ARG1-068
title: Operator-driven queue cleanup primitive (remove shipped tickets from ## Queue)
status: ready
layer: 2
depends_on: [ARG1-054]
blocks: []
allowed_tools: [Read, Edit, Write, Bash, Grep, Glob]
denied_paths: ["argos/specs/v1.0/decisions/**", "argos/specs/v1.0/PRD.md", "argos/specs/v1.0/ARCHITECTURE.md"]
---

## Context

The orchestrator agent doc explicitly defines queue management as
operator-driven: the orchestrator never writes to STATE.md's `## Queue`
section. ARG1-054 (cycle close) shipped with this constraint honored —
it archives `## Done this cycle` entries and clears that section but
does not touch `## Queue`.

Observed during ARG1-067 diagnosis: `## Queue` accumulates stale entries
for tickets that have already shipped. After ARG1-022, ARG1-013, ARG1-023
all merged to main, all three remained listed in the live `## Queue`.
Without manual cleanup, every subsequent `argos orchestrate --dry-run`
proposes re-dispatching shipped tickets.

The orchestrator's invariant is correct (it can't write STATE.md
queue-side without violating ARG1-032's hook contract for non-verifier
authors). The gap is operator-tooling: there's no convenient way for
the operator to clean shipped entries out of the queue.

## Goal

Ship a queue-cleanup primitive that lets the operator remove shipped
tickets from `## Queue` in one command. The primitive performs structural
STATE.md edits (same class as ARG1-054's archival), so it uses the
ARGOS_CYCLE_CLOSE=1 hook bypass.

Likely surface: `argos sync --clean-queue` or `argos sync --remove-shipped`,
mirroring ARG1-054's `--close-cycle` placement. Final naming is the
planner's call.

The mechanism reads `## Done this cycle` (and possibly the cycle archives
under `argos/specs/cycles/`) to identify shipped ticket ids, then removes
matching entries from `## Queue` via atomic tempfile rewrite.

## Acceptance criteria

AC#1 — Subcommand exists with --help; exits 0 with a clear usage line.

AC#2 — Removes from `## Queue` exactly those tickets whose ids appear in
       either `## Done this cycle` of the live STATE.md OR any
       `argos/specs/cycles/*.md` archive. Tickets in the queue that have
       not shipped remain.

AC#3 — Idempotent: second invocation in a row is a no-op.

AC#4 — Uses ARGOS_CYCLE_CLOSE=1 only on the single git commit subprocess,
       matching ARG1-054's pattern. No incidental writes use the bypass.

AC#5 — Atomic tempfile + os.replace for the STATE.md rewrite (ARG1-051
       pattern). Mid-rewrite SIGKILL leaves either old or new state, never
       a partial.

AC#6 — Dry-run support: `--dry-run` prints what would be removed without
       modifying STATE.md or producing a commit.

AC#7 — Empty queue → no-op, no commit (parallel to ARG1-054 AC#5).

AC#8 — Full sweep clean: `python3 -m unittest discover -s argos/cli/tests`
       exits 0.

AC#9 — `argos lint-imports argos/` exits 0.

## Non-goals

- Not automating queue cleanup as part of cycle close. ARG1-054 is
  scope-correct; this is a separate operator action.
- Not touching the orchestrator dispatch loop. The orchestrator continues
  to never write STATE.md.
- Not modifying the hook. The bypass mechanism (ARGOS_CYCLE_CLOSE=1) is
  the legitimate channel for structural rewrites.
- Not building a UI for queue management; this is a CLI primitive only.

## State on completion

Append via `python3 -m argos.cli state-append --suffix done`.

## Plan

Surface chosen: **`argos sync --clean-queue`** — parallels ARG1-054's
`argos sync --close-cycle` (verb-object, same `sync` namespace, same
structural-rewrite class). Final naming per ticket §Goal ("the planner's
call").

Files:
- `argos/cli/commands/clean_queue.py` (new) — mirrors `cycle_close.py`:
  `clean_queue(...)` library entry + `main(argv)` CLI shim, module-local
  error classes (`CleanQueueError`, `QueueSectionMissingError`),
  `CleanQueueResult` dataclass.
  - Shipped-id set = ticket ids in the live `## Done this cycle` section
    (exact-heading bound, blocks-in-section filter — reuses cycle_close's
    discipline so suffixed historical `## Done this cycle (ARG1-001)`
    archives are *not* picked up) ∪ `ticket=` ids across every
    `argos/specs/cycles/*.md` archive (via `state_parser.parse`).
  - `## Queue` scan reuses `queue.TICKET_ID_RE` for id-shape; bullet/
    heading regexes are module-local (mirroring cycle_close). Removes
    exactly the queue bullet lines whose leading id is shipped; every other
    line (placeholder, unshipped bullets, blanks) is preserved verbatim.
  - No removals → return `None` (the idempotent no-op; also covers empty
    queue). Atomic `tempfile` + `os.replace` rewrite. `ARGOS_CYCLE_CLOSE=1`
    exported only on the single `git commit` subprocess; `git add` and the
    tempfile write use unmodified env.
- `argos/cli/__main__.py` (modify) — `sync` dispatch gains a `--clean-queue`
  branch alongside `--close-cycle`; `_STUB_TICKETS` comment updated.
- `argos/cli/tests/test_clean_queue.py` (new) — hermetic temp-git-repo
  harness (same shape as `test_cycle_close.py`), wires the real ARG1-032
  pre-commit hook to prove the bypass is load-bearing.

Stdlib only (argparse, os, re, subprocess, sys, tempfile, dataclasses,
pathlib) — ADR-001 / ADR-002. Does NOT touch `cycle_close.py`, the hook,
or the orchestrator dispatch loop (ticket §Non-goals).

## Verification

All checks run live on branch `ticket/ARG1-068`.

- **AC#1** — `argos sync --clean-queue --help` exits 0 with a `usage:` line
  and the `clean-queue` prog name. ✓
- **AC#2** — End-to-end in a scratch repo: queue listed ARG1-022 (live
  `## Done this cycle`), ARG1-013 + ARG1-023 (in a `cycles/2026-05-01.md`
  archive), and ARG1-099 (unshipped). Run removed exactly
  `ARG1-022, ARG1-013, ARG1-023`; `parse_queue` of the result returned
  `["ARG1-099"]`. Unit: `test_removes_done_section_shipped_keeps_unshipped`,
  `test_archive_only_shipped_is_removed`. ✓
- **AC#3** — Second consecutive run printed `nothing to clean`, returned
  `None`, HEAD unchanged. Unit: `test_second_run_no_op`. ✓
- **AC#4** — `ARGOS_CYCLE_CLOSE=1` is set only on the `git commit`
  subprocess env (`git add` + tempfile write use unmodified env).
  `test_hook_blocks_queue_deletion_without_bypass` confirms the real hook
  rejects the queue-bullet deletion absent the bypass (stderr
  `STATE.md modified outside append-block`). ✓
- **AC#5** — Atomic `tempfile.mkstemp` + `os.fsync` + `os.replace`; no
  `STATE.md.tmp.*` leftovers after the run; result parses clean. Unit:
  `test_no_temp_files_remain_after_write`. ✓
- **AC#6** — `--dry-run` printed `would remove 3 shipped ticket(s) …`,
  left STATE.md byte-identical, produced no commit. Unit:
  `test_dry_run_no_write_no_commit`, `test_cli_dry_run`. ✓
- **AC#7** — Placeholder-only queue → `None`, no commit, `nothing to
  clean`. Unit: `test_placeholder_only_queue_is_noop`,
  `test_cli_empty_queue_prints_nothing_to_clean`. ✓
- **AC#8** — `python3 -m unittest discover -s argos/cli/tests` → Ran 304
  tests, OK (15 new). ✓
- **AC#9** — `python3 -m argos.cli lint-imports argos/` → exit 0. ✓

Decision: pass.
