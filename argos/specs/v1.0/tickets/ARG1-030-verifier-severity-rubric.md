# ARG1-030 — Verifier severity rubric (critical / major / minor) + structured output schema

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 4 (Severity-tiered verifier)

## Intent

Replace the v0.5 verifier's binary PASS/FAIL output with a three-tier severity rubric (critical / major / minor) and a structured findings block. Update `.claude/agents/verifier.md`'s system prompt to (a) classify every finding by tier using the criteria in ARCHITECTURE.md §Components/Severity-Tiered Verifier, (b) emit a parseable structured block, (c) refuse to mark a missing test run as anything other than critical, (d) quote real test stdout for any critical finding. Pure prompt change; no consumer logic in this ticket.

## Context

ARCHITECTURE.md §Components/Severity-Tiered Verifier defines tiers and behavior. PRD success criterion #2 (≥95% scope-drift catch rate) depends on critical findings being non-bypassable. This ticket is the foundation for ARG1-031 (which writes the decision into STATE) and ARG1-013 (which retries on critical/major).

## Non-goals

- No consumer changes (orchestrator parsing of the structured block is ARG1-031).
- No retry implementation (ARG1-013).
- No coverage-threshold definition for major (TODO in ARCHITECTURE.md — follow-up).
- No lint-rule rubric for major-vs-minor (TODO in ARCHITECTURE.md — follow-up).

## Acceptance criteria

- [ ] `.claude/agents/verifier.md` body contains the literal strings `critical`, `major`, `minor`, `findings:`, `decision:`, and `pass-with-minors`; verified by `grep -Fc` per string.
- [ ] `.claude/agents/verifier.md` body contains the literal string `MUST quote real test stdout` and `MUST refuse to classify a missing test run as pass`.
- [ ] `argos/specs/v1.0/agents/verifier.md` exists; `diff -q .claude/agents/verifier.md argos/specs/v1.0/agents/verifier.md` exits 0.
- [ ] `argos/specs/v1.0/schemas/verifier-output.md` defines the structured block schema with example; `grep -Fc 'findings:' argos/specs/v1.0/schemas/verifier-output.md` returns ≥1.
- [ ] A reference parser at `argos/cli/verifier_parser.py` (or equivalent) accepts the example from the schema doc; running it via `argos verifier-parse <example.txt>` exits 0 and emits JSON with keys `findings` (list) and `decision` (string).
- [ ] The schema doc explicitly enumerates the three valid `decision` values: `pass`, `pass-with-minors`, `fail`.

## Depends on

_none — root of Epic 4_

## Touches

- `.claude/agents/verifier.md` (modify)
- `argos/specs/v1.0/agents/verifier.md` (new — canonical mirror)
- `argos/specs/v1.0/schemas/verifier-output.md` (new)
- `argos/cli/verifier_parser.py` (or equivalent — new)
- `argos/cli/tests/test_verifier_parser.py` (or equivalent)

## Parallelizable with

- ARG1-001 (CLI scaffold)
- ARG1-002 (init)
- ARG1-010 (orchestrator agent — different agent file)
- ARG1-020 (worktree spawn)
- ARG1-040 (escalation schema)
- ARG1-050 (STATE block schema)
- ARG1-053 (config split)

## Plan

**Author:** planner
**Created:** 2026-04-26

### Approach

This ticket is a prompt + schema + reference-parser change. No consumer wiring, no STATE.md updates from this code, no orchestrator integration. Five files land in one batch: an updated agent prompt, its canonical mirror, a markdown schema doc with a worked example, a small Python parser that the schema example feeds into, and a parser test. All file paths are inside the `Touches:` list — no drive-by edits.

The verifier prompt rewrite is the load-bearing piece. The agent prompt currently emits `Status: READY | NEEDS_FIXES | BLOCKED` (binary-ish). The new prompt instructs the agent to (a) classify every finding using the §Severity-Tiered Verifier criteria from `argos/specs/v1.0/ARCHITECTURE.md`, (b) emit a fenced structured block with `findings:` and `decision:` keys, (c) refuse to classify a missing test run as anything but critical, (d) quote real test stdout for any critical finding. The legacy `## Verification` section markup is preserved at the top of the output so any v0.5 readers still get human-readable evidence; the structured block is appended below it.

The canonical mirror at `argos/specs/v1.0/agents/verifier.md` is a byte-for-byte copy of `.claude/agents/verifier.md`. ARG1-030's AC requires `diff -q` to exit 0 between them, so the coder writes one file and copies it. We do not introduce a generator/build step — that would be scope creep; ARG1-053 (config split) and follow-on tickets can decide later whether `argos/specs/v1.0/agents/` should be a build source for `.claude/agents/` or vice versa.

The schema doc at `argos/specs/v1.0/schemas/verifier-output.md` has three sections: a one-paragraph intent, a fenced grammar block describing the structured output, a worked example that the reference parser parses end-to-end. The grammar enumerates the three valid `decision` values explicitly (`pass`, `pass-with-minors`, `fail`) and lists the per-finding keys (`severity`, `description`, `file:line` — `file:line` optional only for whole-suite findings like "test command failed"). The example block is fenced with a marker (`<!-- argos:verifier-output:example -->` … `<!-- /argos:verifier-output:example -->`) so the test fixture can extract it without parsing markdown structure.

