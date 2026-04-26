<!-- intentionally invalid: see ARG1-040 -->
---
ticket_id: ARG1-042
session_id: sess-2026-04-26T14:33:01Z-a1b2
severity: critical
raised_by: orchestrator
created: 2026-04-26T14:33:01Z
---

## Question

Same shape as `escalation-blocking.md`, but with a deliberately wrong
`severity` value. The validator must reject this file and name the
`severity` field in stderr.

## Context

- `severity: critical` is not in the allowed enum `{blocking, advisory}`.
- `critical` is a verifier-finding tier (see ARCHITECTURE.md §Severity-Tiered
  Verifier), not an escalation severity. Conflating the two is the realistic
  confusion this fixture exists to catch.
- All four required body sections are still present so the failure is
  unambiguously attributable to the frontmatter `severity` field.

## Options considered

- A: Pretend `critical` is the same as `blocking`. Rejected — the schema is
  the contract; downstream consumers (`argos attend`, webhook payloads) read
  the enum literally.
- B: Add `critical` to the allowed-severity enum. Rejected — that is a
  schema-evolution decision, not a parse-time forgiveness.

## Why escalated

This file is never escalated; it is a negative fixture. The accompanying
test `test_malformed_example_fails_with_severity_error` asserts the validator
rejects it.
