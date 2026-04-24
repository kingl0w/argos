# Argos

Spec driven outer loop orchestration for AI coding agents. An open source analogue to Traycer's Bart mode, built as a thin scaffold over the native agents, slash commands, and hooks of your harness — no separate runtime, no proprietary service. Primary tested target: Claude Code. Experimental support for Cursor, Codex CLI, and Gemini CLI (see [Supported AI coding harnesses](#supported-ai-coding-harnesses)).

Argos is opinionated: specs are the source of truth, a ticket moves through a fixed loop of specialized agents, and the human steers only when plan and reality disagree.

## What Argos is

- A directory layout (`argos/specs/`, plus per-harness `.claude/`, `.cursor/`, `.codex/`, `.gemini/` generated from `source/`) plus a methodology document (`ARGOS.md`) and operating rules (`argos/RULES.md`, mirrored to `CLAUDE.md` and `AGENTS.md` at build time).
- Four agents — **planner**, **coder**, **watchdog**, **verifier** — each with a narrow job and its own allowed-tools set.
- A small set of slash commands (`/new-ticket`, `/next`, `/steer`, `/ask`) that drive the loop.
- CI hooks (`spec-lint`) that fail a PR if `argos/specs/STATE.md` is stale, if a ticket lacks acceptance criteria, or if an ADR is referenced but missing.

Argos is **not** an agent framework, a fine-tune, or a hosted product. It's a template repo. Fork it, run `argos-init.sh`, and the scaffold installs itself into your project.

## The loop

