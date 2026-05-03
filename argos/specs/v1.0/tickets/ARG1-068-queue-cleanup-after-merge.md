---
id: ARG1-068
title: Operator-driven queue cleanup primitive (remove shipped tickets from ## Queue)
status: queued
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
