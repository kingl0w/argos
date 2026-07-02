# ARG-005 — Scan-report generator for retrofit onto existing codebases

**Status:** Queued
**Created:** 2026-07-01
**Priority:** P2

## Intent

`argos init` scaffolds empty specs. For an existing codebase, a scan step that drafts a starting `ARCHITECTURE.md` / `conventions.md` (detected language, test command, dependency policy) would make retrofitting far cheaper than writing them from scratch.

## Context

Filed from the v0.5 queue (file backfilled 2026-07-01 so the queue entry resolves). Output should be a human-reviewable draft, never silently committed — the operator ratifies the scan the way they ratify a merge.

## Non-goals

- Auto-committing generated specs.
- Deep static analysis; heuristics (manifest files, CI config) are enough for a draft.

## Acceptance criteria

- [ ] Running the scan on a non-Argos repo produces draft spec files marked as drafts.
- [ ] The scan degrades gracefully (partial draft, explicit TODOs) when detection fails.
