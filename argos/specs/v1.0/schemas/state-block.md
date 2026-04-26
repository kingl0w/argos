---
name: argos-v1.0-state-block-schema
description: Canonical schema for the append-mostly STATE.md block format used by argos v1.0
status: draft
version: 1.0
---

# STATE.md block schema (v1.0)

**Created:** 2026-04-26
**Owner:** verifier (sole writer of STATE.md per ARCHITECTURE.md §Invariants)

This document is the canonical schema for the timestamped, append-mostly blocks that fill the body of `argos/specs/STATE.md` under v1.0. It lifts the inline schema from `ARCHITECTURE.md` §Contracts/STATE.md format into a versioned, parser-targetable contract. Every other v1.0 component that reads or writes STATE.md (the reference parser, the `argos state-append` write helper, the merge driver, the pre-commit hook, `argos status`) consumes this schema.

## Required block-comment attributes

Every block opens with an HTML comment of the form:

```
<!-- argos:entry id=... ticket=... author=... session=... -->
```

All four attributes are required. The parser raises `MissingAttributeError` if any is absent and `MalformedOpenTagError` if attribute syntax is unparseable.

| Attribute | Format | Example | Validation rule |
|-----------|--------|---------|-----------------|
| `id`      | `{ISO-8601-UTC-timestamp}-{ticket-id}` | `2026-04-26T14:33:01Z-ARG-042` | Globally unique within a single STATE.md file. Duplicates raise `DuplicateIdError`. |
| `ticket`  | Ticket ID matching `[A-Z][A-Z0-9]*-\d+` (e.g. `ARG-042`, `ARG1-050`) | `ARG-042` | Must be present; parser does not cross-check that the ticket file exists (out of scope). |
| `author`  | One of `planner`, `coder`, `watchdog`, `verifier`, `orchestrator` | `verifier` | Parser does not enforce the enum at schema level (would couple parser to agent roster); writers should restrict themselves to the listed values. |
| `session` | Opaque session identifier string (no whitespace) | `sess-a1b2` | Must be present and non-empty. Parser treats the value as opaque. |

Attributes appear in any order on the open tag. Values are whitespace-delimited and may not themselves contain whitespace (the parser uses a `(\w+)=(\S+)` capture).

## Block delimiters

- **Open tag:** `<!-- argos:entry id=... ticket=... author=... session=... -->` on its own line.
- **Close tag:** `<!-- /argos:entry -->` on its own line.
- A block extends from its open tag (exclusive) to its close tag (exclusive). Body lines between the delimiters are preserved verbatim by the parser.
- Nested blocks are not permitted. An open tag encountered while a block is already open is treated as a malformation (the parser will continue accumulating body until it sees the next close tag, which will then close the *outer* block — this is documented for diagnosis but writers must not produce nested blocks).
- A close tag with no matching open tag is silently ignored by the parser (it is not within a block, so it does not delimit one).

## Body line conventions

Body lines are markdown. The canonical first body line is a bullet matching the example in `ARCHITECTURE.md` §Contracts:

```markdown
- **[ISO-timestamp] TICKET-ID — phase** (session SESSION, worktree `.argos/worktrees/...`)
  - Files changed: `path/one`, `path/two`
  - Findings: N critical, N major, N minor (...)
  - Decision: pass | pass-with-minors | fail
```

Nested bullets typically list files changed, findings, and decision. The parser does **not** interpret body content — it preserves it verbatim under each block's `body` field. Downstream consumers may parse the body for findings and decisions; the schema does not constrain that secondary interpretation.

## Append-only invariant

> entries are append-only; never edit an existing entry; corrections are new entries that reference the prior `id`.

This statement is canonical (see `ARCHITECTURE.md` §Invariants — "STATE.md is append-mostly. No edits to existing blocks. Removal only at cycle close, only by the operator, only via `argos sync --close-cycle`."). The parser does not enforce it (it has no history); enforcement lives in the pre-commit hook and the merge driver. This schema document records the invariant so writers do not silently violate it.

## Section ordering

Blocks live inside the conventional STATE.md sections (`## In progress`, `## Done this cycle`, `## Known drift`). The parser does **not** enforce section membership — it scans top-to-bottom and returns blocks in source order, regardless of which `## ` heading encloses them. Section-aware grouping is a separate helper (out of scope for this schema; see ARG1-051 / ARG1-052).

This is deliberate: blocks within a section are unordered for parsing purposes (writers append in time order, but readers should not depend on order beyond "this is a list of entries"). The merge-driver concatenation rule (`ARCHITECTURE.md` §Contracts) preserves both blocks on conflict in either order — the schema must tolerate that.

## Examples

The four reference fixtures live alongside this document:

- `examples/state-valid.md` — one well-formed block under `## Done this cycle`.
- `examples/state-unclosed-block.md` — open tag with no matching close (parser raises `UnclosedEntryError`).
- `examples/state-duplicate-id.md` — two complete blocks sharing the same `id` value (parser raises `DuplicateIdError`).
- `examples/state-missing-attr.md` — open tag missing the `session=` attribute (parser raises `MissingAttributeError`).

The canonical valid block, copied here for ease of reference (mirrors `ARCHITECTURE.md` §Contracts):

```markdown
<!-- argos:entry id=2026-04-26T14:33:01Z-ARG-042 ticket=ARG-042 author=verifier session=sess-a1b2 -->
- **[2026-04-26T14:33:01Z] ARG-042 — verified** (session sess-a1b2, worktree `.argos/worktrees/ARG-042-3f9c/`)
  - Files changed: `src/foo.ts`, `src/foo.test.ts`
  - Findings: 0 critical, 0 major, 1 minor (`src/foo.ts:42` unused import in changed region)
  - Decision: pass-with-minors
<!-- /argos:entry -->
```

## Parser failure modes

The reference parser (`argos/cli/state_parser.py`) detects exactly four malformations. Each maps to a typed exception and a stderr substring contract that downstream tooling and tests rely on:

| Failure mode | Exception class | stderr substring contract |
|--------------|-----------------|---------------------------|
| Open tag with no matching close before EOF | `UnclosedEntryError` | contains `unclosed entry` and a `line N:` prefix pointing at the open-tag line |
| Two blocks share the same `id` value | `DuplicateIdError` | contains `duplicate id` and the offending `id` value verbatim |
| Open tag is missing one of `id`, `ticket`, `author`, `session` | `MissingAttributeError` | contains the missing attribute name and a `line N:` prefix pointing at the open-tag line |
| Open tag's attribute syntax cannot be parsed | `MalformedOpenTagError` | contains `malformed open tag` and a `line N:` prefix |

All four exceptions inherit from `StateBlockError`. The CLI shim (`argos/cli/commands/state_parse.py`) catches `StateBlockError`, writes the message to stderr, and exits with code 1.
