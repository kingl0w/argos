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

## Plan

### Decision summary

**ADR-001 will ratify Python as the implementation language for the argos CLI**, formalizing the de facto state. Reasoning is captured in detail in the ADR; the load-bearing facts:

1. **Existing code is Python.** ARG1-030 (`argos/cli/verifier_parser.py`), ARG1-040 (`argos/cli/escalation_validator.py`, `argos/cli/escalation-validate` shim), and ARG1-050 (`argos/cli/state_parser.py`, `argos/cli/__main__.py`, `argos/cli/commands/state_parse.py`) all merged as stdlib-only Python on the assumption ADR-001 would name Python. STATE.md §Known drift (entry id `2026-04-26T00:00:00Z-ARG1-030-shim`) explicitly defers the layout question to this ticket. Picking any non-Python language throws away three merged tickets and re-opens their ACs.
2. **Stdlib-only is a sustainable contract.** The three existing modules use only `argparse`, `re`, `dataclasses`, `pathlib`, `datetime`, `json`, `sys`. No third-party runtime deps means `python3` (3.10+) is the only install requirement — no `pip install` step in the critical path, no virtualenv friction for the orchestrator subprocess invocations described in ARCHITECTURE.md §Orchestrator → Session.
3. **Packaging story is good enough for v1.0 — but this ticket does NOT close the PRD §Distribution packaging-channel TODO.** `pyproject.toml` + `console_scripts` is *scaffolding*: it makes `pip install -e .` and `pipx install .` work for dogfood-velocity local development and gives the in-repo launcher `argos/cli/argos` something to defer to. It does not commit Argos to PyPI as the published-distribution channel, does not pick between pip / pipx / homebrew formula / standalone binary (PyOxidizer / shiv / Nuitka) for end-user install, and does not establish a release pipeline. PRD §Distribution stays open. ADR-001 explicitly scopes itself to "language + project-manifest format" and explicitly does NOT own the packaging-channel decision; that is a follow-up ADR (ADR-NNN-packaging-channel) gated on real users — premature commitment now would lock in a channel before we know whether users want `brew install argos` or `pipx install argos` or a curl-bash installer. The ADR's Consequences section names this follow-up ADR as required-before-1.0.0-release.
4. **Contributor onboarding cost.** Target users are solo developers running Claude Code, which already requires a working Python toolchain (Claude Code's own helper scripts and many user `.claude/` hooks are Python). Switching to Rust or Go adds a toolchain (rustup, go) that those users likely don't have. Python is the lowest-friction language for this audience.
5. **Python floor: `>=3.9`, not 3.10.** The floor's reason is *concrete stdlib feature use*, not a default round-up: `argparse` subparser dispatch, `re`, `dataclasses`, `pathlib`, `datetime.fromisoformat`, and PEP 604 / PEP 585 generic syntax (`int | None`, `list[str]`, `dict[str, str]`). All existing modules write those generics under `from __future__ import annotations`, which makes them strings — evaluated lazily, so they run on 3.7+. Removing `__future__` and evaluating PEP 604 unions at runtime would require 3.10. We are NOT removing `__future__`, and no existing or planned ARG1-0NN module uses `match` statements, `tomllib` (added 3.11), `ExceptionGroup` (3.11), `Self` (3.11), or `dataclasses(slots=True)` (3.10). The honest floor is 3.9 (where PEP 585 builtin generics like `list[str]` became valid as runtime annotations and where `dict | str`-as-string parses cleanly). 3.10 is reserved for if-and-when a future ticket actually needs `match` or runtime `X | Y`. Future contributors editing `pyproject.toml`: do not raise the floor without naming the stdlib feature that demands it. ADR-001 names this explicitly under Consequences.

6. **Rejected alternatives** (one-line each, expanded in ADR):
   - **Rust** — single-binary distribution is attractive but adds toolchain cost and rewrite cost; v1.0 is dogfood-velocity, not distribution-velocity.
   - **Go** — same single-binary upside as Rust, less common among the target audience (Python/JS-leaning), still requires rewriting three merged modules.
   - **Bash** — fundamentally inadequate for the orchestrator's concurrency, JSON shape validation, and structured-output parsing requirements; the existing shim is a stop-gap, not a target.

### Files this ticket creates / modifies

All paths are within the `Touches:` scope. The ticket Touches says "`pyproject.toml` *or* `Cargo.toml` *or* `go.mod` (TBD by ADR)" — Python is chosen, so `pyproject.toml` at the repo root is the manifest.

| Path | Op | Purpose |
|---|---|---|
| `argos/specs/decisions/ADR-001-cli-language.md` | new | The decision record. Status `Accepted`. Sections: Context, Options (Python/Rust/Go/Bash), Recommendation, Decision (Python), Consequences. |
| `pyproject.toml` | new | PEP 621 project metadata. `name="argos"`, `version="0.1.0"`, `requires-python=">=3.9"`, `[project.scripts] argos = "argos.cli.__main__:main"`. No runtime dependencies. Optional `[project.optional-dependencies] dev = ["pytest"]`. |
| `argos/cli/__init__.py` | edit | Add `__version__ = "0.1.0"` constant. Keep the existing one-line module docstring. Single source of truth for the version string. |
| `argos/cli/__main__.py` | edit | Replace minimal dispatcher with an argparse-based one. Top-level parser owns `--version` (prints `argos {__version__}`) and `--help`. Subparsers register: `init`, `sync`, `status`, `attend` (stubs that print "not yet implemented" and exit 2), `state-parse` (delegates to existing `argos.cli.commands.state_parse:main`), `verifier-parse` (delegates to existing `argos.cli.verifier_parser:main`), `escalation-validate` (delegates to existing `argos.cli.escalation_validator:main`). No-args → print `usage: argos <subcommand> [args...]` to stderr, exit 2. Unknown subcommand → `argos: unknown subcommand: {sub}` to stderr, exit 2. |
| `argos/cli/argos` | edit | Replace the bash shim (currently only handles `verifier-parse`) with a unified launcher: a Python `#!/usr/bin/env python3` script that prepends the repo root to `sys.path` and calls `argos.cli.__main__:main`. Same shebang style as the existing `escalation-validate` shim. Stays executable (chmod +x preserved). |
| `argos/cli/tests/test_version.py` | new | Subprocess-level tests for the five ACs, invoked against `argos/cli/argos` via absolute path. |

### Subcommand-stub contract

`init`, `sync`, `status`, `attend` are not implemented in this ticket — each has its own ticket (ARG1-002/004/003/005). The stubs exist solely so `argos --help` lists them (AC#3) and so the dispatch table has a registered name for them. Each stub's body is two lines: write `argos {sub}: not yet implemented (see ARG1-00X)` to stderr, return 2. No flags beyond `-h/--help`. ADR for each lives in its own ticket.

The three already-implemented subcommands (`state-parse`, `verifier-parse`, `escalation-validate`) keep their current entry points and tests; the new dispatcher just adds a unified front door. Existing tests continue to pass unchanged.

### Help-text contract

`argos --help` output must contain the literal strings `init`, `sync`, `status`, `attend` (AC#3). Because argparse's auto-generated help lists subparser names verbatim, registering the four subparsers is sufficient — no manual help-string assembly. We will not rely on description text containing those strings; the subparser registration is the contract.

### Version-string contract

AC#2 regex: `^argos [0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?$`. We emit `argos 0.1.0` (matches `^argos 0\.1\.0$`). The version comes from `argos.cli.__version__`. Future bumps update one line in `argos/cli/__init__.py` and one line in `pyproject.toml`; CI will eventually enforce parity but that is out of scope for ARG1-001.

### Test plan (`argos/cli/tests/test_version.py`)

All five tests invoke `argos/cli/argos` as a subprocess with absolute path, no shell, capturing stdout/stderr separately:

1. `test_version_exits_zero_and_matches_regex` — runs `argos --version`, asserts exit 0, asserts stdout matches `^argos \d+\.\d+\.\d+(-[a-z0-9.]+)?$\n?`.
2. `test_help_exits_zero_and_lists_subcommands` — runs `argos --help`, asserts exit 0, asserts each of `init`, `sync`, `status`, `attend` appears in stdout.
3. `test_no_args_exits_nonzero_with_usage` — runs `argos` with no args, asserts exit nonzero, asserts stderr contains the substring `usage:`.
4. `test_unknown_subcommand_exits_nonzero` — runs `argos definitely-not-a-real-subcommand`, asserts exit nonzero, asserts stderr contains the substring `unknown`.
5. `test_known_stub_subcommand_exits_nonzero_until_implemented` — runs `argos status`, asserts exit nonzero (sanity: stub returns 2). Not an AC; guards against accidentally promoting a stub to passing.

Tests use the same path-resolution pattern as `argos/cli/tests/test_state_parser.py` (`Path(__file__).resolve().parents[3]` for repo root). They are invoked via `python3 -m unittest argos.cli.tests.test_version -v` or `pytest argos/cli/tests/test_version.py`. Both work; the AC harness uses unittest because pytest is not yet a declared dev dep at the time AC runs.

Wait — re-reading: ARG1-030's verification used unittest, and `pyproject.toml` adds pytest as an *optional* dev dep. To avoid an external-dep requirement at AC time, `test_version.py` will be a `unittest.TestCase` subclass, runnable with `python3 -m unittest argos.cli.tests.test_version`. This matches the convention set by ARG1-030 and ARG1-050.

### What this ticket does NOT do (explicit non-goals beyond ticket §Non-goals)

- Does not implement `argos init` / `argos sync` / `argos status` / `argos attend` bodies. Stubs only.
- Does not add a `[tool.pytest.ini_options]` block — keep `pyproject.toml` minimal; pytest config lives elsewhere when ARG1-002+ need it.
- Does not delete `argos/cli/escalation-validate`. That shim has its own removal disposition tied to ARG1-041 (escalation writer). Touching it now is out of scope.
- Does not add CI for version-string parity between `pyproject.toml` and `__init__.py`. That is a follow-up ticket if it bites.
- Does not add `argos/__init__.py` changes (the package-init for the top-level `argos/` dir, currently used to make `argos.cli` importable). Already present from ARG1-030; no edit needed.

### Watchdog hints

- The plan DOES touch `pyproject.toml` (new file at repo root). This is a manifest, not a runtime dependency add — there are zero entries in `[project.dependencies]`. Watchdog should not flag this as a silent-dep-add violation.
- The plan modifies `argos/cli/argos` from bash to Python. This is the explicit disposition recorded in STATE.md §Known drift; not a drive-by refactor.
- The plan modifies `argos/cli/__main__.py` (already exists from ARG1-050). The existing `state-parse` dispatch remains functional — the change is additive (adds argparse + stubs + new subparsers) plus a refactor of the no-args / unknown-subcommand error paths to satisfy ACs #4 and #5.

### Risks / known unknowns

- **`argparse` exits 2 with `error: ...` on unknown subcommand.** The default message format is `usage: argos ... \n argos: error: argument {sub}: invalid choice: 'foo'`. The string `unknown` is not in the default message. We must either intercept and re-emit, or pass `add_help=True` and override `error()` on the parser. Plan: subclass `ArgumentParser` with an overridden `error()` that emits `argos: unknown subcommand: {arg}` to stderr when the failure is an `invalid choice` for the subparsers dest. Simpler alternative: use `parse_known_args()` plus manual dispatch. The simpler alternative is preferred — it gives full control over both the no-args and unknown-subcommand error paths and keeps the help auto-generation.
- **`argparse` `--version` action calls `sys.exit(0)` after printing, which short-circuits the dispatcher.** Standard library behavior; matches AC#1.
- **`argparse` `--help` exits 0** by default; matches AC#2.
- **Concurrent edits** to `argos/cli/__main__.py` between ARG1-050's merge and this ticket: STATE.md confirms ARG1-050 is merged on `main`; this branch is up to date. No concurrent-edit conflict expected.
