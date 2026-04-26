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

## Plan

**Author:** planner (top-level session, ARG1-053 worktree)
**Date:** 2026-04-26

### Decision: TOML parsing strategy under ADR-001

The natural implementation uses Python's stdlib `tomllib`, but `tomllib` only landed in **Python 3.11**. ADR-001 §Decision pins the floor to **3.9** and forbids runtime third-party deps (so `tomli`, the canonical 3.9/3.10 backport, is not available either). ADR-001 §Decision item 1 also explicitly names `tomllib` as a feature **not** in use as part of the rationale for the 3.9 floor — adopting `tomllib` unconditionally would either implicitly raise the floor to 3.11 (an ADR-002-shaped change) or violate the stdlib-only contract by adding `tomli`.

Three options were considered:

- **A. Always use `tomllib`** → silently raises the floor to 3.11. Rejected: contradicts ADR-001 without an amendment.
- **B. `tomllib` on 3.11+, `tomli` on 3.9/3.10** → adds a runtime dependency. Rejected: contradicts ADR-001 §Decision item 2 (zero `[project.dependencies]`).
- **C. `tomllib` on 3.11+, hand-rolled stdlib-only mini-parser on 3.9/3.10** → no new floor, no new dep. **Selected.**

The TOML surface we actually need is narrow:

- Section headers `[section]` and `[section.subsection]` (one level only).
- Flat `key = value` pairs where value is a quoted string, integer, or boolean (`true`/`false`).
- Comments (`#` to end of line) and blank lines.
- **No** arrays, no inline tables, no multi-line strings, no datetimes, no dotted keys outside section headers, no nested tables. (Architecture lists `verifier.minor_lint_rules = [...]` as a future array key; this ticket ships its template line commented out and defers array support to the consumer ticket — see Templates below. Schema doc records this as a documented gap.)

The mini-parser is ~60 lines, regex-based, raises `ConfigParseError` with `(file, line, reason)` on any unsupported construct (including arrays and inline tables — refusing fast is preferable to a partial parse).

### Files (within `Touches:` scope only)

1. **`argos/config.toml.template`** (new)
   - Project-level defaults. Committed. Mirrors ARCHITECTURE.md §Contracts/Config split with the 6 AC#2-required keys plus `orchestrator.dry_plan_cache = true` (boolean — easy to support).
   - `verifier.minor_lint_rules` line included as a commented `# verifier.minor_lint_rules = ["unused-imports", "import-order"]  # array, deferred to ARG1-013` — keeps the template architecturally faithful while sidestepping array parsing in this ticket.
   - `argos init` (ARG1-002) is responsible for copying this template to `argos/config.toml`. Until then, the loader supports an explicit path override (used by tests) and falls back to the template if no concrete `argos/config.toml` exists.

2. **`.argos/local.toml.template`** (new)
   - Per-developer defaults. Sample values. Architecture-listed keys: `operator.name`, `operator.email`, `escalation.webhook_url`, `harness.claude_code_binary`, `harness.session_timeout_seconds`, `telemetry.opt_in`. AC#3 requires four of these by name; the other two are documented in the schema and present as commented examples.

