---
name: verifier-output-schema
description: Structured output block emitted by the v1.0 verifier — findings classified by severity tier, plus a single decision literal
status: draft
version: 1.0
---

# Verifier Output Schema (v1.0)

## Intent

The v1.0 verifier replaces v0.5's free-form `Status: READY | NEEDS_FIXES | BLOCKED` with a machine-parseable block that downstream consumers (orchestrator, STATE-writer, escalation router) can read without parsing prose. Tiers and behavior are defined in `argos/specs/v1.0/ARCHITECTURE.md` §Components/Severity-Tiered Verifier; this document is the wire-format contract for the block itself. The agent prompt at `.claude/agents/verifier.md` (and its canonical mirror at `argos/specs/v1.0/agents/verifier.md`) tells the verifier *when* to emit each tier; this document tells consumers *how to read* what the verifier emits.

## Location

The block is appended inside the verifier's `## Verification` section in the ticket file. It is delimited by HTML comment markers so that markdown rendering does not break the block, and so that consumers can locate the block by string search rather than by parsing markdown:

```
<!-- argos:verifier-output -->
…block contents…
<!-- /argos:verifier-output -->
```

Exactly one such block per verification run. If a ticket is verified more than once (e.g., after an auto-fix retry per ARG1-013), each verification appends its own block; consumers parse the last one as authoritative.

## Grammar

The block body is a tiny YAML-ish dialect — deliberately small so a stdlib-only parser can read it without pulling in `pyyaml`. The grammar is:

```
block         := "tests_ran:" BOOL NL "findings:" NL FINDINGS "decision:" DECISION NL
BOOL          := "true" | "false"
FINDINGS      := "[]" NL                 # empty list
               | (FINDING_ITEM)+         # one or more list items
FINDING_ITEM  := "  - severity:" SEVERITY NL
                 "    description:" QUOTED_STRING NL
                 ("    file:" PATH_OR_PATH_COLON_LINE NL)?
SEVERITY      := "critical" | "major" | "minor"
DECISION      := "pass" | "pass-with-minors" | "fail"
```

### Field rules

- `tests_ran:` — required, exactly `true` or `false`. If `false`, `decision:` MUST be `fail`. Consumers reject the block if this rule is violated.
- `findings:` — required. Either the literal `[]` (empty list) or one-or-more list items. Each item has:
  - `severity:` — required, exactly one of `critical`, `major`, `minor`.
  - `description:` — required, non-empty string. Quoted with double quotes if it contains a colon, comma, or newline; bare otherwise. For any `severity: critical` finding involving a test failure, the description MUST quote real test stdout (rule enforced by the agent prompt; consumers do not re-validate the stdout).
  - `file:` — optional, `path` or `path:line`. Omit for whole-suite findings (e.g., test command did not run).
- `decision:` — required, exactly one of three literals:
  - `pass` — the run had zero findings of any tier and tests ran cleanly. Every acceptance criterion has concrete evidence.
  - `pass-with-minors` — zero critical, zero major, ≥1 minor. Merge is allowed; minors surface on `argos attend`.
  - `fail` — ≥1 critical, or ≥1 major, or `tests_ran: false`. Triggers the auto-fix retry (cap 1) per ARG1-013 once that lands.

### Consistency invariants (validated by `argos verifier-parse`)

- `decision: pass` requires `findings: []` AND `tests_ran: true`.
- `decision: pass-with-minors` requires every finding's `severity` to be `minor` AND `tests_ran: true`.
- `decision: fail` is valid for any combination of findings, and is required whenever `tests_ran: false`.
- A `decision:` value outside the three literals is a schema violation. The parser exits with code 2.

## Worked example

The block below is the canonical example. The reference parser test extracts it from this document by the example markers and round-trips it through the parser.

<!-- argos:verifier-output:example -->
<!-- argos:verifier-output -->
tests_ran: true
findings:
  - severity: critical
    description: "tests/test_foo.py::test_empty failed: AssertionError: expected 0, got None"
    file: src/foo.ts:42
  - severity: major
    description: "Acceptance criterion 3 partially met: parser handles example A but not example B"
  - severity: minor
    description: "Unused import 'os' inside changed region"
    file: src/foo.ts:1
decision: fail
<!-- /argos:verifier-output -->
<!-- /argos:verifier-output:example -->

A `pass` example, for reference (not used by the parser test):

```
<!-- argos:verifier-output -->
tests_ran: true
findings: []
decision: pass
<!-- /argos:verifier-output -->
```

## Reference parser

The parser at `argos/cli/verifier_parser.py` reads a file containing one such block, validates it against this grammar, and emits JSON `{tests_ran, findings, decision}` on stdout. Exit codes:

- `0` — block parsed and valid.
- `1` — file not found or unreadable.
- `2` — schema violation (missing required key, invalid `decision` literal, invalid `severity`, `decision` inconsistent with `findings` or `tests_ran`).

Invocation (until ARG1-001 ships the real CLI binary):

```
PATH="$PWD/argos/cli:$PATH" argos verifier-parse path/to/example.txt
# or, equivalently:
python3 -m argos.cli.verifier_parser path/to/example.txt
```
