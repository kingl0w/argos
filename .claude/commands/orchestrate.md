---
description: Invoke the Argos orchestrator agent to dispatch the next batch of queued tickets
argument-hint: "[--dry-run] [--batch-size N]"
---

Invoke the **orchestrator** subagent (`.claude/agents/orchestrator.md`,
canonical mirror `argos/specs/v1.0/agents/orchestrator.md`) to read
`argos/specs/v1.0/STATE.md` §Queue and dispatch the next batch of tickets
through the four-agent loop (planner → coder → watchdog → verifier) per
ticket, in their own worktrees.

The orchestrator is a **dispatcher and reconciler** — it never edits code,
PRD.md, ARCHITECTURE.md, or STATE.md. It picks tickets, spawns sessions,
routes escalations, and merges verifier-passed worktrees back to base.
Read its full contract at `argos/specs/v1.0/agents/orchestrator.md`
before invoking it for the first time.

## What this command does

1. **Surface the next batch.** Run `argos orchestrate --dry-run` to read
   `argos/specs/v1.0/STATE.md` §Queue and print the ticket ids the
   orchestrator would consider next, in queue order. Pass the
   `--batch-size N` argument from `$1` / `$2` through to cap the printed
   list. If stdout contains `queue empty`, stop — there is nothing to
   dispatch and the caller should run `/new-ticket` or check
   §Current focus.
2. **Hand off to the orchestrator agent.** Spawn the **orchestrator**
   subagent with the printed ticket-id list, the current epic id (read
   from §Current focus or supplied by the caller), and the configured
   `orchestrator.max_parallel` cap (read by the agent from
   `argos/config.toml` via `argos config get orchestrator.max_parallel`).
   Per its agent definition the orchestrator will:
   - Re-read §Queue, §In progress, §Open decisions, §Known drift, and
     existing worktrees under `.argos/worktrees/` to reconcile state.
   - Pick a candidate batch satisfying the independence invariant
     (file-disjoint planner outputs, no transitive `depends_on:` edges).
   - For each picked ticket, spawn a session via
     `argos run-session --ticket <id> --worktree .argos/worktrees/<id>-<sha>/ --epic <epic>`
     (ARG1-020). The cap is `orchestrator.max_parallel` (default 3) even
     when more tickets are independent.
   - Route each session's verifier output:
     `decision: pass` / `pass-with-minors` → fast-forward merge;
     `decision: fail` → one auto-fix retry (ARG1-013) then escalate;
     sub-agent escalation → leave the worktree intact, mark parked.
   - Append dispatch-log entries under `argos/specs/dispatch/<epic>/`
     (writer is ARG1-012); never overwrite a prior entry.
3. **Stop on escalation.** If the orchestrator (or any sub-agent in any
   session) writes a `severity: blocking` escalation under
   `argos/specs/escalations/`, the dispatch run halts. Surface the
   escalation file path to the operator and suggest `argos attend`.

## Constraints inherited from the orchestrator agent

- The orchestrator never writes to PRD.md, ARCHITECTURE.md, or STATE.md
  directly. STATE.md mutations during dispatch are made by the verifier
  inside each session via `argos verifier-writeback` → `argos
  state-append`. The orchestrator may only append to §Known drift via
  `argos state-append --section "Known drift" --author orchestrator
  --session <id>` when reconciling cross-session drift it observes.
- Never spawn a second orchestrator. The orchestrator is a singleton per
  Argos invocation.
- Never reach into a running session to influence its planner / coder /
  watchdog / verifier — sessions communicate back only through the
  verifier-output block.
- Never silently retry past the auto-fix retry cap (1).

## When to escalate vs. proceed (operator)

Per the orchestrator's escalation triggers
(`argos/specs/v1.0/agents/orchestrator.md` §Escalation triggers): missing
ADR for a load-bearing technology choice, stdlib/third-party boundary
ambiguity, external-tool semantic ambiguity, sub-agent escalation
propagated upward, plan↔reality divergence the watchdog flagged
`CHAOS_BLOCKED` and `/steer` cannot reconcile, merge-time semantic
conflict on file-disjoint sessions, or cross-session drift observable
only across multiple verifier blocks. The orchestrator writes the
escalation; the operator drains it via `argos attend`.

## Tools the orchestrator agent will call

- `argos orchestrate --dry-run` — this command's entry point (ARG1-011).
- `argos run-session --ticket <id> --worktree <path> --epic <epic>` —
  per-ticket worktree spawn (ARG1-020).
- `argos verifier-writeback` — verifier's STATE.md writer
  (ARG1-031); invoked inside each session, not by the orchestrator.
- `argos escalate --ticket <id> --severity blocking --raised-by orchestrator
  --body <text>` — escalation writer (ARG1-041).
- `argos state-append --section "Known drift" --author orchestrator
  --session <id> --body-file <file>` — only-allowed STATE.md write
  surface for the orchestrator (ARG1-051 / ARG1-061).

Real parallel dispatch and merge-on-pass are ARG1-022 and ARG1-023; this
command ships the entry point and the queue-read surface.
