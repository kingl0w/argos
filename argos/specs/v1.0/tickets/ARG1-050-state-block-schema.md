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