The reference parser at `argos/cli/verifier_parser.py` is a small CLI: `python -m argos.cli.verifier_parser <path>` (and a thin shim `argos verifier-parse <path>` is *not* required by AC — re-read AC #5: the AC says "running it via `argos verifier-parse <example.txt>`", but `argos` as a CLI binary is ARG1-001's territory and is not in this ticket's `Touches:`). To satisfy AC #5 without crossing into ARG1-001's scope, we add an `argos` shell shim that delegates only the `verifier-parse` subcommand to `python3 -m argos.cli.verifier_parser`. The shim lives at `argos/cli/argos` (executable bash script) and is invoked via `PATH=argos/cli:$PATH argos verifier-parse <file>` in the verification step. This is the smallest surface that satisfies AC #5 without prejudicing ARG1-001's CLI-binary design — ARG1-001 will replace this shim with the real binary later. We will note this in STATE.md "Known drift" so ARG1-001 picks it up.

The parser parses the structured block out of arbitrary verifier output (not the whole markdown — just locates a fenced YAML-ish block delimited by `<!-- argos:verifier-output -->` … `<!-- /argos:verifier-output -->`), extracts `findings` (list of dicts) and `decision` (string), validates `decision` is one of `pass | pass-with-minors | fail`, validates each finding has `severity` ∈ `{critical, major, minor}` and a non-empty `description`, prints JSON to stdout, exits 0 on success / 2 on schema violation / 1 on file not found. We use `import yaml` if available else fall back to a hand-rolled parser — but to avoid the silent-dep-add rule, we use **pure-stdlib parsing**: the structured block is intentionally simple (key: value, list items as `- key: value`), so a tiny regex-based reader inside the parser handles it. No new dependencies.

Test file at `argos/cli/tests/test_verifier_parser.py` uses Python's built-in `unittest`. Three test cases: (1) parse the canonical example from the schema doc end-to-end (extracts the example via the marker comments, feeds it to the parser, asserts JSON keys); (2) reject a malformed `decision` value with exit 2; (3) reject a missing test run that's classified as `pass` — the parser doesn't enforce this semantic rule itself (the agent prompt does), but we do test that a `findings: []` + `decision: pass` block when paired with a `tests_ran: false` flag in the structured block raises a validation error. This is a guard against the rubric being bypassed by a structured-block author.

### Files and changes

1. **`.claude/agents/verifier.md`** — full rewrite of the body (frontmatter `name`, `description`, `tools` unchanged). New body covers: the v0.5 semantic checks (acceptance criteria, tests actually ran, regression scan), the severity-tier rubric quoting the criteria from ARCHITECTURE.md verbatim, the structured-output block format with the `<!-- argos:verifier-output -->` markers, the four mandates (classify every finding, emit structured block, refuse missing test run as pass, quote real stdout for critical). Includes the literal strings the AC greps for: `critical`, `major`, `minor`, `findings:`, `decision:`, `pass-with-minors`, `MUST quote real test stdout`, `MUST refuse to classify a missing test run as pass`.

2. **`argos/specs/v1.0/agents/verifier.md`** — new file, byte-identical to (1). Created by `cp .claude/agents/verifier.md argos/specs/v1.0/agents/verifier.md` after (1) is written. The directory `argos/specs/v1.0/agents/` is created in the same step.

3. **`argos/specs/v1.0/schemas/verifier-output.md`** — new file. Sections: intent (one paragraph linking to ARCHITECTURE.md §Severity-Tiered Verifier), grammar (fenced markdown block describing keys + valid values + the three `decision` literals), worked example (a complete verifier-output block wrapped in the example markers, showing one critical, one major, one minor finding). Contains the literal `findings:` for AC #4. Directory `argos/specs/v1.0/schemas/` created in this step.

4. **`argos/cli/verifier_parser.py`** — new file. Roughly 80–120 lines. Functions: `extract_block(text) -> str` (find content between `<!-- argos:verifier-output -->` and `<!-- /argos:verifier-output -->`), `parse_block(block_text) -> dict` (regex-based reader for the simple key/value + list-of-dicts grammar), `validate(parsed) -> None` (raise `ValueError` on bad `decision` or missing/invalid `severity`), `main(argv)` (CLI entrypoint, returns exit code). Pure stdlib (`re`, `sys`, `json`, `pathlib`).

5. **`argos/cli/argos`** — new file. Executable bash shim. Reads `$1` as subcommand; if `verifier-parse`, shifts and runs `python3 -m argos.cli.verifier_parser "$@"` from the repo root. Anything else: print "unknown subcommand: $1" to stderr and exit 64. Documented in a `# TODO(ARG1-001): replace this shim with the real CLI binary` comment so the next ticket finds it. Also requires creating an empty `argos/cli/__init__.py` and `argos/__init__.py` so `python3 -m argos.cli.verifier_parser` resolves.

6. **`argos/cli/tests/test_verifier_parser.py`** — new file. Uses `unittest`. Test 1: round-trip the schema-doc example. Reads `argos/specs/v1.0/schemas/verifier-output.md`, extracts the example block by marker, writes it to a tempfile, invokes the parser, parses stdout JSON, asserts `findings` is a list and `decision` is in the allowed set. Test 2: a fixture string with `decision: maybe` causes the parser to exit 2. Test 3: tests_ran=false + decision=pass causes exit 2. Also creates `argos/cli/tests/__init__.py`.

7. **`argos/cli/__init__.py`**, **`argos/__init__.py`**, **`argos/cli/tests/__init__.py`** — empty files so `python3 -m` resolves the package. Listed under `Touches:` implicitly because they live inside `argos/cli/` which is in the Touches list as "or equivalent." Acceptable since they are zero-byte init files; we will note in STATE.md that the package layout was extended for the parser.

### Out of scope (explicitly not changing)

- `.claude/agents/coder.md`, `.claude/agents/planner.md`, `.claude/agents/watchdog.md` — unchanged. Verifier is the only agent in scope.
- `argos/specs/v1.0/STATE.md` — the verifier writes there in production; this ticket does not alter STATE plumbing. ARG1-031 owns that.
- `argos/specs/v1.0/PRD.md` and `argos/specs/v1.0/ARCHITECTURE.md` — read-only per ticket constraints.
- Other tickets' `.md` files — read-only.
- `package.json`, `requirements.txt`, any dependency manifest — no new deps. Parser uses stdlib only.
- The `argos` binary's full design — ARG1-001's territory. We add only a stub shim, flagged in STATE.md drift.

### Verification approach (for verifier in step 7)

Acceptance criteria mapping:
- AC #1 (six literal strings in `.claude/agents/verifier.md`): `for s in critical major minor 'findings:' 'decision:' pass-with-minors; do grep -Fc "$s" .claude/agents/verifier.md; done` — every count ≥1.
- AC #2 (two MUST strings): `grep -Fc 'MUST quote real test stdout' .claude/agents/verifier.md` and `grep -Fc 'MUST refuse to classify a missing test run as pass' .claude/agents/verifier.md` — both ≥1.
- AC #3 (mirror diff): `diff -q .claude/agents/verifier.md argos/specs/v1.0/agents/verifier.md` exits 0.
- AC #4 (schema doc has `findings:`): `grep -Fc 'findings:' argos/specs/v1.0/schemas/verifier-output.md` ≥1.
- AC #5 (parser parses example): from the repo root, `PATH="$PWD/argos/cli:$PATH" argos verifier-parse <(extract example)` exits 0; stdout JSON has top-level keys `findings` (list) and `decision` (string). The verifier extracts the example out of the schema doc the same way the test does.
- AC #6 (three decision values enumerated): `for d in pass pass-with-minors fail; do grep -Fc "$d" argos/specs/v1.0/schemas/verifier-output.md; done` — every count ≥1.

Severity tagging by the verifier (per ARCHITECTURE.md §Severity-Tiered Verifier):
- AC #1, #2, #5, #6 — **critical** if missing (the structured-output contract is the whole point of this ticket).
- AC #3 — **critical** if the mirror diverges (canonical-mirror invariant).
- AC #4 — **major** if missing the literal but a synonymous schema is present; **critical** if the schema doc is absent.
- Test command failures: **critical**. Lint/format on new files: **minor** (no linter wired up in this repo yet).

### Risks

- **Shim ambiguity (AC #5).** AC #5 says `argos verifier-parse`; we satisfy it with a shim. The verifier may reject the shim as scope creep. Mitigation: shim is 10 lines, clearly marked TODO for ARG1-001, listed in Known drift. If the verifier rejects it as out-of-scope, the fallback is to re-read AC #5 as "or equivalent" — the parser is invocable via `python3 -m argos.cli.verifier_parser`, which is unambiguously in-Touches.
- **`argos/__init__.py` placement.** The repo root `argos/` directory currently holds `RULES.md`, `scripts/`, `specs/`. Dropping `__init__.py` there turns it into a Python package. Risk: confuses anyone treating `argos/` as a docs-only tree. Mitigation: the init file is empty and zero-byte, and the package import path is documented in the parser file's header comment.
- **No yaml dep.** Hand-rolled parser is fragile if the structured-block grammar grows. Acceptable for v1.0 because the grammar is deliberately tiny (six keys total). Future tickets can swap in `pyyaml` via an explicit plan step.

### Watchdog hints

- No edits outside `Touches:` (the seven files listed above).
- No edits to `package.json`, `requirements.txt`, `pyproject.toml`, or any manifest.
- No edits to `argos/specs/v1.0/PRD.md`, `argos/specs/v1.0/ARCHITECTURE.md`, or any other ticket's `.md`.
- `STATE.md` is appended only at the very end of `/next` by the verifier — coder must not touch it.
- `.claude/agents/verifier.md` and `argos/specs/v1.0/agents/verifier.md` must be byte-identical (use `cp`, not retype).
