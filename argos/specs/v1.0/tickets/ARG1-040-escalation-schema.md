# ARG1-040 — Escalation file schema and `escalations/` directory contract

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 5 (Escalation channel)

## Intent

Commit the canonical escalation file schema (frontmatter fields, body sections) per ARCHITECTURE.md §Components/Escalation Channel. Create the `argos/specs/escalations/` directory with a `.gitkeep` and a README explaining the directory's role. Provide a reference parser/validator. This is the contract every escalation producer (orchestrator, planner, coder, watchdog, verifier) writes against and every consumer (`argos attend`, webhook) reads against.

## Context

ARCHITECTURE.md §Components/Escalation Channel defines the schema inline. This ticket lifts it into a versioned schema document so changes go through the v1.0 → v1.x → v2.0 schema-evolution process rather than ad-hoc edits to ARCHITECTURE.md.

## Non-goals

- No escalation writer implementation (ARG1-041).
- No `argos attend` consumer (ARG1-005).
- No webhook delivery (ARG1-041).
- No retroactive validation of escalations from earlier sessions (none exist).

## Acceptance criteria

- [ ] `test -f argos/specs/v1.0/schemas/escalation.md` exits 0; the file documents required frontmatter fields `ticket_id`, `session_id`, `severity`, `raised_by`, `created` with example values.
- [ ] `test -f argos/specs/escalations/.gitkeep && test -f argos/specs/escalations/README.md` exits 0.
- [ ] `argos escalation-validate argos/specs/v1.0/schemas/examples/escalation-blocking.md` exits 0 (a committed example validates).
- [ ] `argos escalation-validate argos/specs/v1.0/schemas/examples/escalation-malformed.md` exits non-zero; stderr names the missing/invalid field.
- [ ] The schema doc lists the two valid `severity` values `blocking` and `advisory` and the five valid `raised_by` values `orchestrator`, `planner`, `coder`, `watchdog`, `verifier`.
- [ ] The schema doc requires the body to contain the four sections `## Question`, `## Context`, `## Options considered`, `## Why escalated`; the validator enforces presence (`grep -Fc '## Question' <file>` ≥ 1, etc.).

## Depends on

_none — root of Epic 5_

## Touches

- `argos/specs/v1.0/schemas/escalation.md` (new)
- `argos/specs/v1.0/schemas/examples/escalation-blocking.md` (new)
- `argos/specs/v1.0/schemas/examples/escalation-malformed.md` (new)
- `argos/specs/escalations/.gitkeep` (new)
- `argos/specs/escalations/README.md` (new)
- `argos/cli/escalation_validator.py` (or equivalent — new)
- `argos/cli/tests/test_escalation_validator.py` (or equivalent)

## Parallelizable with

- ARG1-001 (CLI scaffold)
- ARG1-002 (init)
- ARG1-020 (worktree spawn)
- ARG1-030 (verifier rubric)
- ARG1-050 (STATE block schema)
- ARG1-053 (config split)

## Blocking ambiguity (must be resolved before coder runs)

**Language authorization for the validator is not yet granted.** ARG1-001 owns the cross-CLI language ADR and has not been worked. The ticket's `Touches` line hedges: `argos/cli/escalation_validator.py (or equivalent — new)`. Three honest paths:

- **(A) Pick Python now, locally.** Defensible: ticket explicitly says "or equivalent"; ARG1-040 is marked parallelizable-with ARG1-001; Python is the most-cited candidate in ARCHITECTURE.md §Technology choices; stdlib-only means zero new packages. Risk: if ADR-001 picks Rust/Go, this validator becomes a port target.
- **(B) Block on ARG1-001.** Removes risk; contradicts the explicit "Parallelizable with ARG1-001" line; stalls Epic 5.
- **(C) POSIX shell script.** No language commitment; loses richer error reporting; brittle frontmatter parsing in `awk`/`sed`.

**This Plan assumes (A) approved**, with a top-of-file comment in the validator: "Provisional language pending ADR-001; if ADR-001 names a different language, port this file as part of the ADR's migration step." Zero third-party deps; no `requirements.txt` or `pyproject.toml` added. Coder must not begin until (A) is acknowledged or another path chosen.

## Plan

### Files (in dependency order)

