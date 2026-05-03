---
id: ARG1-067
title: Update test_dry_run_lists_queue for ARG1-022 markdown table format
status: ready
layer: 2
depends_on: []
blocks: [ARG1-054]
allowed_tools: [Read, Edit, Write, Bash, Grep, Glob]
denied_paths: ["argos/specs/v1.0/decisions/**", "argos/specs/v1.0/PRD.md", "argos/specs/v1.0/ARCHITECTURE.md"]
---

## Context

`argos/cli/tests/test_orchestrate.OrchestrateCLITests.test_dry_run_lists_queue`
fails on main at df84beb. The test asserts the dry-run CLI's stdout is a flat
list of ticket IDs:

    res.stdout.splitlines() == ["ARG1-022", "ARG1-013", "ARG1-023"]

ARG1-022 AC#6 shipped a richer canonical markdown table format for dry-run
output, with columns ticket_id / group / dispatch_order / parallel_with.
The library contract is unchanged — `test_parse_queue_file_round_trip`
(line 152) confirms `parse_queue_file()` still returns the flat list.
Only the CLI presentation layer evolved.

The test is pinned via `--state-file` to a tempdir fixture, but not via
`--ticket-dir`. The new table format's `parallel_with` column requires
independence detection, which reads ticket frontmatter from the ticket
directory. ARG1-013's planner addressed this in two other dry-run tests
in the same file but didn't touch this one (it didn't fail at the time
ARG1-013 shipped because the format change landed in ARG1-022 the same
session, before ARG1-013's broader sweep ran).

## Goal

Update `test_dry_run_lists_queue` to:
1. Assert against the markdown table format from ARG1-022 AC#6.
2. Pin `--ticket-dir` to a temp dir with synthetic ticket frontmatter, so
   independence detection's output is deterministic.
3. Preserve the test's original intent: the dry-run output enumerates the
   three queued tickets with correct group/order metadata.

## Acceptance criteria

AC#1 — `python3 -m unittest argos.cli.tests.test_orchestrate.OrchestrateCLITests.test_dry_run_lists_queue`
       exits 0.

AC#2 — Test asserts at minimum:
       (a) stdout contains a markdown table header row with literal columns
           `ticket_id`, `group`, `dispatch_order`, `parallel_with`
       (b) each ticket from the fixture queue (ARG1-022, ARG1-013, ARG1-023)
           appears as a data row
       (c) the test does NOT assert specific group/order values — those are
           independence-detection outputs that depend on the synthetic
           ticket frontmatter the test sets up. Asserting that the rows
           are present and have non-empty group/dispatch_order is enough.
           (Stricter assertions risk re-coupling to detection internals.)

AC#3 — `--ticket-dir` pinned to a tempdir per ARG1-013's pattern. The
       tempdir contains synthetic ticket frontmatter files for ARG1-022,
       ARG1-013, ARG1-023 with deterministic `files_touched:` lists. Live
       `argos/specs/v1.0/tickets/` must not affect test outcome.

AC#4 — Full sweep: `python3 -m unittest discover -s argos/cli/tests` exits 0.
       Test count unchanged.

AC#5 — `argos lint-imports argos/` exits 0.

AC#6 — `git diff main -- argos/cli/tests/test_orchestrate.py` shows changes
       only to `test_dry_run_lists_queue` plus any necessary supporting
       fixture helpers. No other tests modified. Library code (parse_queue_file,
       orchestrate.py, dispatch.py, etc) is NOT modified — this is a
       test-only fix.

## Non-goals

- Not modifying the dry-run CLI output format. ARG1-022 AC#6 is the contract.
- Not addressing `## Queue` cleanup-after-merge (separate observation; will
  be filed as ARG1-068 post-merge).
- Not amending the verifier rubric. Output-format-vs-test-assertion drift
  is a future rubric concern, not actionable here.

## State on completion

Append via `python3 -m argos.cli state-append --suffix done`.
