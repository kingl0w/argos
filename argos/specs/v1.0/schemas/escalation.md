---
name: escalation-file-schema
description: Canonical schema for escalation files written by sessions and the orchestrator and drained by `argos attend`.
status: draft
version: 1.0
---

# Escalation file schema

This document is the canonical contract for escalation files. It lifts the inline
schema from `argos/specs/v1.0/ARCHITECTURE.md` (§Components/Escalation Channel)
into a versioned schema document so future changes go through the v1.0 → v1.x →
v2.0 schema-evolution process rather than ad-hoc edits to ARCHITECTURE.md.

Producers (orchestrator, planner, coder, watchdog, verifier — see ARG1-041) and
consumers (`argos attend`, optional webhook — see ARG1-005) must conform to this
schema exactly. The reference validator at `argos/cli/escalation_validator.py`
encodes these rules.

## Frontmatter (required)

Every escalation file begins with a YAML-style frontmatter block delimited by
`---` lines. The reference validator parses flat scalar `key: value` pairs only
(no nested mappings, no lists, no anchors). All five fields below are required.

| Field         | Type   | Allowed values / format                                                                | Example                              |
|---------------|--------|----------------------------------------------------------------------------------------|--------------------------------------|
| `ticket_id`   | string | Non-empty. Convention: `<PREFIX>-<NNN>` matching the ticket file under `argos/specs/tickets/`. | `ARG1-042`                           |
| `session_id`  | string | Non-empty. Convention: `sess-<ISO-8601>-<short-sha>`. (Format set by writer; the schema accepts any non-empty string.) | `sess-2026-04-26T14:33:01Z-a1b2`     |
| `severity`    | enum   | `blocking` \| `advisory`                                                               | `blocking`                           |
| `raised_by`   | enum   | `orchestrator` \| `planner` \| `coder` \| `watchdog` \| `verifier`                     | `orchestrator`                       |
| `created`     | string | ISO-8601 UTC timestamp. Validator accepts anything `datetime.datetime.fromisoformat` parses (Python 3.11+ accepts a trailing `Z`). | `2026-04-26T14:33:01Z`               |

### Severity values

- `blocking` — halts the affected session. The operator must decide before the
  session can proceed.
- `advisory` — noted; the session proceeds with the agent's best guess. The
  operator reviews after the fact via `argos attend`.

### Raised-by values

The five legal authors of an escalation:

- `orchestrator`
- `planner`
- `coder`
- `watchdog`
- `verifier`

Any other value is rejected by the validator.

## Body sections (required)

The body (everything after the closing `---`) must contain all four of the
following H2 headings, each appearing at least once on its own line:

- `## Question` — one-paragraph statement of what the operator must decide.
- `## Context` — what the agent already knows: file paths, line numbers,
  prior decisions consulted.
- `## Options considered` — bullet list of options with their tradeoffs.
- `## Why escalated` — why this is genuine ambiguity, not a default the agent
  should have taken.

The validator enforces presence (`grep -Fc '## Question' <file>` ≥ 1, etc.).
Section ordering is not enforced; producers should emit them in the order above
for readability.

## Filename convention

Escalation files are written to `argos/specs/escalations/` (un-versioned —
runtime state, not spec doc) using the convention:

```
argos/specs/escalations/{ticket-id}-{ISO-timestamp}.md
```

Example: `argos/specs/escalations/ARG1-042-2026-04-26T14-33-01Z.md` (colons in
the timestamp are typically replaced with `-` for filesystem portability; the
canonical `created` value inside the frontmatter retains the colons).

## Worked examples

- Positive (validates): [`examples/escalation-blocking.md`](examples/escalation-blocking.md)
- Negative (deliberately invalid — `severity: critical`):
  [`examples/escalation-malformed.md`](examples/escalation-malformed.md)

## Schema evolution

Changes to this schema are not ad-hoc edits. They go through:

1. An ADR proposing the change, written under `argos/specs/decisions/`.
2. A bump to the `version:` frontmatter field of this file (semver-style:
   additive change → minor; breaking change → major).
3. Coordinated update to `argos/cli/escalation_validator.py` and the example
   files.

Producers and consumers pinned to an older `version:` continue to work against
the older schema document; runtime escalation files do not carry a schema
version (they are ephemeral and must conform to the schema in effect at write
time).
