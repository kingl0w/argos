# ARG1-050 — STATE.md append-mostly block schema + reference parser

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 6 (STATE.md migration + config split)

## Intent

Commit the canonical STATE.md append-mostly block schema per ARCHITECTURE.md §Contracts/STATE.md format. Each entry is wrapped in `<!-- argos:entry id=... ticket=... author=... session=... -->` … `<!-- /argos:entry -->` HTML comments, with `id = {ISO-timestamp}-{ticket-id}`. Ship a reference parser that extracts blocks, validates structure, and detects malformations (missing close tag, duplicate id, missing required attributes).

## Context

ARCHITECTURE.md §Contracts/STATE.md format specifies the schema inline. This ticket lifts it into a versioned schema document and produces the parser every other ticket consumes (`argos status`, `argos state-append`, the merge driver, the pre-commit hook).

## Non-goals

- No write helper (ARG1-051).
- No merge driver (ARG1-052).
- No migration of existing v0.5 STATE.md content (the v0.5 file is hand-edited prose; v1.0 is a fresh format).
- No backward-compatible parsing of v0.5-shaped STATE.md.

## Acceptance criteria

- [ ] `test -f argos/specs/v1.0/schemas/state-block.md` exits 0; the doc enumerates the required block-comment attributes `id`, `ticket`, `author`, `session` and the body line conventions.
- [ ] `argos state-parse argos/specs/v1.0/schemas/examples/state-valid.md` exits 0 and stdout (JSON) contains a list of blocks with all four attributes per block.
- [ ] `argos state-parse argos/specs/v1.0/schemas/examples/state-unclosed-block.md` exits non-zero; stderr contains `unclosed entry`.
- [ ] `argos state-parse argos/specs/v1.0/schemas/examples/state-duplicate-id.md` exits non-zero; stderr contains `duplicate id` and the offending `id` value.
- [ ] `argos state-parse argos/specs/v1.0/schemas/examples/state-missing-attr.md` exits non-zero; stderr names the missing attribute and the surrounding line.
- [ ] The schema doc explicitly states: "entries are append-only; never edit an existing entry; corrections are new entries that reference the prior `id`."
- [ ] Parser handles arbitrary section ordering inside each top-level STATE.md section (blocks within a section are unordered for parsing purposes, even though writers append in time order).

## Depends on

_none — root of Epic 6_

## Touches

- `argos/specs/v1.0/schemas/state-block.md` (new)
- `argos/specs/v1.0/schemas/examples/state-valid.md` (new)
- `argos/specs/v1.0/schemas/examples/state-unclosed-block.md` (new)
- `argos/specs/v1.0/schemas/examples/state-duplicate-id.md` (new)
- `argos/specs/v1.0/schemas/examples/state-missing-attr.md` (new)
- `argos/cli/state_parser.py` (or equivalent — new)
- `argos/cli/commands/state_parse.py` (or equivalent — debug subcommand exposing the parser)
- `argos/cli/tests/test_state_parser.py` (or equivalent)

## Parallelizable with

- ARG1-001 (CLI scaffold)
- ARG1-010 (orchestrator agent)
- ARG1-020 (worktree spawn)
- ARG1-030 (verifier rubric)
- ARG1-040 (escalation schema)
- ARG1-053 (config split — different module)

## Plan

**Sizing note.** Ticket touches 8 files, exceeding the planner's default 3-file/200-LOC threshold. Not splitting: 4 of the touched files are tiny markdown fixtures (≤10 lines each), 1 is a documentation deliverable (schema doc), and the actual code is one parser module + one CLI shim + one test file — a single subsystem (schema definition + reference parser) within Epic 6's root. The work is below the spirit of the threshold and splitting would fragment a single contract.

**Language assumption.** Per ticket guidance, treating Python as the working assumption (the ticket lists `.py` paths explicitly). ARG1-001's ADR-001 has not landed yet; if it picks a non-Python language, this ticket's code paths will need to be re-skinned. See Open questions.

