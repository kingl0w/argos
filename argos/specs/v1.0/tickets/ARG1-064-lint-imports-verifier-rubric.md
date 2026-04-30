---
id: ARG1-064
title: Add structured import-allowlist check (argos lint-imports + verifier rubric amendment)
status: queued
layer: 2
depends_on: []
blocks: []
allowed_tools: [Read, Edit, Write, Bash, Grep, Glob]
denied_paths: ["argos/specs/v1.0/decisions/**", "argos/specs/v1.0/PRD.md", "argos/specs/v1.0/ARCHITECTURE.md"]
---

## Context

Two planner-vs-shipped-spec deviations in 14+ tickets have slipped past the verifier:

1. ARG1-010 AC#3 satisfied non-portably (used `pyyaml` in ACs despite ADR-001
   stdlib-only). Drained via ARG1-057 escalation → ADR-002 ratification →
   ARG1-059 retrofit.

2. ARG1-050's `test_state_parser.py` shipped with `import pytest` at module
   level. Surfaced after the ARG1-020/031/041 three-way merge when discovery
   ran on a clean stdlib python. Drained via ARG1-063.

Both deviations were structurally checkable — an AST walk of imports against
the ADR-001 §Decision item 1 allowlist would have caught both at verification
time. The verifier rubric (ARG1-030) does not currently encode such a check,
so it relies on the verifier agent to notice ad-hoc, which has now failed
twice. ARG1-063's Non-goals named this ticket as the proposed follow-up.

This ticket is **queued**, not ready. Dispatch behind ARG1-011 and ARG1-012
(Layer 2 dispatcher work has critical-path priority). Promote to `ready`
after those two land on main and before the next dependency-chain batch
(ARG1-021).

## Goal

Two changes, shipped together:

1. **New CLI subcommand `argos lint-imports`** — stdlib-only; walks `.py`
   files under a given root, verifies every `import` / `from` statement
   references either a stdlib module from the ADR-001 §Decision item 1
   allowlist, the `__future__` pseudo-module (per ARG1-062), or an internal
   `argos` submodule. Exits 0 if all imports pass; exits 1 with one stderr
   line per violation otherwise.

2. **Verifier rubric amendment** — append a section to ARG1-030's ticket
   file directing the verifier to run `argos lint-imports argos/` as part
   of every ticket's verification step. Mirror the change in both
   `argos/specs/v1.0/agents/verifier.md` (canonical) and
   `.claude/agents/verifier.md` (Claude Code mirror).

The CLI subcommand is the structural mechanism; the rubric amendment is the
contract that says "the verifier must run it." Markdown alone (rubric
without subcommand) is fragile; subcommand alone (no rubric direction) means
the verifier may not invoke it. Both are required.

## Acceptance criteria

AC#1 — `python3 -m argos.cli lint-imports --help` exits 0; subcommand listed
       in `python3 -m argos.cli --help` under INTERNAL_SUBCOMMANDS, matching
       the registration pattern of state-parse / frontmatter-parse /
       verifier-writeback / run-session.

AC#2 — Module is stdlib-only. The same AST allowlist check used in ARG1-063
       AC#5, applied to `argos/cli/lint_imports.py`, exits 0:
       `python3 -c 'import ast, sys; tree = ast.parse(open("argos/cli/lint_imports.py").read()); imports = [n.module if isinstance(n, ast.ImportFrom) else n.names[0].name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]; allowed = {"unittest", "argos", "pathlib", "tempfile", "io", "json", "re", "sys", "os", "subprocess", "textwrap", "ast", "argparse", "__future__"}; bad = [i for i in imports if i.split(".")[0] not in allowed]; sys.exit(0 if not bad else 1)'`

AC#3 — `python3 -m argos.cli lint-imports argos/` exits 0 against current
       main. This is the pre-flight: if any violations beyond the two already
       drained (pytest in test_state_parser.py — fixed in ARG1-063, pyyaml
       in ARG1-010 ACs — fixed in ARG1-059) exist in the tree, the planner
       must surface them in the Plan section and either (a) fix inline if
       single-file mechanical, or (b) escalate per the schema before this
       ticket can ship. Do not silently widen the allowlist to absorb a
       violation.

AC#4 — Violation detection: a fixture at
       `argos/cli/tests/fixtures/lint_imports/bad_import.py` containing
       `import requests` (and nothing else) causes
       `python3 -m argos.cli lint-imports argos/cli/tests/fixtures/lint_imports/`
       to exit 1 with stderr matching the canonical format
       `lint-imports: <relpath>:<line>: forbidden import <name>` (one line
       per violation). The exact format is the contract; downstream tooling
       may grep it.

AC#5 — Missing path: `python3 -m argos.cli lint-imports /nonexistent/path`
       exits 1, stderr matches `lint-imports: <path>: not found`.

AC#6 — Allowlist source of truth: a single literal in
       `argos/cli/lint_imports.py` named `STDLIB_ALLOWLIST` with a docstring
       pointer to ADR-001 §Decision item 1. The literal MUST include at
       minimum the stdlib subset enumerated in ADR-001 plus `__future__`
       plus `argos`. Any future expansion requires both an ADR amendment
       and a literal update — that coupling is intentional.

AC#7 — Verifier agent definition updated in BOTH locations
       (`argos/specs/v1.0/agents/verifier.md` and `.claude/agents/verifier.md`)
       with a new verification step: "Before marking a ticket verified, run
       `argos lint-imports argos/` and confirm exit 0. If the command exits
       1, the ticket fails verification regardless of its own AC outcomes."
       Tool allowlist (Read, Bash, Grep, Glob) unchanged — `lint-imports` is
       a Bash invocation.

AC#8 — ARG1-030's ticket file (`argos/specs/v1.0/tickets/ARG1-030-*.md`)
       gets a new section appended at the bottom titled
       `## Amendment (ARG1-064)`, containing: prose describing the new
       verification step, a one-line citation of the two precedent
       deviations (ARG1-010 AC#3 and ARG1-050 test_state_parser.py), and a
       link to ARG1-064's commit. This follows ARG1-062's pattern of
       clarifying-via-appendix rather than retro-edit.

AC#9 — Test suite: `argos/cli/tests/test_lint_imports.py` exists with ≥6
       tests covering: stdlib-only file passes; single forbidden import
       fails with correct stderr format; multiple violations produce
       multiple stderr lines; ImportFrom syntax handled (`from requests
       import get`); dotted internal imports pass (`from argos.cli.foo
       import bar`); recursion into subdirectories works; missing-path
       returns the canonical not-found error.

AC#10 — Full sweep clean: `python3 -m unittest discover -s argos/cli/tests`
        exits 0, test count ≥ 154 (current 148 + ≥6 new).

## Non-goals

- **Not a pre-commit hook.** Pre-commit infrastructure is ARG1-032's scope;
  this ticket is verifier-rubric-level enforcement only.
- **Not an allowlist expansion.** If a current argos file requires an import
  outside the allowlist, the fix is to refactor to use a permitted module
  or escalate for an ADR-001 amendment. Do not pre-emptively widen.
- **Not an ADR amendment.** ADR-001 and ADR-002 are downstream-of from this
  ticket, not edited by it.
- **Not a CI workflow change.** Verifier invocation is the enforcement point
  in v1.0. CI integration (if it ever lands) is post-Layer 3.
- **Not a verifier tool-allowlist change.** The verifier agent's allowed
  tools (Read, Bash, Grep, Glob) remain unchanged.

## State on completion

Append via `python3 -m argos.cli state-append --suffix done`.
