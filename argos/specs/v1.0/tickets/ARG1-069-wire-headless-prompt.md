---
id: ARG1-069
title: Wire ticket-prompt injection into spawn_session for headless autonomous dispatch
status: ready
layer: 3
depends_on: [ARG1-020, ARG1-022]
blocks: []
allowed_tools: [Read, Write, Edit, Bash, Grep, Glob]
denied_paths: ["argos/specs/v1.0/decisions/**", "argos/specs/decisions/**"]
---

## Context

The dispatcher (ARG1-022) spawns per-ticket Claude Code sessions via
spawn_session (ARG1-020). But spawn_session runs bare `claude` interactively
and passes NO prompt — it only exports ARGOS_TICKET / ARGOS_EPIC /
ARGOS_WORKTREE env vars, which nothing reads. So a spawned session lands in a
worktree with no instruction. Autonomous dispatch cannot work until the
session is actually told what to build. This gap was invisible to tests
because they stub the harness binary with /bin/true.

This is the missing link between "dispatcher stages worktrees" and "dispatcher
runs the loop." It is the keystone of Layer 3.

## Goal

Make spawn_session run the harness headlessly with an auto-built prompt:
`claude -p "<prompt>" --allow-dangerously-skip-permissions` (or the project's
chosen permission mode). The prompt is constructed from the ticket file plus
the standing argos rules. Headless mode (-p) means no tty, so parallel
dispatch (max_parallel > 1) works without terminal contention.

## Acceptance criteria

- [ ] A new prompt-builder (e.g. argos/cli/orchestrator/session_prompt.py)
      reads a ticket file and returns a complete prompt string containing:
      the ticket id, the ticket's full text, the standing rules (stdlib-only
      per ADR-001; AC tooling stdlib-only per ADR-002; verify all ACs before
      commit; state writes via `argos state-append`, never edit STATE.md
      directly; push to origin/<branch>, do not merge; escalate genuine
      ambiguity via argos/specs/v1.0/schemas/escalation.md), and an
      instruction to read the ticket and implement it.
- [ ] spawn_session invokes the harness with `-p <prompt>` (headless), not
      bare interactive. The exact argv is `[binary, "-p", prompt,
      "--allow-dangerously-skip-permissions"]` (permission flag confirmed
      present in `claude --help`). Session stdout/stderr are captured to the
      dispatch log or returned for logging.
- [ ] spawn_session still exports ARGOS_TICKET / ARGOS_EPIC / ARGOS_WORKTREE
      (kept for downstream tooling) and still returns the child exit code.
- [ ] The prompt-builder is unit-tested: given a fixture ticket file, the
      returned prompt contains the ticket id, the ACs, and each standing
      rule. (No live claude invocation in tests — test the builder pure.)
- [ ] spawn_session is tested with a stub binary that records its argv to a
      file, asserting `-p` and the prompt are passed. (Keep the /bin/true
      style but capture argv.)
- [ ] argos lint-imports argos/ exits 0. Stdlib-only (ADR-001).
- [ ] Full sweep: python3 -m unittest discover -s argos/cli/tests exits 0.

## Non-goals

- Not changing the dispatch loop, independence detection, retry, or merge
  logic. Only the spawn-and-instruct link.
- Not building an interactive fallback. Headless is the dispatch path.

## Touches

- argos/cli/orchestrator/session_prompt.py (new — prompt builder)
- argos/cli/worktree.py (spawn_session — headless invocation)
- argos/cli/tests/test_session_prompt.py (new)
- argos/cli/tests/ (spawn_session argv-capture test)

## State on completion

Append via `python3 -m argos.cli state-append --suffix done`.