**Scaffolding scope.** The repo has no `argos/cli/` directory and no Python project file (`pyproject.toml`). ARG1-001 owns full CLI scaffolding (entry point, version, help, dispatch table) and is parallelizable with this ticket; we cannot rely on its output. To make `argos state-parse <file>` invocable per the acceptance criteria, this ticket adds the *minimum* scaffolding: a thin `argos/cli/__main__.py` with a tiny argparse dispatch that knows one subcommand (`state-parse`). When ARG1-001 lands, its richer dispatch can absorb or replace ours; the contract this ticket exposes is the subcommand name and behavior, not the scaffolding mechanism. We do NOT add `pyproject.toml`, do NOT create a console-script entry point, and do NOT add any external runtime dependencies. Invocation in tests is `python3 -m argos.cli state-parse <file>`; an `argos` shim binary is ARG1-001's job. Acceptance-criteria CLI strings (`argos state-parse ...`) are interpreted as "the subcommand exposed by the CLI module" — the verifier runs the module form. This is called out in Open questions for explicit confirmation.

### Files touched

| Path | Status | Purpose |
|------|--------|---------|
| `argos/specs/v1.0/schemas/state-block.md` | new | Canonical schema doc for the append-mostly block format |
| `argos/specs/v1.0/schemas/examples/state-valid.md` | new | One well-formed block (positive fixture) |
| `argos/specs/v1.0/schemas/examples/state-unclosed-block.md` | new | One block with missing `<!-- /argos:entry -->` close tag |
| `argos/specs/v1.0/schemas/examples/state-duplicate-id.md` | new | Two blocks sharing the same `id` attribute |
| `argos/specs/v1.0/schemas/examples/state-missing-attr.md` | new | One block missing a required attribute |
| `argos/cli/__init__.py` | new | Empty package marker for `argos.cli` |
| `argos/cli/commands/__init__.py` | new | Empty package marker for `argos.cli.commands` |
| `argos/cli/__main__.py` | new | Minimal argparse dispatch exposing `state-parse` subcommand (scaffolding stand-in until ARG1-001's CLI lands) |
| `argos/cli/state_parser.py` | new | Reference parser: extract blocks, validate structure, raise typed errors |
| `argos/cli/commands/state_parse.py` | new | CLI shim: file path in, JSON to stdout on success, error message to stderr + nonzero exit on failure |
| `argos/cli/tests/__init__.py` | new | Empty package marker for tests |
| `argos/cli/tests/test_state_parser.py` | new | Pytest tests covering parser API and the four fixtures |

Net new files: 12 (4 fixture markdown, 1 schema markdown, 7 Python — of which 3 are empty `__init__.py` markers and 1 is a ≤30-line CLI dispatch stub). The non-trivial code surface is concentrated in `state_parser.py`, `commands/state_parse.py`, and `tests/test_state_parser.py`.

### Changes per file

#### `argos/specs/v1.0/schemas/state-block.md` (new — schema doc)
- Title and frontmatter (`name`, `description`, `status: draft`, `version: 1.0`).
- Section: **Required block-comment attributes** — table listing `id` (format: `{ISO-8601-UTC-timestamp}-{ticket-id}`), `ticket` (matches ticket ID regex), `author` (one of `planner | coder | watchdog | verifier | orchestrator`), `session` (opaque session identifier string). For each attribute: name, format, example, validation rule.
- Section: **Block delimiters** — open tag `<!-- argos:entry id=... ticket=... author=... session=... -->`; close tag `<!-- /argos:entry -->`; both must be on their own line.
- Section: **Body line conventions** — body lines between delimiters are markdown; the canonical first body line is a bullet with timestamp and ticket ID per the ARCHITECTURE.md §Contracts example; nested bullets list files changed, findings, decision; parser does not interpret body content beyond preserving it verbatim.
- Section: **Append-only invariant** — verbatim statement: "entries are append-only; never edit an existing entry; corrections are new entries that reference the prior `id`." Cite ARCHITECTURE.md §Invariants.
- Section: **Examples** — embed the four example fixture file paths as references (do not duplicate content) and show the canonical valid block inline (copied from ARCHITECTURE.md §Contracts).
- Section: **Parser failure modes** — enumerate the four detected failures (unclosed entry, duplicate id, missing required attribute, malformed open-tag attribute syntax) and the stderr substring contract for each.

#### `argos/specs/v1.0/schemas/examples/state-valid.md` (new — fixture)
- Single well-formed block under a `## Done this cycle` heading, mirroring the ARCHITECTURE.md §Contracts example shape.
- All four required attributes present with realistic values.
- Body has the canonical first-line bullet plus 2–3 nested bullets.

#### `argos/specs/v1.0/schemas/examples/state-unclosed-block.md` (new — fixture)
- Single block with a valid open tag but **no** `<!-- /argos:entry -->` close tag.
- Body content present so the parser proves it scans to EOF before failing.

#### `argos/specs/v1.0/schemas/examples/state-duplicate-id.md` (new — fixture)
- Two complete blocks (open + close) with **identical** `id` attribute values.
- Other attributes may differ; this isolates the duplicate-id failure mode.

#### `argos/specs/v1.0/schemas/examples/state-missing-attr.md` (new — fixture)
- Single complete block with an open tag missing exactly one of the four required attributes (use missing `session=` for concreteness).

#### `argos/cli/__init__.py` (new — package marker)
- Empty file (or single-line module docstring).

#### `argos/cli/commands/__init__.py` (new — package marker)
- Empty file (or single-line module docstring).

#### `argos/cli/__main__.py` (new — minimal dispatch)
- Read `sys.argv`; if first arg is `state-parse`, delegate to `argos.cli.commands.state_parse:main(remaining_args)`; else print short usage to stderr and exit nonzero.
- No external deps; standard-library `argparse` or hand-rolled argv slicing both acceptable. Keep under ~30 lines.
- Module docstring notes this is a scaffolding stand-in to be folded into ARG1-001's CLI dispatch when that lands.

#### `argos/cli/state_parser.py` (new — reference parser)
- Define typed exception classes: `StateBlockError` (base), `UnclosedEntryError`, `DuplicateIdError`, `MissingAttributeError`, `MalformedOpenTagError`. Each carries a human-readable message including the relevant line number (1-indexed) and, where applicable, the offending value (e.g., the duplicated `id`, the missing attribute name).
- Define a `Block` data class (or `TypedDict`) with fields: `id`, `ticket`, `author`, `session`, `body` (str), `start_line` (int), `end_line` (int).
- Public function `parse(text: str) -> list[Block]`: scans the text line-by-line; on encountering `<!-- argos:entry ...-->` opens a block, parses attributes via a regex like `(\w+)=(\S+)`, raises `MalformedOpenTagError` if regex fails, raises `MissingAttributeError` if any of `{id, ticket, author, session}` absent; accumulates body until `<!-- /argos:entry -->`, raises `UnclosedEntryError` if EOF reached first; on close, checks `id` against a seen-set, raises `DuplicateIdError` on collision. Returns the list of blocks in source order.
- Public function `parse_file(path: str | Path) -> list[Block]`: thin wrapper that reads the file and calls `parse`.
- Parser does NOT enforce section ordering or which top-level section a block belongs to — per ticket acceptance criterion, blocks within a section are unordered for parsing purposes. Section boundaries are out of scope for this parser (a future helper can group blocks by enclosing `## ` heading).
- Stderr error messages use exact substrings the acceptance criteria check for: `unclosed entry`, `duplicate id`, and (for missing attr) the missing attribute name plus a `line N:` prefix.

#### `argos/cli/commands/state_parse.py` (new — CLI shim)
- `main(argv: list[str]) -> int`: expects exactly one positional arg (path to a markdown file). On success: serialize the list of blocks as JSON (each block as an object with the four attributes plus `body`, `start_line`, `end_line`) to stdout, exit 0. On `StateBlockError`: write the exception's message to stderr, exit nonzero (use exit code 1 uniformly; per-error-class exit codes are out of scope).
- No JSON-schema doc for the stdout payload in this ticket (downstream consumers are internal; format can stabilize when a second consumer arrives).

#### `argos/cli/tests/__init__.py` (new — package marker)
- Empty file.

#### `argos/cli/tests/test_state_parser.py` (new — pytest)
- Fixture-driven tests using the four schema example files (resolve paths via `pathlib.Path(__file__).resolve().parents[2] / "specs" / "v1.0" / "schemas" / "examples" / ...`).
- `test_parse_valid_returns_blocks_with_required_attrs`: asserts at least one block, all four attributes populated.
- `test_unclosed_block_raises_unclosed_entry`: asserts `UnclosedEntryError` with `unclosed entry` in `str(exc)`.
- `test_duplicate_id_raises_with_offending_id`: asserts `DuplicateIdError`, `duplicate id` in message, and the duplicated `id` value in message.
- `test_missing_attr_names_attribute_and_line`: asserts `MissingAttributeError`, the attribute name in message, and a `line N:` prefix.
- CLI-level tests invoking the module via `subprocess.run([sys.executable, "-m", "argos.cli", "state-parse", str(fixture_path)], capture_output=True)`:
  - `test_cli_valid_exits_zero_and_emits_json`: exit code 0, stdout parses as JSON list, each entry has the four attributes.
  - `test_cli_unclosed_exits_nonzero_with_substring`: nonzero exit, `unclosed entry` in stderr.
  - `test_cli_duplicate_exits_nonzero_with_id`: nonzero exit, `duplicate id` and the offending id value both in stderr.
  - `test_cli_missing_attr_exits_nonzero_naming_attr`: nonzero exit, attribute name and `line ` substring in stderr.

### Acceptance criteria (restated, concrete)

1. `test -f argos/specs/v1.0/schemas/state-block.md` exits 0; `grep -E '^\| ?\`?id\`? ' argos/specs/v1.0/schemas/state-block.md` finds an attribute-table row; `grep -E '^\| ?\`?(ticket|author|session)\`? ' argos/specs/v1.0/schemas/state-block.md` finds rows for the other three required attributes.
2. `grep -F 'entries are append-only; never edit an existing entry; corrections are new entries that reference the prior \`id\`.' argos/specs/v1.0/schemas/state-block.md` exits 0 (verbatim invariant statement present).
3. `python3 -m argos.cli state-parse argos/specs/v1.0/schemas/examples/state-valid.md` exits 0; stdout parses as a JSON list; every entry has keys `id`, `ticket`, `author`, `session`.
4. `python3 -m argos.cli state-parse argos/specs/v1.0/schemas/examples/state-unclosed-block.md` exits nonzero; stderr contains the literal substring `unclosed entry`.
5. `python3 -m argos.cli state-parse argos/specs/v1.0/schemas/examples/state-duplicate-id.md` exits nonzero; stderr contains the literal substring `duplicate id` AND the offending `id` value.
6. `python3 -m argos.cli state-parse argos/specs/v1.0/schemas/examples/state-missing-attr.md` exits nonzero; stderr contains the missing attribute's name AND a `line ` prefix referring to the offending line number.
7. Parser correctly returns all blocks regardless of order within a section: a fixture (constructed inline in the test, no new file) with three valid blocks intermixed with prose paragraphs parses to a 3-element list with all attributes intact.
8. All pytest tests in `argos/cli/tests/test_state_parser.py` pass under `python3 -m pytest argos/cli/tests/test_state_parser.py -v` from the repo root.

### Test strategy

- **Test file:** `argos/cli/tests/test_state_parser.py`.
- **Verifier command (run from repo root):** `python3 -m pytest argos/cli/tests/test_state_parser.py -v`.
- **Test fixture sourcing:** the four schema example files double as test fixtures (`argos/specs/v1.0/schemas/examples/state-*.md`); no separate `tests/fixtures/` directory. Tests resolve paths from `__file__` so they work regardless of CWD as long as repo layout is intact.
- **No new runtime dependencies.** Parser uses standard library only (`re`, `dataclasses`, `pathlib`, `json`, `sys`). Pytest is the only test-time dependency and is already available on PATH (`/home/taddymason/.asdf/shims/pytest`); the verifier may need to ensure `pytest` is importable in the Python it runs (`python3 -m pip install pytest` into the active venv if `python3 -m pytest` fails).
- **Coverage target:** every public function (`parse`, `parse_file`) and every error class is exercised by at least one test; every CLI exit-code branch (success, each of the three error fixtures plus missing-attr) is exercised by a subprocess test.

### Open questions

The following are noted but **do not block coding** per the user's planning guidance — coder may proceed under the stated assumptions:

1. **Language ADR (ARG1-001).** ADR-001 has not landed; this ticket assumes Python because the ticket frontmatter explicitly names `.py` paths. If ARG1-001's ADR picks a non-Python language, this ticket's code is throwaway. Mitigation: schema doc and fixture markdown files are language-independent and survive the choice; only `state_parser.py` and the CLI shim would need re-skinning. Recommendation: land ADR-001 before this ticket if at all possible, but proceed with Python under the explicit assumption otherwise.
2. **CLI invocation form.** Acceptance criteria in the ticket use the form `argos state-parse <file>`; this plan implements the subcommand via `python3 -m argos.cli state-parse <file>` because the `argos` binary shim is ARG1-001's deliverable and not yet present. The verifier should treat the module-form invocation as satisfying the criterion. If a wrapper script is desired in this ticket, it is a one-line shell shim — but I have not added it because installing a shim onto `PATH` is an installer-level concern (see PRD §Distribution, "Packaging channel: TODO"). Coder: stick to the module form.
3. **Parser exit codes.** Plan uses uniform exit code 1 for all parser failures. The acceptance criteria only require "nonzero," so this is safe. Per-error-class exit codes can be added later if a downstream consumer needs them.

## Verification

**Verified:** 2026-04-26
**Decision:** PASS

### Criteria checks

1. **Schema doc exists with attribute table — PASS.**
   - Command: `test -f argos/specs/v1.0/schemas/state-block.md && echo "schema doc exists"`. Output: `schema doc exists` (exit 0).
   - Command: `grep -E '^\| ?\`?id\`? ' argos/specs/v1.0/schemas/state-block.md`. Output (exit 0):
     `| \`id\`      | \`{ISO-8601-UTC-timestamp}-{ticket-id}\` | \`2026-04-26T14:33:01Z-ARG-042\` | Globally unique within a single STATE.md file. Duplicates raise \`DuplicateIdError\`. |`
   - Command: `grep -E '^\| ?\`?(ticket|author|session)\`? ' argos/specs/v1.0/schemas/state-block.md`. Output (exit 0): three rows for `ticket`, `author`, `session` matched.

2. **Verbatim append-only invariant statement present — PASS.**
   - Command: `grep -F 'entries are append-only; never edit an existing entry; corrections are new entries that reference the prior \`id\`.' argos/specs/v1.0/schemas/state-block.md`. Exit 0; matched line begins with `> entries are append-only; never edit an existing entry; corrections are new entries that reference the prior \`id\`.`

3. **Valid fixture parses to JSON list with all four attrs per entry — PASS.**
   - Command: `python3 -m argos.cli state-parse argos/specs/v1.0/schemas/examples/state-valid.md` (exit 0). Stdout was a JSON list with one block; keys `id`, `ticket`, `author`, `session`, `body`, `start_line`, `end_line` present. Shape probe confirmed: `all_keys_present= True`, `count= 1`.

4. **Unclosed-block fixture exits nonzero with `unclosed entry` in stderr — PASS.**
   - Command: `python3 -m argos.cli state-parse argos/specs/v1.0/schemas/examples/state-unclosed-block.md`. Exit 1. Stderr: `state-parse: line 12: unclosed entry — open tag has no matching <!-- /argos:entry --> before EOF`.

5. **Duplicate-id fixture exits nonzero with `duplicate id` and offending id value — PASS.**
   - Command: `python3 -m argos.cli state-parse argos/specs/v1.0/schemas/examples/state-duplicate-id.md`. Exit 1. Stderr: `state-parse: line 26: duplicate id '2026-04-26T16:00:00Z-ARG-044' (block opened at line 21)`. Both `duplicate id` substring and the offending id `2026-04-26T16:00:00Z-ARG-044` appear verbatim.

6. **Missing-attr fixture exits nonzero with attr name and `line ` prefix — PASS.**
   - Command: `python3 -m argos.cli state-parse argos/specs/v1.0/schemas/examples/state-missing-attr.md`. Exit 1. Stderr: `state-parse: line 12: missing required attribute 'session' on open tag`. Contains attribute name `session` and the `line ` prefix.

7. **Parser handles arbitrary section ordering inside a section — PASS.**
   - Exercised by `test_blocks_unordered_within_section_all_returned`, which constructs an inline fixture with three valid blocks intermixed with prose paragraphs and asserts the returned list is a 3-element list with all attributes intact (ids, tickets, authors checked positionally). Pytest line: `argos/cli/tests/test_state_parser.py::test_blocks_unordered_within_section_all_returned PASSED [ 53%]`.

8. **All pytest tests pass — PASS (with host-env caveat).**
   - See Test run section below. 13/13 tests pass under the workaround command. The Plan's exact `python3 -m pytest ...` command is unrunnable on this host due to a pre-existing host environment issue (the active venv `/home/taddymason/.graphify-venv` has no pytest), called out in the Plan's Test strategy as a known verifier concern.

### Test run

**Plan's exact command:** `python3 -m pytest argos/cli/tests/test_state_parser.py -v`
- Output: `/home/taddymason/.graphify-venv/bin/python3: No module named pytest`
- Exit: 1
- Diagnosis: pre-existing host env condition (active venv lacks pytest); not a ticket failure. Plan's Test strategy explicitly anticipated this: "the verifier may need to ensure pytest is importable in the Python it runs."

**Workaround command (binding result):** `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest argos/cli/tests/test_state_parser.py -v` (uses asdf shim `pytest` on PATH which has a working python with pytest installed).
- Exit: 0
- Summary line: `============================== 13 passed in 0.12s ==============================`
- All 13 tests passed: `test_parse_valid_returns_blocks_with_required_attrs`, `test_parse_valid_dict_round_trips_to_json`, `test_unclosed_block_raises_unclosed_entry`, `test_duplicate_id_raises_with_offending_id`, `test_missing_attr_names_attribute_and_line`, `test_malformed_open_tag_raises`, `test_blocks_unordered_within_section_all_returned`, `test_empty_text_returns_empty_list`, `test_stray_close_tag_outside_block_is_ignored`, `test_cli_valid_exits_zero_and_emits_json`, `test_cli_unclosed_exits_nonzero_with_substring`, `test_cli_duplicate_exits_nonzero_with_id`, `test_cli_missing_attr_exits_nonzero_naming_attr`.

### Regression scan

- Grep for callers of the new `argos.cli` module across the repo (`grep -rn "from argos.cli\|import argos" --include="*.py"`): only intra-module references (`__main__.py`, `state_parse.py`, `test_state_parser.py`). No external consumers exist yet (this is the first Python code under `argos/`), so there is no regression surface to break.
- Full pytest run under `argos/`: `13 passed`, exit 0. No other Python tests exist in the repo.
- Files modified outside the ticket's plan: only the ticket file itself (Plan section appended by planner; Verification section appended now). All 12 new files match the Plan's "Files touched" table.

### Notes

- **Open question 1 (Plan):** language ADR (ARG1-001) not yet landed; this ticket assumed Python and the code paths remain consistent with that assumption. Recorded as known drift candidate if ADR-001 picks a non-Python language.
- **Open question 2 (Plan):** CLI invocation form is `python3 -m argos.cli state-parse ...` rather than the `argos state-parse ...` shim binary form. The `argos` shim binary is ARG1-001's deliverable; the verifier accepts the module form per the Plan. Acceptance criteria check this contract via the module form.
- **Open question 3 (Plan):** uniform exit code 1 for all parser failures is acceptable per acceptance criteria ("nonzero").
- **Host env issue:** the active venv lacks pytest. This is a pre-existing operator-machine condition, not a ticket-level fault; both watchdog and verifier worked around it via the asdf `pytest` shim.
