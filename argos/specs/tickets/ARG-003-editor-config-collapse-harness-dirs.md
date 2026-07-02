# ARG-003 — Ship editor config for visual collapse of harness-required directories

**Status:** Queued
**Created:** 2026-07-01
**Priority:** P2

## Intent

The generated harness directories (`.claude/`, `.cursor/`, `.codex/`, `.gemini/`) plus root `CLAUDE.md` / `AGENTS.md` clutter the project root. Ship editor configuration (e.g. VS Code `files.exclude` / explorer file nesting) that visually collapses them without removing them from git.

## Context

Filed from the v0.5 queue (file backfilled 2026-07-01 so the queue entry resolves). The harnesses hardcode these paths at the repo root, so they cannot move — only be hidden.

## Non-goals

- Relocating the harness directories (see ARG-004).

## Acceptance criteria

- [ ] A committed editor config hides or nests the harness directories by default.
- [ ] The config is opt-out and documented in one README line.