1. `argos/specs/v1.0/schemas/escalation.md` — canonical schema doc.
2. `argos/specs/v1.0/schemas/examples/escalation-blocking.md` — positive fixture; validator must accept.
3. `argos/specs/v1.0/schemas/examples/escalation-malformed.md` — negative fixture (`severity: critical` — invalid enum); validator must reject naming `severity`.
4. `argos/specs/escalations/.gitkeep` — zero-byte file.
5. `argos/specs/escalations/README.md` — runtime directory README, references the schema doc, notes un-versioned placement is intentional.
6. `argos/cli/__init__.py` — empty; package marker.
7. `argos/cli/escalation_validator.py` — validator implementation + `main()` entry point.
8. `argos/cli/tests/__init__.py` — empty; package marker.
9. `argos/cli/tests/test_escalation_validator.py` — stdlib `unittest` tests.
10. `argos/cli/escalation-validate` — POSIX shell shim (`exec python3 -m argos.cli.escalation_validator "$@"`), mode 0755, provisional until ARG1-001 ships the unified `argos` dispatcher.

### File content shapes

**1. `argos/specs/v1.0/schemas/escalation.md`** — Frontmatter `name: escalation-file-schema`, `description`, `status: draft`, `version: 1.0`. Body sections: `# Escalation file schema` (intro referencing ARCHITECTURE.md §Components/Escalation Channel); `## Frontmatter (required)` listing the five fields with type, allowed values, and an example value each — `ticket_id` (string), `session_id` (string; convention `sess-<ISO-8601>-<short-sha>`), `severity` (enum: `blocking` | `advisory`), `raised_by` (enum: `orchestrator` | `planner` | `coder` | `watchdog` | `verifier`), `created` (ISO-8601 UTC); `## Body sections (required)` listing the four required H2 headings with one-line descriptions; `## Filename convention` (`argos/specs/escalations/{ticket-id}-{ISO-timestamp}.md`); `## Worked examples` (links to the two example files); `## Schema evolution` (changes go through ARCHITECTURE.md ADR + bump on frontmatter `version`).

**2. `argos/specs/v1.0/schemas/examples/escalation-blocking.md`** — Realization of the ARCHITECTURE.md §Escalation Channel example. All five frontmatter fields valid (`severity: blocking`, `raised_by: orchestrator`). Body has all four required `## Question`, `## Context`, `## Options considered`, `## Why escalated` sections with realistic 1–3 sentence prose.

**3. `argos/specs/v1.0/schemas/examples/escalation-malformed.md`** — Same shape, **deliberately broken in exactly one way**: `severity: critical` (invalid enum value — `critical` is a verifier-finding tier, a realistic confusion). Top-of-file HTML comment `<!-- intentionally invalid: see ARG1-040 -->` so a reader doesn't try to "fix" it.

**4. `argos/specs/escalations/.gitkeep`** — Zero-byte file.

**5. `argos/specs/escalations/README.md`** — Three short paragraphs: (i) directory holds runtime escalation files written by orchestrator/sessions and drained by `argos attend`; (ii) file format documented at `argos/specs/v1.0/schemas/escalation.md`, with filename convention restated; (iii) directory is **not** version-prefixed because it is runtime state — schemas live under `argos/specs/v1.0/schemas/`, runtime instances live here. One sentence: producers (ARG1-041) and consumers (ARG1-005) are tracked separately.

**6. `argos/cli/__init__.py`** — Empty (or single comment `# argos.cli — provisional package; language pending ADR-001`).

**7. `argos/cli/escalation_validator.py`** — Python 3.12, **stdlib only**. Module-level constants:

```
ALLOWED_SEVERITY = {"blocking", "advisory"}
ALLOWED_RAISED_BY = {"orchestrator", "planner", "coder", "watchdog", "verifier"}
REQUIRED_FRONTMATTER_KEYS = ("ticket_id", "session_id", "severity", "raised_by", "created")
REQUIRED_BODY_SECTIONS = ("## Question", "## Context", "## Options considered", "## Why escalated")
```