```
                    ┌──────────────────────────────────────┐
                    │       argos/specs/ (PRD, ARCH,       │
                    │        STATE, tickets, ADRs)         │
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
- **coder** executes the plan against the codebase. Cannot touch `argos/specs/`.
- **watchdog** diffs the coder's changes against the plan. If the coder wandered (new deps, out-of-scope files, missing acceptance-criterion coverage), it emits `CHAOS_BLOCKED` and stops the loop.
- **verifier** runs the project's tests and the ticket's acceptance criteria. Appends a Verification section. On pass, updates `STATE.md`.
- **auto-steer** only fires on `CHAOS_BLOCKED` — the loop hands control back to the human with the mismatch summary. There is no silent recovery.

Retry caps: planner→coder retries once on a flagged plan; verifier never retries itself (a failed verify is a failed ticket, not a loop).

## Quickstart

1. **Use this template** on GitHub (green button → *Use this template* → *Create new repository*).
2. Clone your new repo, then run the init script:
   ```
   ./argos/scripts/argos-init.sh
   ```
   This prompts for project name, ticket prefix, and one-line description; fills the `.template` files in `argos/specs/`; installs an `argos/.initialized` sentinel so it won't re-run.
3. Fill in `argos/specs/PRD.md` and `argos/specs/ARCHITECTURE.md` manually. They're the input the planner reads on every ticket.
4. Open Claude Code in the repo. Run `/new-ticket` to draft your first ticket, then `/next` to run the loop.

A full first cycle — from init to first merged ticket — should take under 30 minutes on a fresh repo.

## Upgrading from v0.4

Argos v0.5 consolidates runtime files under `argos/` instead of scattering them at the repo root. If you started on v0.4, run the one-shot migration from inside your project:

```bash
bash argos/scripts/argos-migrate-v0.5.sh
git add -A
git commit -m "Migrate to Argos v0.5 layout"
```

The script moves `.specs/` to `argos/specs/`, `ARGOS-RULES.md` to `argos/RULES.md`, the per-script helpers to `argos/scripts/`, and regenerates the harness outputs (`CLAUDE.md`, `AGENTS.md`, `.claude/`, `.cursor/`, `.codex/`, `.gemini/`) from `source/`. It is idempotent — re-running on an already-migrated repo is a no-op.

New projects using v0.5 write directly to the new layout; `argos-init.sh` needs no migration.

## Supported AI coding harnesses

Argos v0.4 builds harness-specific output from a single `source/` directory. Not all harnesses are equally tested.

| Harness     | Status       | Notes                                                      |
|-------------|--------------|------------------------------------------------------------|
| Claude Code | Tested       | Primary target. Full loop validated end to end.            |
| Cursor      | Experimental | Files generated under `.cursor/`. Not yet tested in-tool.  |
| Codex CLI   | Experimental | Files generated under `.codex/`. Not yet tested in-tool.   |
| Gemini CLI  | Experimental | Files generated under `.gemini/`. Not yet tested in-tool.  |

All harness directories are committed to the repo, so "Use this template" works instantly with Claude Code and provides a starting point for the others. Per-harness frontmatter tuning (Cursor `.mdc` fields, Codex `$ARGNAME` placeholders, Gemini minimal skills format) is Phase 2 work.

To regenerate after editing `source/`:

```bash
bash scripts/build.sh
```

The build is deterministic — rebuilding from the same source produces byte-identical output.

## Argos vs Traycer Bart

| Dimension             | Traycer Bart                              | Argos                                              |
|-----------------------|-------------------------------------------|----------------------------------------------------|
| Runtime               | Hosted service, proprietary               | Claude Code subagents, local                       |
| Spec format           | Opaque to user                            | Plain markdown in `argos/specs/`, git-tracked     |
| Orchestration         | Single planner/executor                   | Four specialized agents, explicit handoff          |
| Steering              | Implicit, model-driven                    | Manual `/steer` on `CHAOS_BLOCKED` only           |
| Source of truth       | Platform state                            | `STATE.md` + git                                   |
| Extensibility         | Vendor roadmap                            | Fork the template, edit the agents                 |
| Cost model            | SaaS subscription                         | Your own model-provider API usage                  |
| Lock-in               | High — specs live in their system         | None — delete the harness directories and you still have code |

Argos is worse at: onboarding polish, hosted dashboards, multi-user review UI. Traycer is worse at: running offline, being inspected, being forked.

## Pairing with Impeccable

For frontend work, Argos pairs cleanly with [Impeccable](https://github.com/pbakaus/impeccable) — a design-quality skill suite (`/polish`, `/typeset`, `/audit`, `/harden`, etc.) that the coder agent can invoke mid-ticket. Suggested split:

- **Argos** owns *what to build* (tickets, plan, verification).
- **Impeccable** owns *how it looks and feels* (typography, spacing, motion, a11y).

Install Impeccable alongside Argos; the coder agent's allowed-tools list already permits `Skill` invocations. A frontend ticket's Plan can include steps like "after implementation, run `/polish` then `/audit`" and the verifier will check the audit report as part of acceptance.

## Directory layout

```
your-project/
├── argos/                       # Argos-controlled runtime
│   ├── specs/                     # Living spec (PRD, architecture, state, tickets, ADRs)
│   ├── scripts/
│   │   ├── argos-init.sh            # One-time project setup
│   │   ├── argos-status.sh          # Inspect current state
│   │   ├── argos-sync.sh            # Bidirectional GitHub Issues mirror
│   │   ├── argos-chaos-probe.sh     # Mechanical chaos checks (called by watchdog)
│   │   └── argos-migrate-v0.5.sh    # v0.4 → v0.5 one-shot migration
│   └── RULES.md                   # Source of truth for project rules
├── source/                      # Canonical agents + commands (edit here)
│   ├── agents/                    # planner, coder, watchdog, verifier
│   └── commands/                  # next, steer, ask, new-ticket, reconcile
├── scripts/
│   └── build.sh                   # Regenerate harness outputs from source/
├── .claude/                     # Generated: Claude Code (harness-required at root)
│   ├── agents/
│   └── commands/
├── .cursor/                     # Generated: Cursor (harness-required at root)
│   ├── rules/
│   └── commands/
├── .codex/                      # Generated: Codex CLI (harness-required at root)
│   ├── agents/
│   └── prompts/
├── .gemini/                     # Generated: Gemini CLI (harness-required at root)
│   └── skills/
├── .github/                     # Issue templates, spec-lint CI (GitHub-required at root)
│   ├── ISSUE_TEMPLATE/
│   └── workflows/
├── CLAUDE.md                    # Generated from argos/RULES.md (Claude Code reads this at root)
├── AGENTS.md                    # Generated from argos/RULES.md (Codex family convention)
└── ARGOS.md                     # Methodology doc
```

Edit `source/` and re-run `scripts/build.sh` to regenerate the per-harness directories. `argos/specs/` (PRD, ARCHITECTURE.md, STATE.md, tickets, decisions/ADRs) is the project's living spec — written by humans and the verifier, never by the coder.

Why the split between `argos/` and root: `.claude/`, `.cursor/`, `.codex/`, `.gemini/`, `.github/`, `CLAUDE.md`, and `AGENTS.md` are hardcoded by their respective harnesses and must live at the repo root. Everything else Argos owns has been consolidated under `argos/` to keep the project root uncluttered.

## Roadmap

- v0.4 Phase 1 (current): multi-harness build system with Claude Code fully tested
- v0.4 Phase 2: per-harness frontmatter tuning and in-tool validation for Cursor, Codex CLI, Gemini CLI
- v0.4 Phase 3: README and docs sweep, terminology neutralization ("subagent" → "agent" where appropriate)
- v0.5: real-world hardening based on dogfooding on production projects

File a GitHub issue if you hit friction on any harness — the experimental ones in particular need real usage to mature.
