# ARG1-031 — Verifier writes structured decision into STATE.md block

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 4 (Severity-tiered verifier)

## Intent

Wire the verifier's structured output (ARG1-030) into a STATE.md append. On `pass`, write a `verified` block. On `pass-with-minors`, write a `verified-with-minors` block listing the minor findings. On `fail`, write a `verification-failed` block summarizing the critical/major findings. All writes go through `argos state-append` (ARG1-051) so the merge driver and block-id generator stay in one place. Update `.claude/agents/verifier.md` to invoke this command.

## Context

ARCHITECTURE.md §Components/Severity-Tiered Verifier specifies that the verifier remains the sole writer of STATE.md and that minor findings are logged-and-continued. ARCHITECTURE.md §Contracts/Session→STATE.md mandates writes go through the helper, not direct edits.

## Non-goals

- No retry triggering (ARG1-013).
- No alteration of existing STATE.md sections (writes go to "In progress" on start, "Done this cycle" on finish — already-defined).
- No human-readable summary block beyond what the schema requires.

## Acceptance criteria

- [ ] On a synthetic verifier run with `decision: pass`, `argos/specs/STATE.md` gains exactly one new block matching `<!-- argos:entry .* author=verifier .* -->` containing the literal `verified` and the ticket ID.
- [ ] On a synthetic verifier run with `decision: pass-with-minors` and two minor findings, the new STATE.md block contains the literal `verified-with-minors`, both finding `file:line` references, and counts `0 critical, 0 major, 2 minor`.
- [ ] On a synthetic verifier run with `decision: fail` and one critical finding, the new STATE.md block contains the literal `verification-failed` and the verbatim test stdout (verified by `grep -Fc` of a known stdout fragment ≥ 1).
- [ ] The verifier never invokes a write tool other than `argos state-append`; verified by absence of `Edit`/`Write` tool calls targeting `argos/specs/STATE.md` in a test session transcript.
- [ ] `.claude/agents/verifier.md` body contains the literal command `argos state-append`.
- [ ] Two concurrent verifier runs (different tickets, different sessions) both successfully append blocks; final STATE.md contains both block `id`s; no block is overwritten.

## Depends on

- ARG1-030 (verifier severity rubric — produces the structured output)
- ARG1-051 (state-append helper — write path)

## Touches

- `.claude/agents/verifier.md` (modify — invoke `argos state-append`)
- `argos/specs/v1.0/agents/verifier.md` (modify — keep in sync)
- `argos/cli/verifier_writeback.py` (or equivalent — formats the block from structured output)
- `argos/cli/tests/test_verifier_writeback.py` (or equivalent)

## Parallelizable with

- ARG1-003 (status)
- ARG1-005 (attend)
- ARG1-011 (orchestrate slash command)
- ARG1-012 (dispatch log writer)
- ARG1-021 (independence detection)
- ARG1-022 (parallel dispatch)
- ARG1-023 (worktree merge)
- ARG1-041 (escalation writer)
- ARG1-052 (merge driver)

## Plan

**Author:** coder (in-loop)
**Created:** 2026-04-30

### Approach

Two pieces of glue between three already-shipped components: the
verifier-output parser (ARG1-030), the state-append helper (ARG1-051), and
the verifier agent prompt (ARG1-030's mirror at `.claude/agents/verifier.md`
plus its v1.0 mirror).

1. **`argos/cli/verifier_writeback.py` (new).** Pure-stdlib Python module.
   Reads a file (or stdin) containing a `<!-- argos:verifier-output -->`
   block, hands it to `argos.cli.verifier_parser` for extraction +
   validation, maps the structured `decision` to a STATE.md phase label
   (`pass → verified`, `pass-with-minors → verified-with-minors`,
   `fail → verification-failed`), formats a STATE.md block body, and calls
   `argos.cli.state_append.append_block` with `author="verifier"` and a
   `--suffix verify` slug. The body always carries a `Findings: N critical,
   N major, N minor` line and a `Decision: <literal>` line; on
   `pass-with-minors` it lists each minor finding's `file:line` reference;
   on `fail` it embeds `--stdout-file` contents verbatim under a
   `Test stdout:` fenced sub-block so AC#3's `grep -Fc` of a known fragment
   matches.