Functions (signatures fixed):
- `parse_frontmatter(text: str) -> tuple[dict[str, str], str]` — splits on the first two `---` delimiter lines; each frontmatter line matches `^([a-z_]+):\s*(.+?)\s*$`. Returns `(dict, body)`. Raises `ValueError` on missing/malformed delimiters or any non-matching line. (No PyYAML — flat scalar key:value only.)
- `validate(path: pathlib.Path) -> list[str]` — opens the file, calls `parse_frontmatter`, checks each `REQUIRED_FRONTMATTER_KEYS` is present, `severity` in `ALLOWED_SEVERITY`, `raised_by` in `ALLOWED_RAISED_BY`, `created` parses via `datetime.datetime.fromisoformat` (3.11+ accepts trailing `Z`), each `REQUIRED_BODY_SECTIONS` heading appears at least once on its own line in the body. Returns list of human-readable error strings; empty list = valid.
- `main(argv: list[str] | None = None) -> int` — argparse, one positional `path`. Valid: silent stdout, exit 0. Invalid: one error per line on stderr, exit 1. Missing/unreadable file or unparseable frontmatter: error to stderr, exit 2.
- `if __name__ == "__main__": sys.exit(main())`.

Top-of-file docstring notes the schema location and the ADR-001 provisional-language caveat.

**8. `argos/cli/tests/__init__.py`** — Empty.

