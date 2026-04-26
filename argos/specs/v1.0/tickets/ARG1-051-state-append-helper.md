# ARG1-051 — `argos state-append` CLI helper

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 6 (STATE.md migration + config split)

## Intent

Implement `argos state-append --section <name> --ticket <id> --author <agent> --session <id> --body-file <path>`: generates a unique block `id` (UTC ISO timestamp + ticket ID), wraps the body in canonical `<!-- argos:entry ... -->` comments, and appends to the named STATE.md section. Atomic write (write to temp + rename). The single chokepoint for STATE.md mutations — every writer (verifier, cycle-close) goes through here, not direct edits.

## Context

ARCHITECTURE.md §Contracts/Session→STATE.md specifies that all writes go through `argos state-append`. ARCHITECTURE.md §Invariants names atomic, append-only writes as load-bearing for concurrent-safe operation.

## Non-goals

- No section creation. If the named section is absent, the command fails (init owns scaffolding).
- No block deletion (cycle close has its own command, ARG1-054).
- No editing of existing blocks (forbidden by spec).
- No author validation beyond passing the value through to the block attribute (the pre-commit hook ARG1-032 enforces author=verifier).

## Acceptance criteria

- [ ] `argos state-append --section "Done this cycle" --ticket ARG1-099 --author verifier --session sess-test --body-file /tmp/body.md` exits 0; `argos/specs/STATE.md` contains a new block whose `id` matches `^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]+Z-ARG1-099$` and whose other attributes match the flags.
- [ ] The new block appears under the `## Done this cycle` heading and not in any other section; verified by parsing STATE.md and checking the block's enclosing section.
- [ ] Two concurrent `argos state-append` calls (distinct tickets) both succeed; both blocks present in the final file (`grep -c '<!-- argos:entry' argos/specs/STATE.md` increases by 2).
- [ ] Two concurrent `argos state-append` calls (same ticket, same second) produce distinct `id`s (random suffix tiebreaker); no block is overwritten.
- [ ] `argos state-append --section "Nonexistent" --ticket ARG1-099 --author verifier --session sess-test --body-file /tmp/body.md; echo $?` prints non-zero; stderr contains `section not found`.
- [ ] After interrupting `argos state-append` mid-write (kill -9), `argos/specs/STATE.md` is unchanged and parses cleanly via ARG1-050's parser (atomic write proven).
- [ ] `argos state-append --dry-run ...` prints the block that would be written to stdout and does not modify any file.

## Depends on

- ARG1-001 (CLI scaffold)
- ARG1-050 (block schema)

## Touches

- `argos/cli/commands/state_append.py` (or equivalent — new)
- `argos/cli/tests/test_state_append.py` (or equivalent)

## Parallelizable with

- ARG1-002 (init)
- ARG1-003 (status)
- ARG1-005 (attend)
- ARG1-010 (orchestrator agent)
- ARG1-011 (orchestrate slash command)
- ARG1-012 (dispatch log writer)
- ARG1-013 (auto-fix retry)
- ARG1-020 (worktree spawn)
- ARG1-021 (independence detection)
- ARG1-023 (worktree merge)
- ARG1-040 (escalation schema)
- ARG1-052 (merge driver)
- ARG1-053 (config split)

## Plan

**Sizing note.** Principal code surface is two Python files (library + CLI shim) plus one test file. Two additional file edits are integration glue: a one-line subcommand registration in `argos/cli/__main__.py` (the unified dispatcher established by ARG1-001 — every internal subcommand registers there) and the ticket file itself. Total: 2 new code files, 1 new test file, 1 dispatcher edit, 1 ticket-file edit. Below the 3-file/200-LOC default ceiling for the substantive work; the dispatcher edit is integration plumbing rather than independent scope.

