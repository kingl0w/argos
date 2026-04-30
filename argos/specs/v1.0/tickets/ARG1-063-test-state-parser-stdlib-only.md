---
id: ARG1-063
title: Convert test_state_parser.py from pytest to unittest (ADR-001 compliance)
status: ready
layer: 2
depends_on: []
blocks: []
allowed_tools: [Read, Edit, Write, Bash, Grep, Glob]
denied_paths: ["argos/specs/v1.0/decisions/**", "argos/specs/v1.0/PRD.md", "argos/specs/v1.0/ARCHITECTURE.md"]
---

## Context

`argos/cli/tests/test_state_parser.py` was shipped as part of ARG1-050 and contains
`import pytest` at module level. This violates ADR-001 §Decision item 1 (stdlib-only)
and ADR-002 §1 (AC harness portability on the same terms as runtime). The violation
was masked from previous test runs because:

  - Branch-level test sweeps for recent tickets ran `python3 -m unittest argos.cli.tests.<specific_module>`
    rather than discover, never importing the broken module.
  - One developer environment had pytest incidentally installed.

It surfaced after the ARG1-020/031/041 three-way merge when discovery was run against
a clean stdlib python. The merge itself is not the cause; this is pre-existing drift.

This is the second instance of a planner-vs-shipped-spec deviation that the verifier
did not catch (first: ARG1-010 AC#3 satisfied non-portably, drained via ARG1-057 +
ADR-002 + ARG1-059). See `## Known drift` for the pattern observation.

## Goal

Rewrite `argos/cli/tests/test_state_parser.py` to use only `unittest` from the stdlib,
matching the pattern established by `test_run_session.py`, `test_verifier_writeback.py`,
and `test_escalate.py`. Preserve all existing test cases and assertions; this is a
mechanical translation, not a behavioral change.

## Acceptance criteria

AC#1 — `grep -E '^(import pytest|from pytest)' argos/cli/tests/test_state_parser.py`
       exits 1 (no matches).

AC#2 — `python3 -m unittest argos.cli.tests.test_state_parser -v` exits 0 with the
       same set of test method names that existed before, prefixed with `test_`.
       (If the original file used pytest function-style tests, each becomes a method
       on a unittest.TestCase subclass with the same name.)

AC#3 — Test count unchanged or increased. Capture original count via
       `git show main:argos/cli/tests/test_state_parser.py | grep -cE '^def test_'`
       before edit; new count must equal or exceed it.

AC#4 — `python3 -m unittest discover -s argos/cli/tests` exits 0 (full sweep green;
       no other tests were broken by the change).

AC#5 — `python3 -c 'import ast, sys; tree = ast.parse(open("argos/cli/tests/test_state_parser.py").read()); imports = [n.module if isinstance(n, ast.ImportFrom) else n.names[0].name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]; allowed = {"unittest", "argos", "pathlib", "tempfile", "io", "json", "re", "sys", "os", "subprocess", "textwrap", "__future__"}; bad = [i for i in imports if i.split(".")[0] not in allowed]; sys.exit(0 if not bad else 1)'`
       exits 0. Allowlist matches ADR-001 §Decision item 1 stdlib subset plus internal
       `argos` modules. (Add modules to the allowlist literal if the original test
       legitimately needed them — e.g. `hashlib`, `datetime` — but document the
       addition in the Plan section.)

AC#6 — `git diff main -- argos/cli/tests/test_state_parser.py` shows only changes to
       that one file. No other source changes (STATE.md append from state-append is
       separate and expected).

## Non-goals

- Do not amend ARG1-030 verifier rubric or ADR-001/ADR-002. If the planner believes
  the verifier blind spot needs a rubric change to prevent recurrence, escalate per
  argos/specs/v1.0/schemas/escalation.md (proposal: ARG1-064, amend ARG1-030 with
  an import-allowlist AC). Do not amend rubrics inline.
- Do not change test semantics. If a pytest-specific construct (parametrize, fixtures
  with yield) requires a non-trivial unittest equivalent, prefer the most direct
  translation (subTest for parametrize, setUp/tearDown for fixtures).
- Do not touch any other file.

## State on completion

Append via `python3 -m argos.cli state-append --suffix done`.
