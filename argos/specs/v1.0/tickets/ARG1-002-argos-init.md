# ARG1-002 — `argos init` scaffolds specs, config, hooks, merge driver

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 1 (CLI installer)

## Intent

Implement `argos init`: scaffold `argos/specs/` from templates, write `argos/config.toml` with defaults, create `.argos/local.toml` from a template, register the STATE.md custom git merge driver, and append `.argos/` to `.gitignore`. Idempotent: rerunning on an already-initialized repo prints what it found and exits 0 without overwriting.

## Context

ARCHITECTURE.md §Components/Config and §STATE.md format require both config files plus the merge driver to exist before any orchestrator run. PRD §Distribution names `argos init` as the entry point users will invoke first. This ticket wires together the artifacts produced by ARG1-050, ARG1-052, ARG1-053.

## Non-goals

- No template editing. Templates ship from ARG1-050 and ARG1-053 as-is.
- No interactive prompts. `argos init` runs unattended; flags configure non-defaults.
- No project-name detection beyond reading the git remote (default to current directory name on failure).

## Acceptance criteria

- [ ] `argos init` in a fresh directory exits 0 and stdout contains `initialized`.
- [ ] After `argos init`, `test -f argos/specs/STATE.md && test -f argos/specs/PRD.md && test -f argos/specs/ARCHITECTURE.md` exits 0.
- [ ] After `argos init`, `test -f argos/config.toml && test -f .argos/local.toml` exits 0.
- [ ] After `argos init`, `grep -Fxq '.argos/' .gitignore` exits 0.
- [ ] After `argos init`, `git config --get merge.argos-state.driver` exits 0 and prints a non-empty value.
- [ ] Re-running `argos init` in the same directory exits 0 and stdout contains `already initialized`; no file mtimes change.
- [ ] `argos init --force` re-runs and overwrites scaffolded files (mtimes change), but never touches existing tickets under `argos/specs/tickets/`.

## Depends on

- ARG1-001 (CLI scaffold)
- ARG1-050 (STATE.md block schema — needed for STATE.md template)
- ARG1-052 (merge driver — registered by init)
- ARG1-053 (config split — both config files scaffolded by init)

## Touches

- `argos/cli/commands/init.py` (or equivalent — new)
- `argos/cli/templates/` (new directory holding scaffold sources)
- `argos/cli/tests/test_init.py` (or equivalent)

## Parallelizable with

- ARG1-003 (status command — separate command file)
- ARG1-004 (sync command — separate command file)
- ARG1-005 (attend command — separate command file)
- ARG1-010 (orchestrator agent definition — `.claude/agents/`)
- ARG1-020 (worktree spawn helper — `argos/cli/worktree.py`)
- ARG1-040 (escalation schema)