2. **`argos/cli/__main__.py` (modify).** Add `verifier-writeback` to
   `INTERNAL_SUBCOMMANDS`, the help text, the dispatch chain, and the
   docstring's implemented-subcommands list. Single dispatch branch
   delegating to the new module's `main(argv)`. Per the parallel-dispatch
   guidance, this file may merge-conflict with sibling tickets ARG1-020 /
   ARG1-041; resolution is "keep both registrations".

3. **`.claude/agents/verifier.md` + `argos/specs/v1.0/agents/verifier.md`
   (modify).** Add a `## STATE.md write — through the helper, never by hand`
   section directing the verifier to invoke
   `python3 -m argos.cli verifier-writeback ...` (which under the hood
   calls `argos state-append`). The literal command `argos state-append`
   appears 4× in the body, satisfying AC#5. The frontmatter `tools:` line
   stays `Read, Bash, Grep, Glob` — Edit/Write are not in the agent's
   toolbelt, so the agent has no way to write STATE.md except through
   `Bash` invoking the helper. Mirror via `cp` so `diff -q` exits 0.

4. **`argos/cli/tests/test_verifier_writeback.py` (new).** 9 tests across
   two classes. `FormatBodyTests` exercises the body formatter directly
   (pass / pass-with-minors / fail). `WritebackCLITests` runs the wrapper
   end-to-end against a fixture STATE.md, asserting all six ACs.

### Files and changes

- `argos/cli/verifier_writeback.py` — new (~250 lines, stdlib only:
  argparse, datetime, pathlib, sys; `re`/`json` not imported here, the
  underlying `verifier_parser` already provides them).
- `argos/cli/__main__.py` — modify (4-line additions: tuple, help line,
  dispatch branch, docstring).
- `.claude/agents/verifier.md` — modify (insert STATE.md-write section
  before `## Boundaries`; tweak two boundary bullets to reference the
  helper).
- `argos/specs/v1.0/agents/verifier.md` — modify (byte-identical mirror via
  `cp`).
- `argos/cli/tests/test_verifier_writeback.py` — new (9 tests).

### Out of scope (explicitly not changing)

- `argos/cli/state_append.py` and `argos/cli/commands/state_append.py` —
  the ARG1-051 helper is reused unchanged; this ticket does not reinvent
  it.
- `argos/cli/verifier_parser.py` — the ARG1-030 parser is reused
  unchanged.
- `argos/specs/v1.0/STATE.md` — no manual edits; the verifier writes here
  in production via `argos state-append`. Direct edits would violate the
  ticket's hard constraint.
- Sibling ticket domains: `argos/orchestrator/` (ARG1-020) and
  `argos/escalation/` (ARG1-041) — untouched.
- ARG1-013 (auto-fix retry) — not implemented here; the writeback is
  invoked once per verification run, retries are an outer-loop concern.
- ARG1-032 (pre-commit verifier-only-state hook) — separate ticket.

### Verification approach

