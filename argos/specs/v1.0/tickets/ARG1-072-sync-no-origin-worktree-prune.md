---
id: ARG1-072
title: argos sync worktree-prune treats merged worktrees as prunable when no origin exists
status: ready
layer: followup
depends_on: [ARG1-004]
---

## Context

`reconcile_worktrees` (ARG1-004's `argos sync`) prunes a worktree when its
branch is merged into main AND deleted from origin. In a repo with no `origin`
remote, there is no upstream that can "hold" a branch, so the
deleted-from-origin condition is vacuously true and a merged worktree is treated
as prunable. ARG1-004's session documented this as a deliberate, flagged choice
rather than escalating.

The risk: in a local-only repo, a merged-but-still-wanted worktree could be
pruned more eagerly than the operator expects.

## Goal

Decide whether the no-origin case should prune (current behavior) or require an
explicit "origin must exist" gate before pruning. Make the chosen behavior
explicit and documented rather than emergent.

## Acceptance criteria

- [ ] The no-origin pruning behavior is either gated (requires origin) or
      explicitly documented as intended, per the decision.
- [ ] A test covers the no-origin case asserting the chosen behavior.
- [ ] `argos sync --dry-run` in a no-origin repo reports the worktree phase
      result clearly (prunable vs skipped-no-origin).
- [ ] Full sweep green; lint-imports clean.

## Notes

Low severity — flagged by ARG1-004's verifier as a documented edge case, not a
bug. File-and-forget unless local-only repos become a common dogfood target.
