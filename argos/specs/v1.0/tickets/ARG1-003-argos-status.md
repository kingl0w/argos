# ARG1-003 — `argos status` integrity oracle

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 1 (CLI installer)

## Intent

Implement `argos status` as the single command that proves spec integrity. Exit 0 iff: STATE.md parses against the v1.0 block schema; every block's referenced ticket exists; `argos/config.toml` and `.argos/local.toml` parse; `argos/specs/escalations/` is empty (no undrained blocking escalations); and STATE.md's "Done this cycle" entries line up with the recent git log on the current branch. Exit non-zero with a one-screen diagnosis otherwise. This is PRD success criterion #5.

## Context

ARCHITECTURE.md §Invariants names `argos status` as the integrity oracle. v0.5 has `argos/scripts/argos-status.sh` (which ARG-001 fixed for exit codes); v1.0 reimplements inside the CLI binary so it can read the new block schema and config files.

## Non-goals

- No auto-fix. Status only diagnoses; `argos sync` reconciles.
- No network calls (no GitHub Issues check — that's `argos sync`'s job).
- No replacement of the v0.5 shell script in this ticket; deprecation/removal is a follow-up after migration.

## Acceptance criteria

- [ ] In a clean post-`argos init` repo with no tickets, `argos status; echo $?` prints `0`.
- [ ] After hand-corrupting `argos/specs/STATE.md` (delete a closing `<!-- /argos:entry -->` tag), `argos status; echo $?` prints a non-zero number; stderr contains `STATE.md` and `unclosed entry`.
- [ ] After dropping a malformed file at `argos/specs/escalations/blocking.md` (no frontmatter), `argos status; echo $?` prints a non-zero number; stderr names the file path.
- [ ] After dropping a well-formed blocking escalation at `argos/specs/escalations/ARG1-099-2026-04-26T12:00:00Z.md`, `argos status; echo $?` prints a non-zero number; stderr contains `undrained escalation`.
- [ ] `argos status --json` exits with the same code and emits a JSON object on stdout containing keys `state_md`, `config`, `escalations`, `git_alignment`, each with a `pass`/`fail` value.
- [ ] `argos status` completes in under 2 seconds on this repo (`time argos status` user+sys < 2.0).

## Depends on

- ARG1-001 (CLI scaffold)
- ARG1-040 (escalation schema — needed to validate escalation files)
- ARG1-050 (STATE.md block schema — needed to parse blocks)
- ARG1-053 (config split — needed to parse config files)

## Touches

- `argos/cli/commands/status.py` (or equivalent)
- `argos/cli/integrity.py` (or equivalent — checker module)
- `argos/cli/tests/test_status.py` (or equivalent)

## Parallelizable with

- ARG1-002 (init — separate command)
- ARG1-004 (sync — separate command)
- ARG1-005 (attend — separate command)
- ARG1-011 (/orchestrate slash command)
- ARG1-022 (parallel dispatch — separate module)
- ARG1-054 (cycle close — separate command)

## Plan

Implement `argos status` as a stdlib-only integrity oracle (ADR-001/002).

**Module split**
- `argos/cli/integrity.py` — pure checker. `run_checks(repo_root, *, now=None) -> IntegrityReport`. Four `CheckResult` records keyed `state_md`, `config`, `escalations`, `git_alignment`, each `passed: bool` + `messages: list[str]`. No I/O beyond reading repo files + `git log`.
- `argos/cli/commands/status.py` — argparse (`--json`, `--repo-root`), resolves repo root via `git rev-parse --show-toplevel` (fallback CWD), formats output, returns exit code (0 iff all pass).
- Wire `status` in `argos/cli/__main__.py` (replace the ARG1-003 stub).
- `argos/cli/tests/test_status.py` — unittest, one tmp repo per AC.

**Check semantics**
1. `state_md` — parse `argos/specs/STATE.md` via `state_parser.parse`; on `StateBlockError` fail with `STATE.md: {err}` (carries `unclosed entry`). Then every parsed block's `ticket` must resolve to a file `{ticket}.md`/`{ticket}-*.md` under `argos/specs/tickets/` (fallback `argos/specs/v1.0/tickets/`).
2. `config` — require `argos/config.toml` (or `.template`) to exist; load project + local (`.argos/local.toml`/`.template`) via `config.load` with a swallowed warn stream; fail on `ConfigParseError` (names file) or `Config.validate()` type errors.
3. `escalations` — every `*.md` under `argos/specs/escalations/` except `README.md`/dotfiles must pass `escalation_validator.validate` (malformed → fail, names path). A valid `severity: blocking` file with no `## Resolution`/`**Drained:**` marker → fail with `undrained escalation` + path.
4. `git_alignment` — ticket of each block under `## Done this cycle` must appear in `git log` reachable from HEAD (cap `-n 500`). Not-a-git-repo or unparseable STATE.md → skipped (pass).

**Output**
- Text mode: success → one stdout summary line; failure → per-check diagnostics to stderr, exit 1.
- `--json`: JSON object on stdout `{ok, state_md, config, escalations, git_alignment, diagnostics}` with each check key = `"pass"`/`"fail"`; same exit code.
