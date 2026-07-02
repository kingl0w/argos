# Argos

Queue a ticket. Argos builds and tests it in an isolated worktree, pushes a branch, and you merge. That's the whole loop.

Spec driven outer loop orchestration for AI coding agents. An open source take on Traycer's Bart mode with no separate runtime and no proprietary service. Argos ships as **two complementary layers**:

1. **A scaffold that targets multiple harnesses.** Specialized agents, slash commands, and hooks generated from a single `source/` tree into the native formats of Claude Code, Cursor, Codex CLI, and Gemini CLI.
2. **A Python CLI (`argos`).** The current primary interface. It scaffolds a repo, manages the ticket queue, and dispatches work as parallel git worktree sessions that build, test, verify, and **push**. It never merges.

Argos is opinionated. Specs are the source of truth, a ticket moves through a fixed loop of specialized agents, and the human steers only when plan and reality disagree. The human always owns the merge.

> **argos builds, the operator owns the merge.**

## What Argos is

- **A directory layout** (`argos/specs/`, plus the `.claude/`, `.cursor/`, `.codex/`, and `.gemini/` directories generated from `source/` for each harness), a methodology document (`ARGOS.md`), and operating rules (`argos/RULES.md`, mirrored to `CLAUDE.md` and `AGENTS.md` at build time).
- **Five agents:** **orchestrator**, **planner**, **coder**, **watchdog**, and **verifier**. Each has a narrow job and its own allowed tools set. The orchestrator (added with the CLI layer) reads the queue and dispatches sessions. The other four run the per ticket loop.
- **A set of slash commands** (`/new-ticket`, `/next`, `/orchestrate`, `/steer`, `/ask`, `/reconcile`) that drive the loop inside a harness.
- **A Python CLI** (`argos`) that uses only the standard library, drives the same loop headlessly, and adds queue management, parallel dispatch, escalation handling, and reconciliation.
- **Hooks** that keep specs honest. A commit hook keeps `STATE.md` append only, and `argos status` exits nonzero when the specs are internally inconsistent.

