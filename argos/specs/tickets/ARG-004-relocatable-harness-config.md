# ARG-004 — Investigate relocatable config for Cursor / Codex / Gemini

**Status:** Queued
**Created:** 2026-07-01
**Priority:** P2

## Intent

Determine whether Cursor, Codex CLI, and Gemini CLI support loading their agent/command definitions from a non-root path, which would let Argos consolidate the generated outputs under `argos/` instead of four root-level dotdirs.

## Context

Filed from the v0.5 queue (file backfilled 2026-07-01 so the queue entry resolves). This is a spike: the deliverable is a findings note (per harness: relocatable yes/no, mechanism, version constraints), not code.

## Non-goals

- Implementing the relocation (follow-up ticket if the spike says it's possible).

## Acceptance criteria

- [ ] A findings section in this ticket covers all three harnesses with sources.
- [ ] A go/no-go recommendation is recorded.
