# Argos — Target conventions

These are **Argos's own** language, dependency, and test conventions. Argos reads
this file from the repo under work and injects it verbatim into every dispatched
session's prompt, ahead of the Argos-contract rules. When Argos dogfoods on
itself, this is the file that binds its sessions.

Previously these two rules were hardcoded in `session_prompt.STANDING_RULES`
(rules 1 and 2). They now live here so that target-convention rules are sourced
from the target repo rather than baked into the orchestrator. Consumers that
need argos's stdlib-only contract reference this file.

## Language

- Implementation is Python >=3.9, standard library only (ADR-001). Do not add
  any third-party runtime dependency; that is an ADR-level decision, not the
  coder's to make.

## Tests / acceptance criteria

- Acceptance-criteria tooling is standard library only as well (ADR-002). Every
  AC command must run under a fresh python3 >=3.9 with no `pip install` step.
