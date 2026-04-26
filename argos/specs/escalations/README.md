# `argos/specs/escalations/`

This directory holds **runtime escalation files** written by the orchestrator
and per-ticket sessions, and drained by the operator via `argos attend` (see
ARCHITECTURE.md §Components/Escalation Channel). Files appear here when an
agent encounters genuine ambiguity that requires an operator decision; files
disappear here once `argos attend` records the decision in the originating
ticket's Decisions section.

The on-disk file format is documented at
[`argos/specs/v1.0/schemas/escalation.md`](../v1.0/schemas/escalation.md).
Filenames follow the convention
`argos/specs/escalations/{ticket-id}-{ISO-timestamp}.md`. The reference
validator at `argos/cli/escalation_validator.py` is the canonical parser; new
producers must validate their output against it before writing.

This directory is **not** version-prefixed. Schemas live under
`argos/specs/v1.0/schemas/` (versioned — they evolve through the v1.0 → v1.x
→ v2.0 process). Runtime escalation instances live here, un-versioned,
because they are ephemeral state generated against whichever schema version
is current at write time. Producers (ARG1-041) and consumers (ARG1-005, plus
the optional webhook in ARG1-041) are tracked as separate tickets; this
directory exists ahead of both so the schema contract can be committed and
validated in isolation.

The `escalation-validate` shim at `argos/cli/escalation-validate` is
provisional — the unified `argos` CLI dispatcher (ARG1-001) will absorb it
into an `argos escalation-validate <path>` subcommand and remove the shim.