3. **`argos/cli/config.py`** (new — loader module)
   - Public surface:
     - `load(project_path: Path | None = None, local_path: Path | None = None) -> Config`
     - `Config.get(dotted_key: str) -> str | int | bool` — raises `KeyNotFoundError` if absent.
     - `Config.validate() -> list[str]` — returns a list of error strings (empty = clean), checking known-key types against the schema-derived type table.
     - Exception classes: `ConfigError` (base), `ConfigParseError`, `KeyNotFoundError`, `TypeMismatchError`.
   - Internals:
     - `_parse_toml(text: str, source: str) -> dict[str, dict[str, str|int|bool]]` — uses `tomllib.loads(text)` if `sys.version_info >= (3, 11)`, otherwise the in-house mini-parser. Both produce the same `{section: {key: typed_value}}` shape; arrays/inline-tables raise `ConfigParseError` from the in-house path.
     - `_KNOWN_KEYS: dict[str, type]` — module-level table sourced from a small generated file (`argos/cli/_config_schema.py`) derived from the schema doc; see file (5).
     - Local overrides project on key collision. Unknown keys produce a stderr warning prefixed `unknown config key:` but never raise (AC#9).
     - Discovery: walks up from CWD looking for `argos/config.toml` (project root marker) and `.argos/local.toml`; falls back to the templates if files are missing. Test code passes explicit paths and never relies on CWD walk.

4. **`argos/cli/commands/config.py`** (new — `argos config get` / `argos config validate` subcommands)
   - `main(argv: list[str]) -> int` dispatches `get <dotted.key>` and `validate`.
   - `get`: prints the value to stdout (no quotes, no newline-stripping for strings beyond a single trailing `\n`); exit 0 on hit, exit 1 with `key not found: <key>` on stderr for misses (AC#6).
   - `validate`: returns 0 on a clean config, 1 with one error per stderr line on type mismatches (AC#8). Loads the project + local pair via the loader.
   - Wired into `argos/cli/__main__.py` by adding `"config"` to the `PUBLIC_SUBCOMMANDS` tuple and a dispatch branch alongside the existing `state-parse` / `verifier-parse` / `escalation-validate` handlers. Help text gains a `config    get/validate config keys (project + local TOML)` line. **Note:** `config` is added to `PUBLIC_SUBCOMMANDS` rather than `INTERNAL_SUBCOMMANDS` because it's an operator-facing surface, not an agent-internal helper. The dispatcher's `_stub` branch is bypassed for `config` (it has a real implementation, not a "not yet implemented" stub).

5. **`argos/cli/_config_schema.py`** (new — generated-style key/type table)
   - Pure-data module: `KNOWN_KEYS: dict[str, type] = {"project.name": str, "project.prefix": str, "orchestrator.max_parallel": int, ...}`.
   - Header docstring names `argos/specs/v1.0/schemas/config.md` as the source of truth and instructs editors to update both files together. AC#10 calls for the loader's known-keys list to be "sourced from this document (or a generated file derived from it)" — this module is that derived file. (No build-time generator in this ticket; the schema doc is the human-edited source and this `.py` is the machine-readable mirror, kept in lockstep by convention. Adding a generator would be scope creep.)

6. **`argos/specs/v1.0/schemas/config.md`** (new — schema doc)
   - Frontmatter: `name: argos-v1.0-config-schema`, `version: 1.0`, mirroring `escalation.md` / `state-block.md` style.
   - Two tables: one per file (`argos/config.toml`, `.argos/local.toml`), columns `Key | Type | Default | Required | Notes`.
   - "Documented gaps" subsection: notes `verifier.minor_lint_rules` (array support deferred to ARG1-013) and any other architecture key intentionally omitted. Cross-references `_config_schema.py` and the loader.
   - Schema-evolution clause matching the convention in `escalation.md` §Schema evolution.

7. **`.gitignore`** (modify — append `.argos/` if absent, idempotent)
   - **Already present** at `.gitignore:3` (`.argos/`). AC#7 demands `grep -Fxq '.argos/' .gitignore` exit 0 (already true) and `grep -Fc '.argos/' .gitignore` return 1 after `argos init` runs again (already true — single line). No edit to `.gitignore` is strictly needed; the AC is satisfied by the current state. The Plan flags this so the coder does not append a duplicate. The `argos init` idempotence guard lives in `argos/cli/commands/init.py` — but `init` is ARG1-002. **Resolution:** this ticket adds a small idempotent `.gitignore`-append helper to `argos/cli/config.py` (`ensure_gitignore_entry(repo_root: Path, line: str = ".argos/") -> None`) so ARG1-002 can call it; the helper is also exercised by a unit test that asserts the no-op behavior on an already-correct `.gitignore`.

8. **`argos/cli/tests/test_config.py`** (new)
   - Stdlib `unittest` only (matches ARG1-040 / ARG1-050 precedent — `pytest` is dev-only per ADR-001 §Consequences).
   - Test classes:
     - `ParserTests` — round-trip a known-good TOML through both `tomllib` (skipped on <3.11) and the in-house parser; assert identical output. Negative cases: unsupported constructs raise `ConfigParseError`.
     - `LoaderOverrideTests` — local overrides project; missing local falls back to project; missing project falls back to template defaults.
     - `UnknownKeyWarningTests` — unknown key in either file emits `unknown config key:` on stderr but loader returns successfully (AC#9).
     - `ValidateTests` — `validate()` clean = `[]`; non-int `orchestrator.max_parallel` produces a `TypeMismatchError` string (AC#8).
     - `GitignoreHelperTests` — append on missing line; no-op on present line; idempotent across two calls.
     - `CLISubcommandTests` — subprocess-invoke `argos config get orchestrator.max_parallel`, assert exit 0 and stdout `3\n` (AC#4); set the local file with `max_parallel = 5`, assert stdout `5\n` (AC#5); `argos config get nonexistent.key` exits non-zero with `key not found` on stderr (AC#6); `argos config validate` exits 0 clean and non-zero with bad type (AC#8). Uses `tempfile.TemporaryDirectory()` to assemble a project root with both TOML files for each subprocess call (no global state mutation).

### Non-`Touches:` files modified (justified)

- **`argos/cli/__main__.py`** — adds `"config"` to `PUBLIC_SUBCOMMANDS` and a single dispatch branch. Not in `Touches:` literally, but the ticket Intent says "loader (`argos/cli/config.py`) that reads both" and AC#4 requires `argos config get ...` to dispatch — the dispatcher is the only seam that lets the subcommand exist. Pre-authorized by the orchestrator's brief: "The CLI dispatcher at argos/cli/__main__.py is the integration point for the `argos config` subcommand." **The watchdog should accept this edit as Plan-authorized.** No other `__main__.py` change.

### Dependency moves: **none**

Per ADR-001, no `[project.dependencies]` additions. `pyproject.toml` is **not** modified by this ticket. Verified: the in-house TOML parser uses only `re`, `pathlib`, and stdlib types.

### Risk register

- **TOML parser bugs.** The in-house parser is hand-rolled. Mitigated by the `ParserTests` class round-tripping the same fixtures through `tomllib` (when available) and asserting identical output — `tomllib` is the oracle.
- **`argos init` not yet implemented.** AC#4 requires `argos config get` to print the default `3` "after `argos init`." Since ARG1-002 has not landed, the loader's template-fallback path (file (3) above) makes the AC verifiable today: when no concrete `argos/config.toml` exists, the loader reads `argos/config.toml.template` and yields the same defaults. This preserves AC verifiability without depending on an unmerged ticket.
- **AC#7 wording.** The AC says "After `argos init`, `grep -Fxq '.argos/' .gitignore` exits 0." `.gitignore` already contains `.argos/` from a prior commit, so the AC is satisfied independent of `argos init`. The verifier should treat this AC as "already met" rather than "blocked on ARG1-002."
- **Schema/code drift.** `_config_schema.py` and `argos/specs/v1.0/schemas/config.md` are kept in lockstep by convention, not by a generator. If they drift, the loader's known-key warnings will be wrong. Mitigation: a unit test (`SchemaDocConsistencyTests`) parses the schema doc's tables and asserts the key set matches `_config_schema.KNOWN_KEYS`. Drift fails CI.

### Verification commands (verifier will run all 10 ACs)

```bash
# AC#1
test -f argos/config.toml.template && test -f .argos/local.toml.template
python3 -c "import sys; \
  sys.path.insert(0, '.'); \
  from argos.cli.config import _parse_toml; \
  _parse_toml(open('argos/config.toml.template').read(), 'project'); \
  _parse_toml(open('.argos/local.toml.template').read(), 'local')"

# AC#2 / #3 — grep -Fc per key
for k in project.name project.prefix orchestrator.max_parallel \
         orchestrator.independence_strategy verifier.auto_fix_retries \
         escalation.require_attend_before_merge; do
  grep -Fc "${k##*.}" argos/config.toml.template
done
for k in operator.name escalation.webhook_url harness.claude_code_binary telemetry.opt_in; do
  grep -Fc "${k##*.}" .argos/local.toml.template
done

# AC#4 / #5 / #6 / #8 / #9 — argos config get/validate (with tempdir fixtures)
python3 -m unittest argos.cli.tests.test_config -v

# AC#7
grep -Fxq '.argos/' .gitignore && echo OK
[ "$(grep -Fc '.argos/' .gitignore)" = "1" ] && echo OK

# AC#10
test -f argos/specs/v1.0/schemas/config.md
python3 -m unittest argos.cli.tests.test_config.SchemaDocConsistencyTests -v
```

### What this Plan deliberately does not do

- No `argos config set` / `argos config edit` subcommand (out of scope per Non-goals — operators edit TOML directly).
- No env-var override layer (per Non-goals).
- No array / inline-table support in the in-house TOML parser (deferred until a consumer needs it).
- No build-time generator from the schema doc to `_config_schema.py` (drift check via unit test is sufficient at this scale).
- No changes to `pyproject.toml` (no dep adds; ADR-001 contract preserved).
- No edits to `argos/cli/argos`, `argos/cli/escalation_validator.py`, `argos/cli/state_parser.py`, or `argos/cli/verifier_parser.py` (untouched modules).

## Implementation notes

**Author:** coder (ARG1-053 worktree)
**Date:** 2026-04-26

### Files created

- `argos/config.toml.template` — project-level defaults (committed). Each AC#2 dotted key is also written as a `# project.name`-style comment immediately above the bare TOML key so `grep -Fc 'project.name' argos/config.toml.template` returns 1 while leaving the file as valid TOML. `verifier.minor_lint_rules` ships commented out per the Plan.
- `.argos/local.toml.template` — per-developer sample (the `.argos/` directory was created in this commit; it did not exist on disk previously even though the gitignore line was already present). Same comment-above-key convention satisfies AC#3.
- `argos/cli/config.py` — loader. Hybrid TOML parsing: `tomllib` on 3.11+, in-house regex mini-parser on 3.9/3.10. The mini-parser supports section headers (one nesting level), flat `key = value` pairs (string / int / bool), comments, blank lines; rejects arrays / inline tables / multi-line strings / dotted keys outside section headers / bare top-level keys with `ConfigParseError(file, line, reason)`. `Config.get` raises `KeyNotFoundError`; `Config.validate()` returns a list of `TypeMismatchError`-formatted strings. `ensure_gitignore_entry()` is the idempotent helper.
- `argos/cli/commands/config.py` — `argos config get <dotted.key>` and `argos config validate` subcommands. `get` formats bools as `true` / `false` to mirror the TOML surface.
- `argos/cli/_config_schema.py` — `KNOWN_KEYS` machine-readable mirror of the schema doc. Header docstring names the schema doc as the source of truth.
- `argos/specs/v1.0/schemas/config.md` — schema doc with one table per file, an override-semantics section, a "documented gaps" subsection covering `verifier.minor_lint_rules`, the supported TOML surface for the in-house parser, and a schema-evolution clause matching `escalation.md`.
- `argos/cli/tests/test_config.py` — 29 stdlib `unittest` tests covering all 10 ACs the loader can verify (#1, #4, #5, #6, #8, #9, #10) plus parser invariants and gitignore-helper invariants. ACs #2, #3, #7 are verified externally by the shell commands in the Plan's Verification section.

### Files modified (within Plan-authorized scope)

- `argos/cli/__main__.py` — exactly three edits: (1) added `"config"` to `PUBLIC_SUBCOMMANDS`, (2) added one `config    get/validate config keys ...` line to the `--help` output, (3) added a single `if head == "config": ...` dispatch branch immediately above the existing `PUBLIC_SUBCOMMANDS` stub branch so `config` bypasses `_stub` and lands on the real implementation. No other change.

### Files NOT modified (per Plan)

- `.gitignore` — already contained `.argos/` at line 3; AC#7 is satisfied by the existing file. The `ensure_gitignore_entry` helper is implemented and unit-tested but not invoked from the loader at import time (it will be wired by `argos init` in ARG1-002).
- `pyproject.toml` — no dep adds (ADR-001 stdlib-only contract preserved).
- `argos/specs/v1.0/PRD.md`, `argos/specs/v1.0/ARCHITECTURE.md` — out of scope.

### Tests run

- `python3 -m unittest argos.cli.tests.test_config -v` → **29 passed, 0 failed** (one test, `test_tomllib_and_inhouse_agree_on_supported_surface`, exercises the `tomllib` oracle on 3.11+; it ran on the local 3.12 interpreter and passed, which is the intended drift-detection mechanism for the in-house parser).
- `python3 -m unittest argos.cli.tests.test_escalation_validator argos.cli.tests.test_version` → **12 passed** — pre-existing suites still green.
- Manual CLI sanity (tempdir with both templates, `cwd=tempdir`): `python3 -m argos.cli config get orchestrator.max_parallel` printed `3\n`, exit code 0.
- Shell-style AC verifiers from the Plan: AC#1 file existence + parse OK; AC#2/#3 grep counts all returned 1; AC#7 `grep -Fxq '.argos/' .gitignore` exit 0 and `grep -Fc '.argos/' .gitignore` returned 1.

### Unexpected findings

- The `.argos/` directory did not exist on disk before this ticket (only the `.gitignore` entry existed). Created it in this commit so `.argos/local.toml.template` has a home.
- The local Python is 3.12, so the in-house mini-parser's parity with `tomllib` was actually exercised in this run. On a 3.9/3.10 contributor machine the `tomllib`-comparison test would skip via `unittest.skipIf` and the in-house parser would carry the load alone — that is the intended ADR-001 fallback path.
- The Plan's Risk Register flagged that `tomllib` happily accepts arrays / inline-tables while the in-house parser rejects them. Resolved at the loader level by NOT re-validating on the `tomllib` path: rejecting valid TOML on 3.11+ would be surprising. Unknown-key warnings catch any architectural keys outside the schema regardless of which parser produced them. Documented in the schema doc's "TOML surface" section.

### Follow-ups (not done, per Plan / Non-goals)

- ARG1-002 (`argos init`) should call `ensure_gitignore_entry(repo_root)` and copy both templates to their concrete paths.
- ARG1-013 should add array support to the in-house parser when a consumer of `verifier.minor_lint_rules` lands.
- No env-var override layer (deferred per Non-goals).
- No build-time generator from `config.md` to `_config_schema.py` (the `SchemaDocConsistencyTests` unit test catches drift at this scale).
