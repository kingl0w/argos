# ARG-002 — Document self-hosting setup in README

**Status:** Queued
**Created:** 2026-07-01
**Priority:** P2

## Intent

The README explains running Argos on a foreign repo but not the self-hosting arrangement this repo uses (root `argos/specs/` tree plus the versioned `argos/specs/v1.0/` CLI-layer tree, and which STATE.md is live for what). Document it so contributors don't have to reverse-engineer the layout.

## Context

Filed from the v0.5 queue (file backfilled 2026-07-01 so the queue entry resolves). See `argos/cli/spec_paths.py` for the resolution rule the CLI actually applies.

## Non-goals

- Changing the spec-tree layout itself.

## Acceptance criteria

- [ ] README (or a linked doc) explains the two spec trees and which one the CLI resolves.
- [ ] A new contributor can answer "where do I put a new ticket for the CLI layer?" from the docs alone.
