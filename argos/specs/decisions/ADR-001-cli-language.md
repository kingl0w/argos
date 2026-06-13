# ADR-001 — CLI implementation language

**Date:** 2026-04-26
**Status:** Accepted
**Deciders:** ianfrushon@gmail.com

## Context

Argos v1.0 ships a CLI binary (`argos init / sync / status / attend`, plus internal subcommands like `state-parse`, `verifier-parse`, `escalation-validate`) that orchestrates the four-agent loop and is invoked both interactively by the operator and as a subprocess by the orchestrator agent (per ARCHITECTURE.md §Orchestrator → Session). `ARCHITECTURE.md` §Technology choices marks the implementation language as TODO with four candidates (Python, Rust, Go, Bash) and gates further Epic-1 work on this decision.

Three v1.0 tickets have already merged with provisional Python implementations on the assumption that ADR-001 would land on Python:

- ARG1-030 — `argos/cli/verifier_parser.py`, `argos/cli/argos` (bash shim), `argos/cli/tests/test_verifier_parser.py`
- ARG1-040 — `argos/cli/escalation_validator.py`, `argos/cli/escalation-validate` (sh shim), `argos/cli/tests/test_escalation_validator.py`
- ARG1-050 — `argos/cli/state_parser.py`, `argos/cli/__main__.py`, `argos/cli/commands/state_parse.py`, `argos/cli/tests/test_state_parser.py`

`argos/specs/v1.0/STATE.md` §Known drift (entry id `2026-04-26T00:00:00Z-ARG1-030-shim`) records the bash `argos` shim and the package-init files as drift to be resolved by this ticket. The decision now is whether to ratify Python (making those modules canonical) or pick another language (making them throwaway).

The constraints that bear on this decision:

- **Audience.** Solo developers running Argos against their own repos via Claude Code (PRD §Target user). Their machines reliably have `python3`; they often do not have `rustup` or `go`.
- **Operator subprocess model.** The orchestrator spawns sessions via `argos run-session ...`; tight start-up latency is preferable, but the orchestrator runs locally with no per-call cold-start budget — it is not a serverless context.
- **Maintainer bandwidth.** Single maintainer (PRD §Constraints/Resource). Rewrites are expensive in calendar time even when they are easy in line count.
- **Scope of this ADR.** Language and project-manifest format only. ADR-001 does NOT pick the published-distribution channel (pip / pipx / homebrew / standalone binary). That is a separate ADR (ADR-NNN-packaging-channel), gated on real users and required before any 1.0.0 release.

## Options

### Option A — Python (3.9+, stdlib-only)

**Pros:**
- Three v1.0 modules and their tests are already written in Python; ratifying it costs nothing.
- Stdlib coverage of every CLI need (argparse, re, dataclasses, pathlib, json, datetime) means no `pip install` step in the orchestrator's critical path; `python3` is the only install requirement.
- Available on every dev machine targeted by Claude Code's audience.
- `pyproject.toml` + `console_scripts` gives `pip install -e .` and `pipx install .` for local development without committing to a specific published channel.

**Cons:**
- No single-binary distribution out of the box. Solving that needs a follow-up tool (PyOxidizer / shiv / Nuitka) and is part of the packaging-channel ADR.
- `python3` is *usually* present but not universal on minimal Linux containers; users of those environments will need to install it.
- Run-time type-annotation evaluation rules diverge across 3.9 / 3.10 / 3.11; we mitigate by using `from __future__ import annotations` in every module so PEP 604 / PEP 585 generics are stringified.

### Option B — Rust

**Pros:**
- Single static binary, trivially distributable.
- Strong type system catches a class of bugs the dynamic Python won't.
- Ecosystem (clap for arg parsing, serde, tokio) is excellent.

**Cons:**
- Throws away three merged Python modules (~600 lines + tests). Each must be rewritten and re-verified against its original ACs.
- Requires `rustup` on contributor machines. Most of the target audience does not have it.
- Compile-time cost on every change; iteration loop is slower than Python's.
- Maintainer is single-person; rewrite cost is real.

### Option C — Go

**Pros:**
- Single static binary like Rust, with a faster build loop.
- Standard library covers most CLI needs (`flag`, `encoding/json`, etc.).
- Concurrency primitives (goroutines, channels) map cleanly to the orchestrator's parallel-session model.

**Cons:**
- Same rewrite cost as Rust for the three merged modules.
- `go` toolchain less common among the target audience than Python.
- Goroutine concurrency is overkill: ARCHITECTURE.md §Concurrency primitive specifies OS-level processes coordinated via the file system, not in-process concurrency.

### Option D — Bash

**Pros:**
- Zero runtime dependency; ships with every Unix.
- The existing `argos/cli/argos` shim is bash; precedent exists for the launcher pattern.

**Cons:**
- Cannot reasonably express the orchestrator's responsibilities: structured-output validation (JSON / frontmatter parsing), concurrent-writer semantics around STATE.md, ISO-8601 parsing, dataclass-shaped findings. The existing reference parsers would each become hundreds of lines of `awk`/`sed`/`jq`.
- Error handling and exit-code discipline are weak relative to a real language.
- Cross-platform fragility (macOS bash 3.2 vs. GNU bash 5.x).