- AC#1 — pass case: feed a `decision: pass` block; assert `grep -E
  '<!-- argos:entry .* author=verifier .* -->'` matches a tag containing
  `ARG1-031` and the resulting block body contains the literal `verified`.
- AC#2 — pass-with-minors with two minor findings: assert `grep -Fc
  'verified-with-minors'` ≥ 1, both `file:line` references appear, and
  `0 critical, 0 major, 2 minor` is present verbatim.
- AC#3 — fail with one critical finding plus `--stdout-file` containing a
  known fragment: assert `grep -Fc 'verification-failed'` ≥ 1 and
  `grep -Fc '<known-stdout-fragment>'` ≥ 1.
- AC#4 — verifier never invokes a write tool other than `argos
  state-append`. Verified at code level (the wrapper module has no direct
  STATE.md writes — only `append_block` is imported) and at agent level
  (the agent's frontmatter `tools:` line excludes Edit, Write, and
  NotebookEdit).
- AC#5 — `grep -Fc 'argos state-append' .claude/agents/verifier.md` ≥ 1
  (and same for the v1.0 mirror).
- AC#6 — two concurrent `verifier-writeback` invocations on the same
  STATE.md fixture file (different tickets, different sessions): assert
  both block ids appear, all ids globally unique, the resulting file
  parses cleanly.
- All ACs verified through `python3 -c 'import json, sys; ...'` style
  pipes per ADR-002 — no `pyyaml`, no `jq`.

### Risks

- **Body schema drift.** The phase-label mapping (`verified` /
  `verified-with-minors` / `verification-failed`) is added by this ticket;
  it is not pre-pinned in `state-block.md`. The schema doc is permissive
  (the body is preserved verbatim, the parser does not interpret it), so
  this is a writer-side convention, not a schema change. Documented in
  the verifier agent prompt.
- **Sibling merge conflict on `argos/cli/__main__.py`.** Expected per the
  ticket spec; resolution is "keep both registrations".

## Verification

**Verifier:** in-loop (this ticket's coder + harness)
**Run date:** 2026-04-30

### Acceptance Criteria evidence

- **AC#1 (pass → verified block).** Harness fed a `decision: pass` block
  and ran `python3 -m argos.cli verifier-writeback --input pass.txt
  --ticket ARG1-031 --session sess-ac1 --suffix verify --state-file
  $TMP/STATE.md`. Result: 1 match for
  `<!-- argos:entry .* author=verifier .* -->` containing `ARG1-031` and
  literal `verified`. Block id `2026-04-30T16:28:00Z-ARG1-031-verify`.
- **AC#2 (pass-with-minors).** Two minor findings (`src/foo.py:7`,
  `src/bar.py:11`). Result: `grep -Fc 'verified-with-minors'` = 1; both
  file:line refs grep to 1; `grep -Fc '0 critical, 0 major, 2 minor'` =
  1.
- **AC#3 (fail with stdout fragment).** One critical finding plus
  `--stdout-file` containing `AssertionError: expected 0, got None`.
  Result: `grep -Fc 'verification-failed'` = 1; `grep -Fc 'AssertionError:
  expected 0, got None'` = 2 (≥1; the fragment appears once in the
  finding description echo and once in the embedded stdout block).
- **AC#4 (no Edit/Write on STATE.md).** `grep -E '^tools:'
  .claude/agents/verifier.md` returns `tools: Read, Bash, Grep, Glob` —
  no Edit/Write/NotebookEdit. The wrapper module
  `argos/cli/verifier_writeback.py` imports only
  `argos.cli.state_append.append_block` for STATE.md writes — verified by
  test `test_ac4_writeback_uses_only_state_append`.
- **AC#5 (literal `argos state-append`).** `grep -Fc 'argos state-append'
  .claude/agents/verifier.md` = 4. Mirror grep = 4. `diff -q
  .claude/agents/verifier.md argos/specs/v1.0/agents/verifier.md` exits
  0.
- **AC#6 (concurrent appends).** Two `verifier-writeback` processes
  spawned in parallel against the same fixture STATE.md (tickets
  `ARG1-AAA` / `ARG1-BBB`, sessions `sess-a` / `sess-b`). Both exited 0;
  both ticket strings appear; 21 ids parsed, all unique;
  `argos state-parse` round-trip exited 0.

### Tests

`python3 -m unittest argos.cli.tests.test_verifier_writeback -v` →
**9 tests, all OK**. Regression sweep
`test_state_append test_verifier_parser test_frontmatter_parser
test_escalation_validator test_version test_config
test_verifier_writeback` → **98 tests, all OK** (the
ARG1-050-pytest-gated `test_state_parser` skipped in stdlib-only
environments per its module-import gate).

### ADR compliance

- ADR-001 (Python ≥3.9 stdlib-only): wrapper imports
  `argparse`, `json`, `sys`, `pathlib`, `datetime` plus the project's
  own `argos.cli.{state_append, verifier_parser}`; no third-party
  imports. `pyproject.toml` unchanged.
- ADR-002 (stdlib-only AC tooling): all six ACs verified with `grep -F`
  / `grep -E` and `python3 -c 'import json, sys; ...'` pipes; no
  `pyyaml`, no `jq`.

### Decision: pass
