# ARG-002 — Document self-hosting setup in README

**Status:** Done
**Created:** 2026-07-01
**Priority:** P2
**Closed:** 2026-07-12

## Intent

The README explains running Argos on a foreign repo but not the self-hosting arrangement this repo uses (root `argos/specs/` tree plus the versioned `argos/specs/v1.0/` CLI-layer tree, and which STATE.md is live for what). Document it so contributors don't have to reverse-engineer the layout.

## Context

Filed from the v0.5 queue (file backfilled 2026-07-01 so the queue entry resolves). See `argos/cli/spec_paths.py` for the resolution rule the CLI actually applies.

## Non-goals

- Changing the spec-tree layout itself.

## Acceptance criteria

- [x] README (or a linked doc) explains the two spec trees and which one the CLI resolves.
- [x] A new contributor can answer "where do I put a new ticket for the CLI layer?" from the docs alone.

## Resolution

Closed 2026-07-12 (audit batch, out-of-loop). README gained a "Self-hosting: the two spec trees" section explaining both trees, the `spec_paths.py` probe rule, the new stderr note when the v1.0 tree is auto-selected, and an explicit answer to "where does a new ticket go" for both layers. An "Installing the CLI" subsection (pipx / `pip install -e` / `python3 -m argos.cli`) was added alongside, since the `python3 -m` form only works from inside the clone.