## Recommendation

**Option A — Python (3.9+, stdlib-only).** It ratifies the de facto state, costs zero rewrite, demands the smallest install footprint on contributor machines, and fits the maintainer-bandwidth constraint. Single-binary distribution is desirable but is a packaging concern, not a language concern, and is appropriately deferred to a follow-up ADR.

## Decision

**Accepted: Python, with the following constraints:**

1. **Floor: `requires-python = ">=3.9"`.** This floor is set by stdlib feature use, not by default round-up:
   - PEP 585 builtin generics (`list[str]`, `dict[str, str]`) used in existing modules — valid in annotations from 3.9.
   - PEP 604 union syntax (`int | None`) used in existing modules under `from __future__ import annotations`, so it is a *string* at runtime; this works on 3.7+ but the codebase standardizes on 3.9 to match builtin-generics availability.
   - No module uses `match` (3.10), `tomllib` (3.11), `ExceptionGroup` (3.11), `typing.Self` (3.11), or `dataclasses(slots=True)` (3.10).
   - Future contributors: do not raise this floor without naming the specific stdlib feature that demands it. Document the reason in this ADR's amendment trail or supersede with a new ADR.

2. **Stdlib-only at runtime.** Zero entries in `[project.dependencies]` in `pyproject.toml`. Any future need for a third-party runtime dependency requires an ADR. Test-only dev dependencies (`pytest`) live in `[project.optional-dependencies] dev` and are not part of the install critical path.

3. **Project manifest: `pyproject.toml` (PEP 621).** With a `[project.scripts] argos = "argos.cli.__main__:main"` console-script entry. This is the local-development entry point.

4. **Package layout: `argos/cli/`.** Existing layout, kept. The `argos/` directory remains a dual-purpose tree (Python package + spec docs under `argos/specs/`); the `__init__.py` files at `argos/`, `argos/cli/`, and `argos/cli/tests/` are the markers that make the Python import resolution work. STATE.md's drift entry on those files is closed by this decision.

5. **Bash shim `argos/cli/argos` is replaced by a Python launcher** in this ticket. The escalation shim `argos/cli/escalation-validate` is left in place; its disposition is bound to ARG1-041 and out of scope here.

## Consequences

### What this decision establishes

- Every Argos CLI surface is implemented in Python ≥3.9 with stdlib only.
- The version of record lives in `argos/cli/__init__.py` as `__version__`; `pyproject.toml` mirrors it.
- All three already-merged provisional modules (`verifier_parser.py`, `escalation_validator.py`, `state_parser.py`) are now canonical, not provisional.
- STATE.md §Known drift entries scoped to "pending ADR-001" can be closed by ARG1-001's verification.

### What this decision does NOT establish

- **Published distribution channel.** Whether end users get Argos via `pipx install argos`, `brew install argos`, a single self-extracting binary, or `curl | sh` is open. Required follow-up: **ADR-NNN-packaging-channel**, which must land before any 1.0.0 release. PRD §Distribution (the "TODO — npm vs. homebrew vs. cargo vs. standalone binary" line) remains open.
- **Release tooling.** No commitment to a build/publish pipeline (`build`, `twine`, `cibuildwheel`, GitHub Actions release workflow) is made here. That belongs with the packaging ADR.
- **Test framework.** Tests use `unittest` from the stdlib (precedent: ARG1-030, ARG1-050). `pytest` is allowed as an optional dev dependency for ergonomics but is not required to run the AC verification.

### What becomes harder

- A future "we want a single binary" decision must contend with a Python codebase (PyOxidizer / shiv / Nuitka) rather than picking a natively-static language up front. This is a known tradeoff and is judged acceptable.
- Adding a runtime dependency is now an ADR-gated decision; convenience libraries that would be one-line `cargo add` calls in Rust now require justification.

### What becomes easier

- Iteration loop is fast (no compile step).
- Contributors with Python literacy (the dominant case for the target audience) can read and modify the orchestrator without learning a new language.
- The orchestrator can spawn `python3 -m argos.cli ...` subprocesses without a custom binary on PATH for development workflows.

## Amendment trail

Per §Decision item 1, additions to the stdlib import allowlist
(`argos/cli/lint_imports.py` `STDLIB_ALLOWLIST`) are documented here with the
specific stdlib feature that demands them. These are stdlib-only additions; the
runtime-stdlib mandate and the zero-third-party-dependency rule are unchanged.

- **2026-06-13 — `atexit`, `signal` (ARG1-066).** ARG1-066's merge-aware
  independence detector runs dry-run `git merge` in a throwaway git worktree.
  ARG1-066 AC#2 mandates that the worktree be cleaned up "even on crash (atexit
  + signal handlers)". `atexit.register` covers normal interpreter exit and
  unhandled exceptions; `signal.signal` (SIGINT/SIGTERM) covers operator
  interrupts that bypass `atexit`. Both are stdlib; no third-party dependency is
  introduced. The context-manager path remains the primary cleanup; these are
  the crash backstops the AC requires.
