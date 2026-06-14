# ARG1-078 — queue edits trip the append-only STATE.md hook

## Intent

The pre-commit STATE.md hook permits only `<!-- argos:entry … -->` blocks as
added lines. But the `## Queue` and `## In progress` sections hold plain bullets
(`- TICKET-ID`). So EVERY queue edit — adding or removing a ticket — is rejected
as "modified outside append-block" and requires `ARGOS_CYCLE_CLOSE=1`. This is
the last bypass in the otherwise-generic init→queue→orchestrate flow.

## Context

Found in the ARGO-001 clean-room proof. Initially suspected the scaffolded queue
PLACEHOLDER bullet (`- _none yet…_`) was the cause (deleting it tripped the
deletion guard). Removing the placeholder did NOT fix it: a plain `- TEST-001`
ADDITION is still rejected, because the hook's awk validator only accepts
entry-block additions anywhere in STATE.md. The hook and the queue's plain-bullet
format are in direct contradiction.

## Design question (decide before patching)

1. Is `ARGOS_CYCLE_CLOSE=1` (or a dedicated `argos queue add <id>` command) the
   SANCTIONED write path for the queue, making hand-editing simply unsupported?
   If so the fix is UX (build the command), not hook logic.
2. OR should the hook exempt `## Queue` and `## In progress` from entry-block-only
   validation, restricting strict append-only to `## Done this cycle` (the section
   that actually holds entry blocks)?

## Acceptance criteria

- [ ] Decision recorded (command-based vs hook-section-scoping).
- [ ] After the fix, a first queue add commits with NO bypass on a freshly
      init-ed repo (the clean-room test that currently fails).
- [ ] `## Done this cycle` append-only enforcement is unchanged (regression).

## Touches

- argos/scripts/hooks/pre-commit-state-write.sh (if section-scoping)
- or a new argos/cli/commands/queue.py (if command-based)

## Depends on

- (none; adjacent to ARG1-073, same hook file)