**9. `argos/cli/tests/test_escalation_validator.py`** — Stdlib `unittest`, no pytest dep. Cases:
- `test_blocking_example_validates` — runs `validate()` against the blocking fixture; asserts empty error list. (AC #3.)
- `test_malformed_example_fails_with_severity_error` — runs `validate()` against the malformed fixture; asserts non-empty error list and at least one error mentions `severity`. (AC #4.)
- `test_main_exit_codes` — `subprocess.run([sys.executable, "-m", "argos.cli.escalation_validator", <path>], ...)` against both fixtures; exit 0 for blocking, non-zero for malformed, non-empty stderr for malformed. (Cross-checks AC #3, #4 at CLI surface.)
- `test_missing_required_field_each` — for each of the five required keys, write a temp file (under `tempfile.TemporaryDirectory`) omitting only that key; assert the error names that key. (AC #4 generality.)
- `test_missing_each_body_section` — for each of the four sections, omit only that heading; assert the error names it. (AC #6.)
- `test_invalid_severity_value` — `severity: urgent`; assert error mentions `severity` and `urgent`. (AC #5.)
- `test_invalid_raised_by_value` — `raised_by: human`; assert error mentions `raised_by` and `human`. (AC #5.)

Fixture path resolution: `pathlib.Path(__file__).resolve().parents[3] / "specs" / "v1.0" / "schemas" / "examples"` — portable, no absolute paths.

**10. `argos/cli/escalation-validate`** — POSIX shell wrapper, mode 0755:

```
#!/usr/bin/env sh
exec python3 -m argos.cli.escalation_validator "$@"
```

Top-of-file comment: provisional shim; ARG1-001 will replace this with a unified `argos` subcommand dispatcher and delete this file.

### CLI contract (validator)

- **Committed invocation:** `python3 -m argos.cli.escalation_validator <path>` — what the tests exercise.
- **AC-compatibility invocation:** `argos/cli/escalation-validate <path>` (the shim, repo-relative path). The verifier uses this — the AC bullets write `argos escalation-validate <path>` but no top-level `argos` binary exists yet (ARG1-001 scope).
- **Exit codes:** `0` valid; `1` parses but fails validation (stderr lists each failure, one per line, `<field-or-section>: <reason>`); `2` missing/unreadable file or unparseable frontmatter (stderr names path + parse-level reason).
- **Stdout:** silent on success — no banner, scriptable in pipelines.
- **Stderr error format:** machine-grep-able, e.g. `severity: invalid value 'critical' (allowed: advisory, blocking)`, `## Question: required body section missing`.

### Acceptance-criteria → coverage map

| AC bullet | Covered by |
|---|---|
| `test -f argos/specs/v1.0/schemas/escalation.md` exits 0; documents required frontmatter fields with example values. | File 1 + verifier `test -f` and `grep -Fc 'ticket_id'` etc. |
| `test -f argos/specs/escalations/.gitkeep && test -f argos/specs/escalations/README.md` exits 0. | Files 4, 5. |
| `argos escalation-validate <blocking>` exits 0. | File 2 + 7 + 10; verifier runs the shim. |
| `argos escalation-validate <malformed>` exits non-zero; stderr names the missing/invalid field. | File 3 + 7 (stderr format) + 10. |
| Schema doc lists two `severity` and five `raised_by` values. | File 1 "Frontmatter (required)" — verified by `grep -Fc`. |
| Schema doc requires four body sections; validator enforces presence. | File 1 documents headings; file 7 `REQUIRED_BODY_SECTIONS`; file 9 `test_missing_each_body_section` proves enforcement. |

Every AC bullet mapped; no bullet uncovered.

### Test commands (verifier, run from repo root)

```
python3 -m unittest argos.cli.tests.test_escalation_validator -v
test -f argos/specs/v1.0/schemas/escalation.md
test -f argos/specs/escalations/.gitkeep
test -f argos/specs/escalations/README.md
grep -Fc 'blocking' argos/specs/v1.0/schemas/escalation.md
grep -Fc 'advisory' argos/specs/v1.0/schemas/escalation.md
for v in orchestrator planner coder watchdog verifier; do grep -Fc "$v" argos/specs/v1.0/schemas/escalation.md; done
for s in '## Question' '## Context' '## Options considered' '## Why escalated'; do grep -Fc "$s" argos/specs/v1.0/schemas/escalation.md; done
argos/cli/escalation-validate argos/specs/v1.0/schemas/examples/escalation-blocking.md
argos/cli/escalation-validate argos/specs/v1.0/schemas/examples/escalation-malformed.md 2>&1 1>/dev/null | grep -F 'severity'
```

First eight checks must exit 0; ninth must exit 0; tenth (validating malformed) must exit non-zero AND stderr must contain `severity`.

One-liner summary for verifier:

```
python3 -m unittest argos.cli.tests.test_escalation_validator -v && \
  test -f argos/specs/v1.0/schemas/escalation.md && \
  test -f argos/specs/escalations/.gitkeep && test -f argos/specs/escalations/README.md && \
  argos/cli/escalation-validate argos/specs/v1.0/schemas/examples/escalation-blocking.md && \
  ! argos/cli/escalation-validate argos/specs/v1.0/schemas/examples/escalation-malformed.md
```

### Dependencies

**No third-party packages added.** Stdlib-only (`pathlib`, `re`, `argparse`, `sys`, `datetime`, `unittest`, `subprocess`, `tempfile`). No `pyproject.toml` or `requirements.txt` created or modified — `python3` invoked directly. Complies with RULES.md "no silent dep adds": no dep file to silently grow.

### CLI wiring (without ARG1-001)

ARG1-001 has not landed; the AC-bullet form `argos escalation-validate <path>` cannot be invoked. Plan ships `argos/cli/escalation-validate` (sh shim) as the provisional invocation surface, called by repo-relative path. Top-of-file comment in the shim and a one-line note in `argos/specs/escalations/README.md` flag this as provisional and reference ARG1-001 as the ticket that absorbs it. No generic `argos` arg parser, version flag, help, or subcommand registry — that's ARG1-001's scope.

### Spec-tree placement (confirmed; do not "fix")

- Schema doc + examples under `argos/specs/v1.0/schemas/` (versioned).
- Runtime escalation files under `argos/specs/escalations/` (un-versioned — runtime state, not spec doc).

Matches ARCHITECTURE.md §System shape, which places `argos/specs/escalations/` at the same level as `STATE.md` and `tickets/`. Coder must NOT relocate the runtime directory under `v1.0/`.

### Open questions

- **Blocking:** Language authorization (above). Until acknowledged, Coder must not begin.
- **Non-blocking, defer to ARG1-001:** The shim will be replaced when the real CLI lands.
- **Non-blocking, defer to ARG1-041:** `session_id` regex documented but not strictly enforced (any non-empty string accepted) — canonical format set by writer, not schema.

## Implementation notes

**Commits:** none yet — coder phase per RULES.md does not commit; that step happens after watchdog + verifier sign off.

**Files created (10/10, exact list authorized by Plan):**

- `argos/specs/v1.0/schemas/escalation.md`
- `argos/specs/v1.0/schemas/examples/escalation-blocking.md`
- `argos/specs/v1.0/schemas/examples/escalation-malformed.md`
- `argos/specs/escalations/.gitkeep` (zero bytes)
- `argos/specs/escalations/README.md`
- `argos/cli/__init__.py`
- `argos/cli/escalation_validator.py`
- `argos/cli/tests/__init__.py`
- `argos/cli/tests/test_escalation_validator.py`
- `argos/cli/escalation-validate` (mode 0755)

No files outside this list were touched.

**Tests run (real stdout):**

```
$ python3 -m unittest argos.cli.tests.test_escalation_validator -v
test_main_exit_codes ... ok
test_blocking_example_validates ... ok
test_malformed_example_fails_with_severity_error ... ok
test_invalid_raised_by_value ... ok
test_invalid_severity_value ... ok
test_missing_each_body_section ... ok
test_missing_required_field_each ... ok
----------------------------------------------------------------------
Ran 7 tests in 0.039s
OK
```

```
$ argos/cli/escalation-validate argos/specs/v1.0/schemas/examples/escalation-blocking.md; echo "exit=$?"
exit=0

$ argos/cli/escalation-validate argos/specs/v1.0/schemas/examples/escalation-malformed.md 2>&1 1>/dev/null; echo "exit=$?"
severity: invalid value 'critical' (allowed: advisory, blocking)
exit=1
```

Shim is executable: `-rwxr-xr-x 1 taddymason taddymason 286 Apr 26 15:07 argos/cli/escalation-validate`.

**Deviations from the Plan (with justification):**

1. **Test fixture path uses `parents[2]`, not `parents[3]`.** The Plan suggested
   `pathlib.Path(__file__).resolve().parents[3] / "specs" / "v1.0" / "schemas" / "examples"` but instructed me to verify and fix if off. The test file lives at `<repo>/argos/cli/tests/test_escalation_validator.py`, so `parents[2]` is `<repo>/argos` and the fixtures live at `<repo>/argos/specs/v1.0/schemas/examples`. `parents[3]` would have been `<repo>/` and the path would have resolved to `<repo>/specs/...` (no such directory). Used `parents[2]`; comment in the test file flags the off-by-one.

2. **Frontmatter parser tolerates leading HTML comments.** Plan File 3 mandates the malformed fixture begin with `<!-- intentionally invalid: see ARG1-040 -->`, AND the AC requires `stderr names the missing/invalid field` (i.e. `severity`). Without parser tolerance for a leading HTML comment, the parser bails at delimiter-detection (exit 2 with "frontmatter must begin with '---'") and never reaches the enum check — the malformed fixture's stated failure mode (severity enum) becomes unreachable. I extended `parse_frontmatter` to skip leading blank lines and single-line `<!-- ... -->` HTML comments before requiring the opening `---`. The line-format regex for frontmatter content lines is unchanged. This reconciles File 3's mandated comment with AC #4's requirement that stderr name `severity`. One fix attempt; surfaced here for watchdog review.

**Unexpected findings:**

- The Plan's AC-coverage map line "Schema doc lists two `severity` and five `raised_by` values — verified by `grep -Fc`" interacts oddly with the verifier's bash test list: `for v in orchestrator planner ...; do grep -Fc "$v" ...; done` will fail with exit code 1 on any value not present, but `grep -Fc` returns count 0 with exit 1 when no match. The schema doc lists all five; this is a heads-up for the verifier, not a coder action.
- `argos/specs/escalations/README.md`'s relative link to the schema doc resolves as `../v1.0/schemas/escalation.md` (correct from the README's directory). Not load-bearing for tests but worth noting if a docs CI pass starts checking links.

**Follow-ups (for new tickets, not this one):**

- ARG1-001 will absorb `argos/cli/escalation-validate` shim into a unified subcommand dispatcher. The shim's top-of-file comment and `argos/specs/escalations/README.md` both flag this.
- ARG1-041 (escalation writer) should validate its output via `python3 -m argos.cli.escalation_validator` before writing — wire this into the writer's contract.
- If ADR-001 names a non-Python language for the CLI, this validator becomes a port target (flagged in `escalation_validator.py` top-of-file docstring per Plan).
- Ticket section structure note: this ticket file contains both a Plan section and now an Implementation notes section appended to the body, after the Plan's "Open questions" subsection. Watchdog should confirm this placement matches conventions used in earlier closed tickets.

**STATE.md not touched** (verifier's exclusive write per RULES.md). **No new dependencies** added (stdlib only; no `requirements.txt` / `pyproject.toml` / `setup.py` created).

## Verification

**Date:** 2026-04-26
**Verifier:** verifier subagent
**Decision:** pass

### Findings

- 0 critical, 0 major, 0 minor

### AC bullet → evidence

- **AC1** (schema doc exists, documents 5 fields with example values):
  ```
  $ test -f argos/specs/v1.0/schemas/escalation.md && echo OK
  OK
  exit=0
  $ for f in ticket_id session_id severity raised_by created; do printf "%s: " "$f"; grep -Fc "$f" argos/specs/v1.0/schemas/escalation.md; done
  ticket_id: 1
  session_id: 1
  severity: 2
  raised_by: 1
  created: 2
  ```
  Schema doc documents each of the five required frontmatter fields with type, allowed values, and an example value (table at lines 26–32 of the schema doc).

- **AC2** (`.gitkeep` + `README.md` under `argos/specs/escalations/`):
  ```
  $ test -f argos/specs/escalations/.gitkeep && test -f argos/specs/escalations/README.md && echo OK
  OK
  exit=0
  ```

- **AC3** (blocking example validates, exit 0):
  ```
  $ argos/cli/escalation-validate argos/specs/v1.0/schemas/examples/escalation-blocking.md; echo "exit=$?"
  exit=0
  ```

- **AC4** (malformed example fails non-zero, stderr names invalid field):
  ```
  $ argos/cli/escalation-validate argos/specs/v1.0/schemas/examples/escalation-malformed.md 2>&1 1>/dev/null; echo "exit=$?"
  severity: invalid value 'critical' (allowed: advisory, blocking)
  exit=1
  ```
  Stderr names `severity` (the invalid field).

- **AC5** (severity + raised_by enum values listed in schema doc):
  ```
  $ grep -Fc 'blocking' argos/specs/v1.0/schemas/escalation.md
  3
  $ grep -Fc 'advisory' argos/specs/v1.0/schemas/escalation.md
  2
  $ for v in orchestrator planner coder watchdog verifier; do printf "%s: " "$v"; grep -Fc "$v" argos/specs/v1.0/schemas/escalation.md; done
  orchestrator: 4
  planner: 3
  coder: 3
  watchdog: 3
  verifier: 3
  ```
  All five `raised_by` values and both `severity` values present (each ≥ 1).

- **AC6** (4 body sections required + validator enforcement):
  ```
  $ for s in '## Question' '## Context' '## Options considered' '## Why escalated'; do printf "%s: " "$s"; grep -Fc "$s" argos/specs/v1.0/schemas/escalation.md; done
  ## Question: 2
  ## Context: 1
  ## Options considered: 1
  ## Why escalated: 1
  ```
  Schema doc requires all four sections (lines 53–67). Validator enforcement proven by `test_missing_each_body_section` in `argos/cli/tests/test_escalation_validator.py` (lines 126–157), which constructs a fixture omitting each required section in turn and asserts `validate()` returns an error naming the missing heading. Test passed in the run below.

### Tests run

`python3 -m unittest argos.cli.tests.test_escalation_validator -v`

```
test_main_exit_codes (argos.cli.tests.test_escalation_validator.CliExitCodeTests.test_main_exit_codes) ... ok
test_blocking_example_validates (argos.cli.tests.test_escalation_validator.FixtureTests.test_blocking_example_validates) ... ok
test_malformed_example_fails_with_severity_error (argos.cli.tests.test_escalation_validator.FixtureTests.test_malformed_example_fails_with_severity_error) ... ok
test_invalid_raised_by_value (argos.cli.tests.test_escalation_validator.InvalidEnumTests.test_invalid_raised_by_value) ... ok
test_invalid_severity_value (argos.cli.tests.test_escalation_validator.InvalidEnumTests.test_invalid_severity_value) ... ok
test_missing_each_body_section (argos.cli.tests.test_escalation_validator.MissingBodySectionTests.test_missing_each_body_section) ... ok
test_missing_required_field_each (argos.cli.tests.test_escalation_validator.MissingRequiredFieldTests.test_missing_required_field_each) ... ok

----------------------------------------------------------------------
Ran 7 tests in 0.039s

OK
exit=0
```

### Notes

The validator is provisional Python pending ADR-001 (cross-CLI language decision); top-of-file docstrings in `argos/cli/escalation_validator.py` and the `argos/cli/escalation-validate` shim flag this. Stdlib only — no `requirements.txt` or `pyproject.toml` added. The shim is a temporary surface; ARG1-001 will absorb it into a unified `argos` subcommand dispatcher. v0.5 manual loop run on the v1.0 spec tree (no worktree dispatch); STATE.md is still in v0.5 free-form prose format pending ARG1-050, so this verification entry uses the existing idiom rather than the v1.0 block schema.
