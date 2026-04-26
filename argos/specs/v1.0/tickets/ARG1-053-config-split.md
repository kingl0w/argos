# ARG1-053 — Config split: `argos/config.toml` + `.argos/local.toml` + loader

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 6 (STATE.md migration + config split)

## Intent

Define the v1.0 config split per ARCHITECTURE.md §Contracts/Config split. Ship `argos/config.toml.template` (committed defaults — project-level) and `.argos/local.toml.template` (gitignored — per-developer), plus a loader (`argos/cli/config.py`) that reads both, applies local-overrides-project on key collision, and warns on unknown keys without failing. Also ensure `.argos/` is added to `.gitignore` (idempotent). Schema doc enumerates every supported key with type, default, and which file it belongs in.

## Context

ARCHITECTURE.md §Contracts/Config split specifies the keys per file. PRD §Target user calls out the project-vs-local split as the architectural seam that keeps team support possible without delivering it in v1.0.

## Non-goals

- No env-var override layer (TODO if needed; not required by current consumers).
- No interactive config editing UI (operators edit the TOML files directly).
- No schema migration on key renames (none expected within v1.0).

## Acceptance criteria

- [ ] `test -f argos/config.toml.template && test -f .argos/local.toml.template` exits 0; both files parse as valid TOML.
- [ ] `argos/config.toml.template` contains keys `project.name`, `project.prefix`, `orchestrator.max_parallel`, `orchestrator.independence_strategy`, `verifier.auto_fix_retries`, `escalation.require_attend_before_merge`; verified by `grep -Fc` per key.
- [ ] `.argos/local.toml.template` contains keys `operator.name`, `escalation.webhook_url`, `harness.claude_code_binary`, `telemetry.opt_in`; verified by `grep -Fc` per key.
- [ ] `argos config get orchestrator.max_parallel` exits 0 and prints the integer default `3` after `argos init`.
- [ ] After setting `orchestrator.max_parallel = 5` in `.argos/local.toml`, `argos config get orchestrator.max_parallel` prints `5` (local overrides project).
- [ ] `argos config get nonexistent.key; echo $?` prints non-zero; stderr contains `key not found`.
- [ ] After `argos init`, `grep -Fxq '.argos/' .gitignore` exits 0; running init again does not duplicate the line (`grep -Fc '.argos/' .gitignore` returns `1`).
- [ ] `argos config validate` exits 0 on a clean config and exits non-zero with a typed-error message when `orchestrator.max_parallel` is set to a non-integer.
- [ ] An unknown key in either TOML file produces a stderr warning containing `unknown config key` but does not fail any command; verified by setting `orchestrator.future_key = "x"` and observing exit 0 from `argos config get orchestrator.max_parallel`.
- [ ] `argos/specs/v1.0/schemas/config.md` documents every key with type and default; loader's known-keys list is sourced from this document (or a generated file derived from it).

## Depends on

- ARG1-001 (CLI scaffold)

## Touches

- `argos/config.toml.template` (new)
- `.argos/local.toml.template` (new)
- `argos/cli/config.py` (or equivalent — new)
- `argos/cli/commands/config.py` (or equivalent — `get`/`validate` subcommands)
- `argos/specs/v1.0/schemas/config.md` (new)
- `.gitignore` (modify — append `.argos/` if absent)
- `argos/cli/tests/test_config.py` (or equivalent)

## Parallelizable with

- ARG1-010 (orchestrator agent)
- ARG1-020 (worktree spawn — depends on this ticket but separate module)
- ARG1-030 (verifier rubric)
- ARG1-040 (escalation schema)
- ARG1-050 (state block schema — different module)
- ARG1-051 (state-append helper)
- ARG1-052 (merge driver)
