# Argos — Architecture

**Scope:** the whole repo. The CLI layer (orchestrator, worktree dispatch, escalations, STATE block schema) has its own detailed, versioned architecture at `argos/specs/v1.0/ARCHITECTURE.md`; this file records the repo-wide shape and invariants and defers to the v1.0 doc for CLI-layer specifics.

## System shape

Argos is two complementary layers over the same spec tree:

1. **Harness scaffold.** Agent and command definitions authored once under `source/` and built by `scripts/build.sh` into the native formats of Claude Code (`.claude/`), Cursor (`.cursor/`), Codex CLI (`.codex/`), and Gemini CLI (`.gemini/`). Root `CLAUDE.md` and `AGENTS.md` are built copies of `argos/RULES.md`.
2. **Python CLI** (`argos/cli/`, stdlib-only per ADR-001). Drives the same loop headlessly: queue management, parallel worktree dispatch, verification write-back, escalation drain, reconciliation.

Specs are the source of truth; code follows specs. A ticket moves planner → coder → watchdog → verifier; sessions push branches and never merge.

## Spec trees

- `argos/specs/` (this tree) — the repo's living spec: `STATE.md`, flat `tickets/`, `decisions/` (ADRs), `escalations/`, `cycles/`, `dispatch/`. This is also the layout `argos init` scaffolds onto foreign repos.
- `argos/specs/v1.0/` — the versioned spec set for the CLI layer, with its own `STATE.md`, `tickets/` (ARG1-*), `agents/`, and `schemas/`. `argos/cli/spec_paths.py` resolves the v1.0 tree when present, so bare CLI commands operate on it in this repo and on the flat tree in scaffolded repos.

## Invariants

- **Generated files are never edited directly.** `source/` and `argos/RULES.md` are canonical; the harness directories, `CLAUDE.md`, and `AGENTS.md` are build outputs of `scripts/build.sh`.
- **Stdlib only** in `argos/cli/` (ADR-001), enforced by `argos lint-imports`. The target repo's own conventions live in `argos/conventions.md` and are not constrained by this.
- **Only the verifier writes `STATE.md`** during a loop run; humans write it on out-of-loop edits. Enforced by the pre-commit hook (ARG1-032).
- **Sessions never merge.** Worktree sessions build, verify, and push; the operator owns the merge.
- **If `argos status` exits zero**, STATE.md, tickets, config, escalations, and git are mutually consistent.

## Technology choices

Python ≥ 3.9, standard library only (ADR-001). Shell scripts under `argos/scripts/` are v0.5-era helpers being superseded by CLI subcommands. Distribution channel (pip / pipx / binary) is deliberately undecided — see ADR-001 §Scope.

## What this architecture deliberately does not support

- A hosted service or daemon; everything runs locally in the operator's repo.
- Silent merges or auto-applied spec fixes (`argos sync` reports, the operator ratifies).

## Known drift

Tracked in `STATE.md` §Known drift, not here.
