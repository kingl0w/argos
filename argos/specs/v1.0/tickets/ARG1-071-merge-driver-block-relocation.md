---
id: ARG1-071
title: Merge driver relocates STATE.md blocks, tripping the append-only pre-commit hook
status: ready
layer: followup
depends_on: []
---

## Context

During the Layer 3 merges (ARG1-005, ARG1-004), merging two branches that both
appended to STATE.md produced a reconciliation where an existing entry block was
*relocated* (deleted from one section, re-added in another) rather than purely
appended. The ARG1-032 pre-commit hook reads the deletion-half of the move as
"modified outside append-block" and rejects the commit. Each merge required the
`ARGOS_CYCLE_CLOSE=1` bypass.

The content is not lost — it's a move, not a deletion — so the bypass is safe.
But "every STATE.md merge needs a manual bypass" is friction that undercuts the
append-only guarantee the hook is supposed to enforce automatically.

## Goal

Make merge-driven STATE.md reconciliation not trip the hook, OR make the hook
recognize a merge-commit context and allow driver-authored relocations. Two
candidate approaches:
1. Hook detects MERGE_HEAD (in-progress merge) and relaxes the
   modified-outside-append check to "no block content changed" (move OK,
   edit not OK).
2. Merge driver preserves block position (append-only at the destination
   section) so no relocation occurs.

## Acceptance criteria

- [ ] A merge of two branches that each appended a STATE.md entry commits
      WITHOUT the `ARGOS_CYCLE_CLOSE=1` bypass.
- [ ] A genuine append-only violation (block *body* edited) during a merge is
      still rejected by the hook.
- [ ] The chosen approach is documented (hook comment or merge-driver doc).
- [ ] Full sweep green; the ARG1-032 hook test suite still passes.

## Notes

Surfaced repeatedly during the Layer 3 dogfood — this is a real
driver/hook interaction, not a one-off.