**Language assumption.** Python ≥3.9, stdlib-only, per ADR-001 (ratified by ARG1-001). No new runtime dependencies. Test framework is `unittest` (matches ARG1-001 / ARG1-030 / ARG1-040; pytest is intentionally avoided here because ARG1-001's verifier confirmed pytest is host-env-fragile in this repo).

**Library / CLI split.** Mirrors ARG1-050's pattern (`state_parser.py` library + `commands/state_parse.py` CLI shim). The library exposes a small import-friendly API so the verifier subagent (or any future in-process writer) can call it without spawning a subprocess; the CLI shim handles flag parsing, body-file reading, and exit codes. The ticket's `Touches:` line names only the CLI module ("or equivalent"); the library file is the "or equivalent" expansion documented here.

**STATE.md path.** The acceptance criteria list the literal path `argos/specs/STATE.md`. The canonical v1.0 STATE.md is at `argos/specs/v1.0/STATE.md` (where ARG1-001 / ARG1-030 entries live). The CLI defaults `--state-file` to `argos/specs/v1.0/STATE.md`; the AC literal path is interpreted as "the canonical v1.0 STATE.md for this repo," in line with how ARG1-050's Open Question 2 reconciled `argos state-parse` (binary form) vs `python3 -m argos.cli state-parse` (module form). See Open questions.

### Files touched

| Path | Status | Purpose |
|------|--------|---------|
| `argos/cli/state_append.py` | new | Library: `build_block`, `generate_id`, `append_block`. Holds the file lock, atomic write, section search, ID-collision tiebreaker. Importable by verifier subagent code as `from argos.cli.state_append import append_block`. |
| `argos/cli/commands/state_append.py` | new | CLI shim: argparse for `--section`, `--ticket`, `--author`, `--session`, `--body-file`, `--dry-run`, `--state-file`; reads body file; calls into library; maps exceptions to exit codes and stderr substrings. |
| `argos/cli/__main__.py` | edit | Register `state-append` subcommand in unified dispatcher (one-line addition mirroring `state-parse` / `verifier-parse` / `escalation-validate` registrations). Update `INTERNAL_SUBCOMMANDS` tuple and `_print_usage` Internal-subcommands list. |
| `argos/cli/tests/test_state_append.py` | new | unittest tests for all seven acceptance criteria (basic append, section membership, concurrent distinct tickets, concurrent same-second same-ticket, section-not-found, atomic-write kill, dry-run). |
| `argos/specs/v1.0/tickets/ARG1-051-state-append-helper.md` | edit | This Plan section + Verification section (verifier phase). |
| `argos/specs/v1.0/STATE.md` | append | v1.0-format verifier block on pass (end of loop, verifier-only write). |

### Changes per file

#### `argos/cli/state_append.py` (new — library)

Public API:

- `generate_id(ticket: str, *, now: datetime | None = None, existing_ids: set[str], _rng: random.Random | None = None) -> str` — composes `{UTC-ISO-timestamp-to-seconds}-{ticket}`. If the candidate is in `existing_ids`, retries with a 6-hex-char random suffix (`{primary}-{abc123}`) until uniqueness, max 5 attempts (each draws fresh randomness). Uses UTC; format `%Y-%m-%dT%H:%M:%SZ` to match the schema example.

- `build_block(*, block_id: str, ticket: str, author: str, session: str, body: str) -> str` — composes the full block string: open tag + body (verbatim, trailing-newline-trimmed) + close tag, with a single trailing newline. The open-tag attribute order is `id ticket author session` (matches schema doc Table). The body is written verbatim — no escaping, no rewrapping.

- `class SectionNotFoundError(Exception)` — raised by `append_block` when the named section heading cannot be located.

- `append_block(state_file: Path, *, section: str, ticket: str, author: str, session: str, body: str, dry_run: bool = False, now: datetime | None = None) -> str` — the chokepoint. Returns the composed block string (whether it was written or just composed for dry-run).

  Logic:
  1. If `dry_run`: open `state_file` read-only, parse existing IDs (via `argos.cli.state_parser.parse_file`), generate ID, build block, return it without writing. (Read-only access still lets us avoid duplicate IDs in dry-run output.) If `state_file` doesn't exist in dry-run mode, ID generation falls back to empty `existing_ids`.
  2. Otherwise: open a sidecar lock file at `{state_file}.lock` with `O_CREAT | O_RDWR`; acquire `fcntl.flock(LOCK_EX)`. Hold the lock across all subsequent steps; release in a `finally`.
  3. Read current `state_file` text. Locate the `## {section}` line: scan for a line matching exactly `^## {re.escape(section)}\s*$`. If absent → raise `SectionNotFoundError(section)`.
  4. Parse existing block IDs via `argos.cli.state_parser.parse(text)` to feed `generate_id`'s `existing_ids` set.
  5. Generate unique ID; build block.
  6. Find insertion point: from the section heading line, scan forward for the next line matching `^## `; that line's index is the insert point (insert just before it). If no next `## ` heading exists (this is the last section), insert at end of file. Composed insertion includes a leading blank line for visual separation when content already exists in the section.
  7. Construct new file content: `before + insertion + after`. Where insertion is `"\n" + block + "\n"` (yielding one blank line before the open tag and one blank line between the close tag and the next heading / EOF, matching the existing STATE.md visual rhythm).
  8. Write to a temp file: `tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=state_file.parent, prefix=state_file.name + ".tmp.", delete=False)`. fsync the file before close (durability against crash-after-rename, optional but cheap). Then `os.replace(tmp.name, state_file)` — atomic rename on POSIX.
  9. **Test hook (only active when `ARGOS_TEST_DELAY_BEFORE_RENAME` env var is set to a number of seconds):** `time.sleep(float(env_var))` between temp-write and `os.replace`. This makes AC#6 deterministically testable: spawn the subprocess with the env var set, kill -9 during the sleep, assert original file is byte-identical and the temp file (orphaned) does not corrupt anything. The env var is undocumented runtime API; only the test reads it.
  10. Return the composed block.

  Edge cases:
  - `state_file` does not exist (non-dry-run): `SectionNotFoundError` (consistent — there's no section to append to).
  - `body` contains an open tag (`<!-- argos:entry`) or close tag (`<!-- /argos:entry`) substring: log a stderr warning and proceed. Per the schema, nested blocks are not permitted; we don't enforce that here (writers are trusted), but we surface a hint. This is a defensive courtesy; not an AC requirement.
  - `body` is empty: allowed; the block has no body lines between open and close.

#### `argos/cli/commands/state_append.py` (new — CLI shim)

```python
def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="argos state-append", ...)
    parser.add_argument("--section", required=True)
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--body-file", required=True)
    parser.add_argument("--state-file", default="argos/specs/v1.0/STATE.md")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    ...
```

- Read body from `--body-file` (special case: `--body-file -` reads stdin to support pipelines, not required by AC but trivially small).
- On body-file missing: stderr `state-append: body file not found: <path>`, exit 1.
- Call `append_block(...)` with the parsed args.
- On success non-dry-run: silent (exit 0). On success dry-run: write composed block to stdout, exit 0.
- On `SectionNotFoundError`: stderr `state-append: section not found: '<section>'`, exit 1. Substring `section not found` is the AC#5 contract.
- On other unexpected errors (IOError, lock failure): stderr `state-append: <message>`, exit 1.

#### `argos/cli/__main__.py` (edit — dispatcher registration)

Three small edits, all isomorphic to existing entries:

1. `INTERNAL_SUBCOMMANDS` tuple: append `"state-append"` so it's recognized as internal.
2. `_print_usage`: add a line `"  state-append          append a verifier-authored block to STATE.md\n"` under the `Internal subcommands:` heading.
3. Dispatch: add a new `if head == "state-append":` branch that does `from argos.cli.commands.state_append import main as state_append_main; return state_append_main(rest)`.

No other changes to `__main__.py`. No refactor.

#### `argos/cli/tests/test_state_append.py` (new — unittest)

Test class `StateAppendTests(unittest.TestCase)`. Helpers:

- `setUp` creates a fresh `tempfile.TemporaryDirectory()`; copies a minimal STATE.md fixture (with sections `## Current focus`, `## In progress`, `## Done this cycle`, `## Known drift`) to `<tmpdir>/STATE.md`; writes a body file `<tmpdir>/body.md` with canonical first-line bullet content.
- `_run(*flags)` invokes `argos/cli/argos` via `subprocess.run`, returning the CompletedProcess (mirrors `test_version.py`).

Tests (one per AC, plus body-verbatim):

1. `test_basic_append_creates_block_with_attrs` — invoke with all flags, `--state-file <tmpdir>/STATE.md`, `--ticket ARG1-099`. Assert exit 0. Re-parse STATE.md via `argos.cli.state_parser.parse_file`; find the new block; assert all four attributes match the flags; assert id regex `^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]+Z-ARG1-099$`. **Maps to AC#1.**

2. `test_block_appears_under_named_section_only` — same invocation; read STATE.md raw lines; locate the new block's open-tag line index; locate the most recent preceding `## ` heading; assert it equals `## Done this cycle`. Also assert no `## In progress` heading sits between `## Done this cycle` and the new block. **Maps to AC#2.**

3. `test_two_concurrent_distinct_tickets_both_present` — count `<!-- argos:entry` lines pre. Spawn two `subprocess.Popen` invocations with distinct tickets (`ARG1-098`, `ARG1-099`); `wait()` both; both must exit 0. Count `<!-- argos:entry` lines post; assert pre + 2 = post; both ticket IDs appear in the file. **Maps to AC#3.**

4. `test_two_same_second_same_ticket_get_distinct_ids` — call the library directly twice in the same test process with the same `ticket="ARG1-099"` and an injected `now=datetime(2026,4,26,14,33,1, tzinfo=UTC)`. First call's id is `2026-04-26T14:33:01Z-ARG1-099`; second call must collide on primary, retry with random suffix; assert second id matches `^2026-04-26T14:33:01Z-ARG1-099-[0-9a-f]{6}$`. Both blocks present in file, distinct ids, parser doesn't raise `DuplicateIdError`. **Maps to AC#4.**

5. `test_section_not_found_exits_nonzero` — invoke with `--section "Nonexistent"`. Assert exit non-zero; assert `section not found` substring in stderr. **Maps to AC#5.**

6. `test_atomic_write_kill_leaves_file_unchanged` — record SHA-256 of `<tmpdir>/STATE.md`. Spawn the CLI with env `ARGOS_TEST_DELAY_BEFORE_RENAME=2.0`; sleep 0.5s (to let it pass arg parse and reach the temp-write); `proc.kill()` (SIGKILL); `proc.wait()`. Assert: STATE.md SHA-256 unchanged; `parse_file(STATE.md)` raises no exception; no leftover `.tmp.` files cause issues for a subsequent normal append (run a second `_run(...)` and confirm exit 0). **Maps to AC#6.**

7. `test_dry_run_prints_block_and_does_not_modify_file` — record SHA pre. Invoke with `--dry-run`. Assert exit 0; stdout contains `<!-- argos:entry id=` and `<!-- /argos:entry -->`; SHA post equals SHA pre. **Maps to AC#7.**

8. `test_body_content_preserved_verbatim` — body file contains a multi-line markdown bullet list with backticks, asterisks, an em-dash, and trailing whitespace on one line. After append, parser's `Block.body` must equal the input body modulo a single trailing newline-strip. (Defensive — AC doesn't require it but the spec's "preserved verbatim" rule does.)

### Acceptance criteria (restated, concrete)

The verifier runs each command and asserts the named contract.

1. `python3 -m argos.cli state-append --section "Done this cycle" --ticket ARG1-099 --author verifier --session sess-test --body-file <body-tmp> --state-file <state-tmp>` exits 0; the new block parses cleanly, its `id` attribute matches `^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]+Z-ARG1-099$`, and `ticket=ARG1-099 author=verifier session=sess-test`.
2. The new block's open-tag line is preceded (with no intervening `## ` heading) by the `## Done this cycle` heading line.
3. Two subprocesses (`ARG1-098`, `ARG1-099`) launched concurrently both exit 0; `grep -c '<!-- argos:entry' <state-tmp>` post-run equals pre-run + 2.
4. Two library calls with the same ticket and the same `now=` produce ids `X` and `X-{6hex}`; both blocks present; parser sees no `DuplicateIdError`.
5. `python3 -m argos.cli state-append --section "Nonexistent" ...; echo $?` prints non-zero; stderr substring `section not found` present.
6. Subprocess killed (SIGKILL) during `ARGOS_TEST_DELAY_BEFORE_RENAME` sleep leaves STATE.md byte-identical (SHA-256 match) and parser-clean; subsequent normal `state-append` succeeds.
7. `python3 -m argos.cli state-append --dry-run ...` exits 0; stdout contains a complete block; SHA-256 of state-file is unchanged.

### Test strategy

- **Test file:** `argos/cli/tests/test_state_append.py`.
- **Test command (verifier runs from repo root):** `python3 -m unittest argos.cli.tests.test_state_append -v`. Stdlib-only; no third-party deps.
- **Regression scope:** Verifier additionally runs the existing test suites — `python3 -m unittest argos.cli.tests.test_version argos.cli.tests.test_verifier_parser argos.cli.tests.test_escalation_validator argos.cli.tests.test_state_append -v` — to confirm no regression in ARG1-001 / ARG1-030 / ARG1-040 wiring (the dispatcher edit touches `__main__.py` which `test_version.py` exercises). The pre-existing pytest-gated `test_state_parser.py` is unchanged and not run here.
- **No new runtime deps.** `pyproject.toml` is not modified. ADR-001's stdlib-only contract is preserved.

### Open questions

Noted but **do not block coding** under the stated assumptions:

1. **AC literal path `argos/specs/STATE.md` vs. canonical v1.0 path `argos/specs/v1.0/STATE.md`.** The ticket's AC#1 quotes the older flat path; the canonical v1.0 STATE.md (where ARG1-001 / ARG1-030 entries live) is at `argos/specs/v1.0/STATE.md`. The CLI defaults `--state-file` to the v1.0 path; the verifier interprets the AC literal as targeting the canonical v1.0 STATE.md. Mirrors ARG1-050's Open Question 2 (module-vs-binary CLI form). If a future ticket establishes a flat `argos/specs/STATE.md` symlink or moves the file, the default flips trivially.
2. **Lock file location.** Sidecar lock at `{state_file}.lock` is the cleanest stdlib-only option (`fcntl.flock` on the STATE.md file itself works but interacts awkwardly with the file being replaced via rename). The lock file is stable across renames and self-cleans logically (the lock is released when the FD is closed; the file's continued existence on disk is harmless and gitignored — TODO: add `.lock` to `.gitignore` in a follow-up ticket; out of scope here).
3. **AC#6 testability.** The kill-mid-write AC is non-deterministic without a hook. The `ARGOS_TEST_DELAY_BEFORE_RENAME` env var is the minimum surface needed to make it deterministic. The hook is internal API (no operator-visible flag); name is namespaced with `ARGOS_TEST_` so it's clearly test-only.
4. **Authorship enforcement.** Per ticket Non-goals: "No author validation beyond passing the value through." `--author orchestrator` would be accepted as readily as `--author verifier`. The pre-commit hook (ARG1-032) enforces author=verifier on STATE.md changes by author identity, not by this flag. This ticket is the chokepoint for *format*, not for *authorization*.

### Observations (planner notes — do not block)

- **ARG1-050 STATE.md ledger gap.** ARG1-050 is verified per its ticket file (`Verified: 2026-04-26 / Decision: PASS`, all 8 ACs met) and its deliverables (`state_parser.py`, schema doc, fixtures) are on disk and used by ARG1-001's verification. However, no dedicated `<!-- argos:entry id=...-ARG1-050 -->` block exists in `argos/specs/v1.0/STATE.md` — only an indirect reference inside ARG1-001's verified block. This is a process-level ledger gap that the very helper this ticket builds will close going forward; it does not invalidate ARG1-050's work as a dependency. Recommendation: backfill an ARG1-050 STATE.md block as a one-line follow-up after ARG1-051 lands and ARG1-051's helper itself can write it. Not a blocker for this ticket.

## Verification

**Verified:** 2026-04-26
**Decision:** PASS

### Criteria checks

1. **Basic append produces a block with id matching the regex and attrs matching flags — PASS.**
   - Test: `argos.cli.tests.test_state_append.StateAppendCLITests.test_basic_append_creates_block_with_attrs`. Subprocess invocation with all flags exits 0; reparsing STATE.md via `argos.cli.state_parser.parse_file` returns 2 blocks (seed + new); the new block has `ticket=ARG1-099`, `author=verifier`, `session=sess-test`, and `id` matching `^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]+Z-ARG1-099$`.
   - Test result: PASS.

2. **Block appears under `## Done this cycle` and not in any other section — PASS.**
   - Test: `test_block_appears_under_named_section`. After append, scans STATE.md raw lines, finds the new block's open-tag line, walks back to the most recent `## ` heading, asserts equality with `## Done this cycle`, and asserts no other `## ` heading sits between that heading and the new block.
   - Test result: PASS.

3. **Two concurrent calls (distinct tickets) both succeed; both blocks present — PASS.**
   - Test: `test_two_concurrent_distinct_tickets_both_present`. Spawns two `subprocess.Popen` invocations with `ARG1-098` and `ARG1-099`; both exit 0. `<!-- argos:entry` count post = pre + 2. Both ticket IDs found in parsed blocks. The `fcntl.flock(LOCK_EX)` on the sidecar `STATE.md.lock` serializes the two appends.
   - Test result: PASS.

4. **Two concurrent calls (same ticket, same second) produce distinct ids (random suffix tiebreaker) — PASS.**
   - Test: `test_two_same_second_same_ticket_get_distinct_ids`. Library-level: two `append_block` calls with frozen `now=datetime(2026,4,26,14,33,1, tzinfo=UTC)` and `ticket="ARG1-099"`. First id = `2026-04-26T14:33:01Z-ARG1-099`. Second id matches `^2026-04-26T14:33:01Z-ARG1-099-[0-9a-f]{6}$`. Parser sees both blocks with no `DuplicateIdError`.
   - Test result: PASS.

5. **`--section "Nonexistent"` exits non-zero with `section not found` in stderr — PASS.**
   - Test: `test_section_not_found_exits_nonzero`. Subprocess invocation with `--section Nonexistent` exits non-zero; `result.stderr` contains the literal substring `section not found`.
   - Test result: PASS.

6. **SIGKILL mid-write leaves STATE.md byte-identical and parser-clean — PASS.**
   - Test: `test_atomic_write_kill_leaves_file_unchanged`. Spawns the CLI with `ARGOS_TEST_DELAY_BEFORE_RENAME=5.0`; sleeps 1.0s (deterministically inside the post-fsync, pre-rename delay window); `proc.kill()`. SHA-256 of STATE.md matches pre-state exactly. `parse_file(STATE.md)` returns the original 1-block list with no exception. A subsequent normal `state-append` call exits 0 — confirming no stale lock/temp-file state corrupts subsequent writes.
   - Test result: PASS.

7. **`--dry-run` prints block to stdout and does not modify the file — PASS.**
   - Test: `test_dry_run_prints_block_and_does_not_modify_file`. Subprocess with `--dry-run` exits 0; stdout contains `<!-- argos:entry id=`, `ticket=ARG1-099`, and `<!-- /argos:entry -->`. SHA-256 of STATE.md matches pre-state exactly.
   - Test result: PASS.

### Test run

**Command:** `python3 -m unittest argos.cli.tests.test_state_append -v`
- Exit: 0
- Summary line: `Ran 12 tests in 1.231s` ... `OK`
- All 12 tests passed: `test_build_block_shape`, `test_generate_id_appends_suffix_on_collision`, `test_generate_id_primary_when_no_collision`, `test_section_not_found_dry_run`, `test_atomic_write_kill_leaves_file_unchanged`, `test_basic_append_creates_block_with_attrs`, `test_block_appears_under_named_section`, `test_body_content_preserved_verbatim`, `test_dry_run_prints_block_and_does_not_modify_file`, `test_section_not_found_exits_nonzero`, `test_two_concurrent_distinct_tickets_both_present`, `test_two_same_second_same_ticket_get_distinct_ids`.

**Regression command:** `python3 -m unittest argos.cli.tests.test_version argos.cli.tests.test_verifier_parser argos.cli.tests.test_escalation_validator argos.cli.tests.test_state_append -v`
- Exit: 0
- Summary line: `Ran 27 tests in 1.347s` ... `OK`
- ARG1-001 (CLI scaffold), ARG1-030 (verifier parser), ARG1-040 (escalation validator) tests all still pass. The dispatcher edit does not regress any of them.

**Smoke check (CLI on the live repo STATE.md, dry-run):**
- Command: `python3 -m argos.cli state-append --section "Done this cycle" --ticket ARG1-099 --author verifier --session sess-smoke --body-file /tmp/body.md --dry-run --state-file argos/specs/v1.0/STATE.md`
- Exit: 0
- Stdout contained a well-formed block: `<!-- argos:entry id=2026-04-26T22:56:43Z-ARG1-099 ticket=ARG1-099 author=verifier session=sess-smoke --> ... <!-- /argos:entry -->`.
- Repo STATE.md SHA-256 unchanged after dry-run: `7b7e9c7166a8f656495f5f7e439b33a0484268f5b4dec281f71f246e1c45c883`.

**Smoke check (--help integration):**
- Command: `python3 -m argos.cli --help | grep state-`
- Output: `state-parse  parse STATE.md append-mostly blocks` and `state-append  append a block to a STATE.md section` — confirms dispatcher registration is wired into the unified `--help` listing alongside the existing internal subcommands.

### Findings

- 0 critical
- 0 major
- 0 minor

### Regression scan

- `pyproject.toml` unchanged — ADR-001 stdlib-only contract preserved.
- `git diff` shows only 5 files affected (3 new, 2 edited): `argos/cli/state_append.py`, `argos/cli/commands/state_append.py`, `argos/cli/tests/test_state_append.py`, `argos/cli/__main__.py`, `argos/specs/v1.0/tickets/ARG1-051-state-append-helper.md`. All match the Plan's "Files touched" table.
- `argos/cli/__main__.py` edits are three isomorphic additions (tuple, usage line, dispatch branch); behavior of pre-existing `state-parse`, `verifier-parse`, `escalation-validate` paths is unchanged (regression suite confirms).
- The pre-existing pytest-gated `test_state_parser.py` is not run by this ticket's verifier; it remains gated on pytest from ARG1-050's host-env caveat.

### Notes

- **Open question 1 (Plan):** the AC text's literal path `argos/specs/STATE.md` is reconciled by defaulting `--state-file` to `argos/specs/v1.0/STATE.md` (canonical v1.0 location). The verifier reads the AC literal path as targeting the canonical v1.0 STATE.md, mirroring ARG1-050's binary-vs-module reconciliation. Tests use temp files via `--state-file` so no production STATE.md was modified during testing.
- **Open question 3 (Plan):** the `ARGOS_TEST_DELAY_BEFORE_RENAME` env var is necessary to make AC#6 (kill-mid-write) deterministic. The hook is internal API (no operator-visible flag), name-spaced with `ARGOS_TEST_` so it's clearly test-only, and reads the value via `os.environ.get` (absent or empty → no delay).
- **Observation 1 (Plan):** the ARG1-050 STATE.md ledger gap is now structurally closeable — this ticket's helper is the mechanism to backfill it. Recommended one-line follow-up after ARG1-051 lands.
