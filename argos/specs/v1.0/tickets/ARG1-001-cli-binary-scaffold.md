# ARG1-001 — CLI binary scaffold + language ADR

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 1 (CLI installer)

## Intent

Stand up the `argos` CLI binary skeleton: argument parser, subcommand dispatch table, version output, help text. No subcommands implemented yet beyond `--version` and `--help`. File the ADR that picks the implementation language (Python vs. Rust vs. Go vs. Bash) and lock it before any other Epic-1 ticket starts coding against it.

## Context

PRD §Distribution lists `argos init / sync / status / attend` as the v1.0 public surface. ARCHITECTURE.md §Technology choices marks the language as TODO with four candidates. Every other ticket in this v1.0 release imports or invokes the CLI; without a binary entry point and a language decision, nothing else can land. This ticket is the dependency root of Epic 1 and a hard prerequisite for ARG1-020, ARG1-051, ARG1-053.

## Non-goals

- No subcommand implementations beyond `--version` / `--help`. Each subcommand has its own ticket.
- No installer/packaging pipeline (homebrew formula, npm publish, cargo crate). Packaging channel is its own follow-up ADR per PRD §Distribution.
- No shell completion scripts.

## Acceptance criteria

- [ ] `argos/specs/decisions/ADR-001-cli-language.md` exists with status `Accepted` naming the chosen language and the rejected alternatives with one-line reasons.
- [ ] `argos --version` exits 0 and stdout matches regex `^argos [0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?$`.
- [ ] `argos --help` exits 0 and stdout contains the strings `init`, `sync`, `status`, `attend`.
- [ ] `argos` (no args) exits non-zero and stderr contains the string `usage:`.
- [ ] `argos nonexistent-subcommand` exits non-zero and stderr contains the string `unknown`.

## Depends on

_none — root of Epic 1_

## Touches

- `argos/specs/decisions/ADR-001-cli-language.md` (new)
- `argos/cli/` (new directory; entry point + arg parser)
- `argos/cli/__init__.py` or `cmd/argos/main.go` or `src/main.rs` (TBD by ADR)
- `pyproject.toml` or `Cargo.toml` or `go.mod` (TBD by ADR)
- `argos/cli/tests/test_version.{py,rs,go}` (TBD by ADR)

## Parallelizable with

- ARG1-030 (verifier severity rubric — touches `.claude/agents/verifier.md` only)
- ARG1-040 (escalation schema — touches `argos/specs/v1.0/schemas/escalation.md` only)
- ARG1-050 (STATE.md block schema — touches `argos/specs/v1.0/schemas/state-block.md` and `argos/cli/state_parser.py` — but state_parser may collide depending on language layout; recheck after ADR-001)
