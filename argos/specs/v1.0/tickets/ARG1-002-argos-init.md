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

## Plan

**Author:** planner (ARG1-002 worktree) · **Date:** 2026-06-13

### Approach

`argos init` is a Python subcommand (`argos/cli/commands/init.py`) wired into the
dispatcher at `argos/cli/__main__.py` (the same integration seam ARG1-053 used for
`config`). It scaffolds the *current* repo (CWD, or `--path`) from package-shipped
templates, registers the ARG1-052 merge driver, and drops an idempotency sentinel.

### Scaffold-source location

`argos/cli/templates/` holds the scaffold sources, copied **verbatim** (byte-for-byte,
via `cp`) from the canonical ARG1-050 / ARG1-053 templates so they travel with the
package (standard package-data co-location) and `argos init` works regardless of CWD:

| `argos/cli/templates/` file | source (as-is) | rendered/copied to |
|---|---|---|
| `STATE.md.template` | `argos/specs/STATE.md.template` | `argos/specs/STATE.md` (placeholders rendered) |
| `PRD.md.template` | `argos/specs/PRD.md.template` | `argos/specs/PRD.md` (rendered) |
| `ARCHITECTURE.md.template` | `argos/specs/ARCHITECTURE.md.template` | `argos/specs/ARCHITECTURE.md` (rendered) |
| `config.toml.template` | `argos/config.toml.template` | `argos/config.toml` (verbatim) |
| `local.toml.template` | `.argos/local.toml.template` | `.argos/local.toml` (verbatim) |

Spec templates carry `{{PROJECT}}/{{PREFIX}}/{{DESC}}/{{DATE}}` placeholders (their
ARG1-050 design) and are rendered; config templates are static defaults (their ARG1-053
design) and are copied as-is — honoring "templates ship as-is" by respecting each
template's own substitution contract.

### Steps performed by `argos init`

1. **Idempotency.** Sentinel `.argos/.initialized` (gitignored). If present and no
   `--force`: print `already initialized` + an inventory of found/missing files, exit 0,
   touch nothing (satisfies AC#6's no-mtime-change).
2. **Identity.** Project name = git `origin` basename, else CWD dir name (per Non-goals).
   Prefix derived (2–4 uppercase letters). `--name/--prefix/--desc` override; non-interactive.
3. **Scaffold dirs/files.** Create `argos/specs/tickets/` (with `.gitkeep` only when empty —
   never overwritten, AC#7), render spec templates, copy config templates.
4. **`.gitignore`.** `config.ensure_gitignore_entry(repo_root, ".argos/")` — idempotent,
   adds the exact `.argos/` whole line (AC#4).
5. **Merge driver.** `git init -q` if not already a repo; copy `state-merge-driver.sh` into
   `argos/scripts/`; register `merge.argos-state.{name,driver,recursive}`; add the STATE.md
   `merge=argos-state` lines to `.gitattributes` (AC#5). git-absent path warns, non-fatal.
6. **Hooks (title scope).** Best-effort install of the ARG1-032 pre-commit hook into
   `.git/hooks/pre-commit` (sentinel-delimited block); never raises.
7. **Sentinel + summary.** Write sentinel, print `initialized` (AC#1).

`--force` skips the sentinel check and rewrites generated files (new mtimes, AC#7) while
leaving `argos/specs/tickets/` contents untouched.

### Files

| Path | Op | Notes |
|---|---|---|
| `argos/cli/templates/*` | new | 5 scaffold sources, byte-identical copies of the canonical templates |
| `argos/cli/commands/init.py` | new | the command |
| `argos/cli/tests/test_init.py` | new | 8 stdlib `unittest` tests (subprocess via the launcher) |
| `argos/cli/__main__.py` | edit | one dispatch branch for `init`; drop `init` from the stub table; docstring touch-up |

Non-`Touches:` edit justification — `argos/cli/__main__.py` is the only seam that lets the
subcommand exist (Intent requires `argos init` to dispatch); same pre-authorized pattern as
ARG1-053's `config` wiring. No dep adds (ADR-001 stdlib-only; `lint-imports` clean).

## Verification

**Verified:** 2026-06-13 · **Decision:** pass

### Acceptance criteria (real output quoted)

All run in a fresh `mktemp -d` via the launcher `argos/cli/argos`.

1. **`argos init` → exit 0, stdout contains `initialized` — PASS.**
   stdout line: `Argos initialized 'tmp.3z18wmwwsq' (prefix TMPZ) at /tmp/...`; `exit=0`.
2. **Spec files exist — PASS.** `test -f argos/specs/STATE.md && … PRD.md && … ARCHITECTURE.md` → `exit=0`.
3. **Config files exist — PASS.** `test -f argos/config.toml && test -f .argos/local.toml` → `exit=0`.
4. **`.gitignore` has `.argos/` — PASS.** `grep -Fxq '.argos/' .gitignore` → `exit=0`.
5. **Merge driver registered — PASS.** `git config --get merge.argos-state.driver` →
   `argos/scripts/state-merge-driver.sh %O %A %B %P %L` (`exit=0`, non-empty).
6. **Re-run idempotent — PASS.** Second run `exit=0`, stdout contains `already initialized`;
   `STATE.md` / `config.toml` / `local.toml` mtimes byte-identical before/after.
7. **`--force` — PASS.** STATE.md mtime changes; an operator-authored
   `argos/specs/tickets/REAL-001.md` keeps its content and (epoch-stamped) mtime.

### Test run

**Command:** `python3 -m unittest argos.cli.tests.test_init -v` → `Ran 8 tests … OK` (8 pass, 0 fail).
**Regression:** `python3 -m unittest discover -s argos/cli/tests -p 'test_*.py'` → `Ran 341 tests … OK`.
**Lint (ADR-001):** `argos lint-imports argos/cli/commands/init.py` and `… test_init.py` → exit 0 each.

### Findings

- 0 critical, 0 major, 0 minor. No dep adds; scope limited to the Touches list plus the
  pre-authorized dispatcher edit.
