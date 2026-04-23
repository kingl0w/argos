# Argos

Spec-driven outer-loop orchestration for Claude Code. An open-source analogue to Traycer's Bart mode, built as a thin scaffold over Claude Code's native subagents, slash commands, and hooks — no separate runtime, no proprietary service.

Argos is opinionated: specs are the source of truth, a ticket moves through a fixed loop of specialized subagents, and the human steers only when plan and reality disagree.

## What Argos is

- A directory layout (`.specs/`, `.claude/agents/`, `.claude/commands/`) plus a methodology document (`ARGOS.md`) and operating rules (`CLAUDE.md`).
- Four Claude Code subagents — **planner**, **coder**, **watchdog**, **verifier** — each with a narrow job and its own allowed-tools set.
- A small set of slash commands (`/new-ticket`, `/next`, `/steer`, `/ask`) that drive the loop.
- CI hooks (`spec-lint`) that fail a PR if `.specs/STATE.md` is stale, if a ticket lacks acceptance criteria, or if an ADR is referenced but missing.

Argos is **not** an agent framework, a fine-tune, or a hosted product. It's a template repo. Fork it, run `argos-init.sh`, and the scaffold installs itself into your project.

## The loop

```
                    ┌──────────────────────────────────────┐
                    │          .specs/ (PRD, ARCH,         │
                    │          STATE, tickets, ADRs)       │
                    └──────────────────────────────────────┘
                                      │
                                      ▼
  ┌─────────┐   plan    ┌─────────┐   diff   ┌────────────┐   report   ┌──────────┐
  │ planner │──────────▶│  coder  │─────────▶│  watchdog  │───────────▶│ verifier │
  └─────────┘           └─────────┘          └────────────┘            └──────────┘
       ▲                                           │                        │
       │                                           │ CHAOS_BLOCKED          │ pass/fail
       │                                           ▼                        ▼
       │                                    ┌────────────┐            ┌──────────┐
       └────────── auto-steer ──────────────│   human    │◀───────────│ STATE.md │
                                            │  (/steer)  │   update   │  write   │
                                            └────────────┘            └──────────┘
```

- **planner** reads `STATE.md`, `ARCHITECTURE.md`, and the ticket; writes a Plan section into the ticket. Read-only on code.
- **coder** executes the plan against the codebase. Cannot touch `.specs/`.
- **watchdog** diffs the coder's changes against the plan. If the coder wandered (new deps, out-of-scope files, missing acceptance-criterion coverage), it emits `CHAOS_BLOCKED` and stops the loop.
- **verifier** runs the project's tests and the ticket's acceptance criteria. Appends a Verification section. On pass, updates `STATE.md`.
- **auto-steer** only fires on `CHAOS_BLOCKED` — the loop hands control back to the human with the mismatch summary. There is no silent recovery.

Retry caps: planner→coder retries once on a flagged plan; verifier never retries itself (a failed verify is a failed ticket, not a loop).

## Quickstart

1. **Use this template** on GitHub (green button → *Use this template* → *Create new repository*).
2. Clone your new repo, then run the init script:
   ```
   ./scripts/argos-init.sh
   ```
   This prompts for project name, ticket prefix, and one-line description; fills the `.template` files in `.specs/`; installs a `.argos-initialized` sentinel so it won't re-run.
3. Fill in `.specs/PRD.md` and `.specs/ARCHITECTURE.md` manually. They're the input the planner reads on every ticket.
4. Open Claude Code in the repo. Run `/new-ticket` to draft your first ticket, then `/next` to run the loop.

A full first cycle — from init to first merged ticket — should take under 30 minutes on a fresh repo.

## Supported AI coding harnesses

Argos v0.4 supports four harnesses from a single source:

- Claude Code (`.claude/`)
- Cursor (`.cursor/`)
- Codex CLI (`.codex/`)
- Gemini CLI (`.gemini/`)

All harness directories are built from `source/` and committed to the
repo, so "Use this template" works instantly with any supported tool.

To regenerate after editing source/: `bash scripts/build.sh`

## Argos vs Traycer Bart

| Dimension             | Traycer Bart                              | Argos                                              |
|-----------------------|-------------------------------------------|----------------------------------------------------|
| Runtime               | Hosted service, proprietary               | Claude Code subagents, local                       |
| Spec format           | Opaque to user                            | Plain markdown in `.specs/`, git-tracked          |
| Orchestration         | Single planner/executor                   | Four specialized subagents, explicit handoff       |
| Steering              | Implicit, model-driven                    | Manual `/steer` on `CHAOS_BLOCKED` only           |
| Source of truth       | Platform state                            | `STATE.md` + git                                   |
| Extensibility         | Vendor roadmap                            | Fork the template, edit the agents                 |
| Cost model            | SaaS subscription                         | Your own Anthropic API usage                       |
| Lock-in               | High — specs live in their system         | None — delete `.claude/` and you still have code  |

Argos is worse at: onboarding polish, hosted dashboards, multi-user review UI. Traycer is worse at: running offline, being inspected, being forked.

## Pairing with Impeccable

For frontend work, Argos pairs cleanly with [Impeccable](https://github.com/pbakaus/impeccable) — a design-quality skill suite (`/polish`, `/typeset`, `/audit`, `/harden`, etc.) that the coder subagent can invoke mid-ticket. Suggested split:

- **Argos** owns *what to build* (tickets, plan, verification).
- **Impeccable** owns *how it looks and feels* (typography, spacing, motion, a11y).

Install Impeccable alongside Argos; the coder agent's allowed-tools list already permits `Skill` invocations. A frontend ticket's Plan can include steps like "after implementation, run `/polish` then `/audit`" and the verifier will check the audit report as part of acceptance.

## Directory layout

```
.
├── .claude/
│   ├── agents/         # planner, coder, watchdog, verifier subagent definitions
│   └── commands/       # /new-ticket, /next, /steer, /ask
├── .specs/
│   ├── PRD.md              # product-level intent (human-written)
│   ├── ARCHITECTURE.md     # structural decisions (human-written, updated via ADRs)
│   ├── STATE.md            # current focus / queue / drift (agent-written, human-reviewed)
│   ├── tickets/            # one markdown file per ticket, the unit of work
│   └── decisions/          # ADRs, numbered, immutable once decided
├── .github/
│   ├── ISSUE_TEMPLATE/     # mirrors ticket shape so GitHub Issues = tickets view
│   └── workflows/          # spec-lint CI, ticket↔issue sync
├── scripts/
│   └── argos-init.sh       # one-shot template initializer
├── ARGOS.md            # methodology: why this shape, what it optimizes for
├── CLAUDE.md           # operating rules Claude Code reads on every session
├── LICENSE
└── README.md
```

## Status

v0.1. Expect rough edges in the planner (under-specs tests), the coder (over-refactors fresh repos), and the verifier (can claim tests pass without running them). See `ARGOS.md` for the known-weakness list and what to watch.