Argos is **not** an agent framework, a fine tune, or a hosted product. It is a template repo *and* a CLI. The current entry path is the **`argos init`** command (see [Quickstart](#quickstart)). The older interactive bootstrap (`argos/scripts/argos-init.sh`) still exists and is described under [The two entry paths](#the-two-entry-paths).

## The CLI

`argos --help` lists the public subcommands:

| Command        | What it does                                                                 |
|----------------|------------------------------------------------------------------------------|
| `init`         | scaffold `argos/specs/`, write a per repo `argos/conventions.md`, install hooks |
| `queue`        | add/remove a ticket in `STATE.md`'s `## Queue`                               |
| `orchestrate`  | read the queue and dispatch the next batch (in parallel where independent)   |
| `status`       | exit 0 iff the specs are internally consistent                              |
| `sync`         | reconcile tickets, `STATE.md`, and git                                       |
| `attend`       | drain the escalation queue (the operator ratifies ambiguities)              |
| `escalate`     | write an escalation file                                                      |
| `config`       | get / validate config keys                                                   |
| `independence` | decide whether tickets can run in parallel                                   |

**Python ≥3.9, standard library only.** Zero third party runtime dependencies. That is *Argos's own* convention for its own code, enforced by `argos lint-imports`, and it is **not** imposed on your project (see below). If the `argos` console script isn't on your `PATH` yet, every command also works as `python3 -m argos.cli <subcommand>`.

## Conventions as data: Argos works on any repo

Argos is not just for building Argos. `argos init` scaffolds a per repo **`argos/conventions.md`** where the *target* repo declares its **own** language, dependency, and test rules. Argos injects those conventions into every dispatched session, so each session builds to the host project's standards:

- Argos's own repo declares "Python, standard library only."
- A FastAPI service declares its framework, its dependencies, and `pytest` as its test command.
- A TypeScript app declares `npm test`, its lint rules, and so on.

The orchestration machinery is the same everywhere. The rules are data the target owns, which is what lets Argos run on a foreign repo with no special casing.

## Execution model

A dispatched session is autonomous and bounded:

1. Runs in **its own git worktree** (isolated from your working tree and from sibling sessions).
2. **Plans** against the ticket, then **writes code and tests**.
3. **Verifies** against the ticket's acceptance criteria using the host repo's declared test command.
4. **Pushes a branch.** It **never merges.**

`argos orchestrate` runs multiple sessions **in parallel** when independence detection (`argos independence`) clears them as not conflicting. Otherwise they run serially. Finalization is deliberately conservative: push and preserve, or merge on pass only where the config explicitly opts in, and **never silent**. The operator reviews the pushed branch and merges. That boundary is the whole point: *argos builds, the operator owns the merge.*

## The loop

```
        argos/specs/  (PRD, ARCHITECTURE, STATE, tickets, ADRs, conventions)
                                    │
                  argos queue add ▼ │
                          ┌───────────────┐  reads ## Queue, runs independence
                          │  orchestrator │  detection, dispatches a batch,
                          └───────────────┘  one git worktree per ticket
                                    │  (parallel where independent)
                                    ▼
  ┌─────────┐  plan   ┌─────────┐  diff   ┌──────────┐  report  ┌──────────┐
  │ planner │────────▶│  coder  │────────▶│ watchdog │─────────▶│ verifier │
  └─────────┘         └─────────┘         └──────────┘          └──────────┘
       ▲                                       │                      │ pass
       │ autosteer (retry once)                │ CHAOS_BLOCKED        ▼
       │                                       ▼                 push branch ──▶ operator
       └──────────────────────────────── operator (/steer)        + STATE.md     reviews
                                                                   write          & merges
```

- **orchestrator** reads `STATE.md`'s `## Queue`, decides which tickets are independent, and dispatches a batch of per ticket sessions into isolated worktrees. It finalizes conservatively and never merges silently.
- **planner** reads `STATE.md`, `ARCHITECTURE.md`, and the ticket, then writes a Plan section into the ticket. It reads code but never writes it.
- **coder** executes the plan against the codebase. Cannot touch `argos/specs/`.
- **watchdog** diffs the coder's changes against the plan. If the coder wandered (new deps, out of scope files, missing acceptance criterion coverage), it emits `CHAOS_BLOCKED` and stops the loop.
- **verifier** runs the project's tests and the ticket's acceptance criteria, appends a Verification section, and on pass updates `STATE.md`. The session pushes its branch for operator review.
- **autosteer** only fires on `CHAOS_BLOCKED`. The loop hands control back to the human with the mismatch summary. There is no silent recovery.

Retry caps: the planner to coder step retries once on a flagged plan. The verifier never retries itself (a failed verify is a failed ticket, not a loop).

## Quickstart

The bare flow on **any repo** (no workarounds, this is the path validated end to end):

```bash
# 1. Get argos (clone the template; install the CLI, or use `python3 -m argos.cli`).
git clone https://github.com/kingl0w/argos.git

# 2. From inside the repo you want argos to work on:
cd your-repo
argos init                       # scaffolds argos/specs/, writes argos/conventions.md, installs hooks

# 3. Tell argos YOUR repo's rules.
$EDITOR argos/conventions.md     # language, dependencies, test command, injected into every session

# 4. Write a ticket (with acceptance criteria) under argos/specs/.../tickets/, then queue it.
argos queue add ABC-001

# 5. Dispatch. The session builds, tests, verifies, and pushes a branch.
argos orchestrate

# 6. Review the pushed branch and merge it yourself.
```

Fill in `argos/specs/PRD.md` and `argos/specs/ARCHITECTURE.md` once. They are the input the planner reads on every ticket. Inside a harness, `/new-ticket` drafts tickets and `/orchestrate` (or `/next`) drives the loop interactively.

### The two entry paths

- **`argos init` (current, primary).** The CLI command: scaffolds `argos/specs/`, writes the per repo `argos/conventions.md`, and installs the git hooks. Use this.
- **`argos/scripts/argos-init.sh` (legacy v0.5 bootstrap).** An interactive shell script that fills the `{{PROJECT}}` / `{{PREFIX}}` / `{{DESC}}` / `{{DATE}}` placeholders in `argos/specs/**/*.template`, renames `EXAMPLE-001.md` → `<PREFIX>-001.md`, and drops an `argos/.initialized` sentinel so it won't run twice. It predates the CLI and does not install hooks or scaffold `conventions.md`, so prefer `argos init`.

## Upgrading from v0.4

Argos v0.5 consolidated runtime files under `argos/` instead of scattering them at the repo root. If you started on v0.4, run the migration once from inside your project:

```bash
bash argos/scripts/argos-migrate-v0.5.sh
git add -A
git commit -m "Migrate to Argos v0.5 layout"
```

The script moves `.specs/` to `argos/specs/`, `ARGOS-RULES.md` to `argos/RULES.md`, the helper scripts to `argos/scripts/`, and regenerates the harness outputs (`CLAUDE.md`, `AGENTS.md`, `.claude/`, `.cursor/`, `.codex/`, `.gemini/`) from `source/`. It is idempotent. Running it again on an already migrated repo does nothing.

## Supported AI coding harnesses

Argos builds output for each harness from a single `source/` directory. Not all harnesses are equally tested.

| Harness     | Status       | Notes                                                      |
|-------------|--------------|------------------------------------------------------------|
| Claude Code | Tested       | Primary target. Full loop validated end to end.            |
| Cursor      | Experimental | Files generated under `.cursor/`. Not yet tested in the tool. |
| Codex CLI   | Experimental | Files generated under `.codex/`. Not yet tested in the tool. |
| Gemini CLI  | Experimental | Files generated under `.gemini/`. Not yet tested in the tool. |

All harness directories are committed to the repo, so "Use this template" works instantly with Claude Code and gives the others a starting point. Per harness frontmatter tuning (Cursor `.mdc` fields, Codex `$ARGNAME` placeholders, Gemini minimal skills format) is queued for a later release.

To regenerate after editing `source/`:

```bash
bash scripts/build.sh
```

Running `scripts/build.sh` again regenerates the per harness directories from `source/`.

## Argos vs Traycer Bart

| Dimension       | Traycer Bart                | Argos                                                          |
|-----------------|-----------------------------|----------------------------------------------------------------|
| Runtime         | Hosted service, proprietary | Local: harness subagents + a stdlib only Python CLI            |
| Spec format     | Opaque to user              | Plain markdown in `argos/specs/`, git tracked                  |
| Orchestration   | Single planner/executor     | Five specialized agents; a CLI orchestrator dispatches parallel worktree sessions |
| Merge control   | Implicit                    | Sessions push branches; the operator always owns the merge     |
| Steering        | Implicit, model driven      | Manual `/steer` on `CHAOS_BLOCKED` only                        |
| Source of truth | Platform state              | `STATE.md` + git                                               |
| Extensibility   | Vendor roadmap              | Fork the template, edit the agents, declare your own conventions |
| Cost model      | SaaS subscription           | Your own model provider API usage                              |
| Lock-in         | High: specs live in their system | None: delete the harness directories and you still have code |

Argos is worse at: onboarding polish, hosted dashboards, multi user review UI. Traycer is worse at running offline, being inspected, and being forked.

## Pairing with Impeccable

For frontend work, Argos pairs cleanly with [Impeccable](https://github.com/pbakaus/impeccable), a design quality skill suite with commands like `/polish` and `/audit`. Suggested split:

- **Argos** owns *what to build* (tickets, plan, verification).
- **Impeccable** owns *how it looks and feels* (typography, spacing, motion, a11y).

Install Impeccable alongside Argos. The coder agent does **not** invoke Impeccable itself. Its allowed tools are `Read, Write, Edit, Bash, Grep, Glob` (no `Skill`). Instead, on a frontend ticket (a change touching `.tsx/.jsx/.vue/.svelte/.html/.css`) it checks whether Impeccable is installed (it looks for `.claude/commands/polish.md`) and, if so, appends a "Frontend polish suggested: run `/audit` and `/polish` before closing" note to the ticket's Implementation notes. Running the skills is the operator's call.

## Directory layout

```
your-project/
├── argos/                       # Argos controlled runtime
│   ├── specs/                     # Living spec (PRD, architecture, state, tickets, ADRs)
│   │   └── v1.0/                    # Versioned CLI layer specs (agents, schemas, tickets)
│   ├── cli/                       # The argos Python CLI (stdlib only)
│   │   ├── __main__.py              # Subcommand dispatch: init, queue, orchestrate, status, ...
│   │   ├── commands/                # One module per public subcommand
│   │   └── templates/               # Scaffold templates, incl. conventions.md.template
│   ├── conventions.md             # THIS repo's language/dependency/test rules (scaffolded by `argos init`)
│   ├── scripts/
│   │   ├── argos-init.sh             # Legacy interactive template bootstrap (predates the CLI)
│   │   ├── argos-status.sh           # Inspect current state
│   │   ├── argos-sync.sh             # Bidirectional GitHub Issues mirror
│   │   ├── argos-chaos-probe.sh      # Mechanical chaos checks (called by watchdog)
│   │   ├── argos-migrate-v0.5.sh     # v0.4 → v0.5 one shot migration
│   │   └── hooks/                    # Git hooks (e.g. STATE.md append only commit hook)
│   └── RULES.md                   # Source of truth for project rules
├── source/                      # Canonical loop agents + commands (edit here, then build)
│   ├── agents/                    # planner, coder, watchdog, verifier
│   └── commands/                  # next, steer, ask, new-ticket, orchestrate, reconcile
├── scripts/
│   └── build.sh                   # Regenerate harness outputs from source/
├── .claude/                     # Generated: Claude Code (harness requires it at root)
│   ├── agents/                    # Five agents: orchestrator, planner, coder, watchdog, verifier
│   └── commands/
├── .cursor/                     # Generated: Cursor (rules/ + commands/)
├── .codex/                      # Generated: Codex CLI (agents/ + prompts/)
├── .gemini/                     # Generated: Gemini CLI (skills/)
├── .github/                     # Issue templates, spec lint CI (GitHub requires it at root)
├── pyproject.toml               # `argos` console script; dependencies = [] (stdlib only runtime)
├── CLAUDE.md                    # Generated from argos/RULES.md (Claude Code reads this at root)
├── AGENTS.md                    # Generated from argos/RULES.md (Codex family convention)
└── ARGOS.md                     # Methodology doc
```

Edit `source/` and run `scripts/build.sh` again to regenerate the per harness directories. `argos/specs/` is the project's living spec, written by humans and the verifier, never by the coder. All five agents (including the orchestrator, specified in the CLI layer under `argos/specs/v1.0/agents/`) build from `source/agents/` into every harness directory.

Why the split between `argos/` and root: `.claude/`, `.cursor/`, `.codex/`, `.gemini/`, `.github/`, `CLAUDE.md`, and `AGENTS.md` are hardcoded by their respective harnesses and must live at the repo root. Everything else Argos owns is consolidated under `argos/` to keep the project root uncluttered.

## Status

Argos works **end to end**, validated by running it on a *separate* repo, not just on itself, through the full `init → queue → orchestrate → push → operator merge` flow with no workarounds. The stdlib only CLI, parallel worktree dispatch, escalation drain, and conservative finalization are all in use.

It is a working system with a **named backlog**, not an unfinished one. Open *design* questions are tracked as tickets rather than left implicit, for example the `STATE.md` authorship model (who may write which sections, and how the hook enforces it). Mechanical follow ups (status edge cases, self hosting docs, editor config for collapsing the harness directories, retrofit tooling for existing codebases) are likewise filed as tickets under `argos/specs/`.

File a GitHub issue if you hit friction on any harness. The experimental ones in particular need real usage to mature.
