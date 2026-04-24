# ARG-004 — Investigate relocatable config for Cursor / Codex / Gemini

**Status:** Queued
**Created:** 2026-04-24
**Priority:** P2

## Intent
Determine whether any of .cursor/, .codex/, or .gemini/ support relocatable config paths (env var, alt location, or explicit flag). If even one supports it, add an opt-in flag to move it under argos/.

## Context
Follow-up from v0.5 consolidation. Claude Code's .claude/ and CLAUDE.md are definitively hardcoded. The other three harnesses need research — their documentation may have changed since Argos v0.4, or there may be undocumented flags. Any win here reduces root clutter further.

## Out of scope
- Implementing the move (depends on findings)
- Building a wrapper runtime to intercept harness file reads (explicitly rejected in v0.4 design)
- Migrating Claude Code's .claude/ (known hardcoded)

## Acceptance criteria (draft)
- [ ] Research note in argos/specs/decisions/ for each harness: can config dir be relocated?
- [ ] If yes for any harness, file implementation ticket (ARG-NNN)
- [ ] If no for all three, close with an ADR documenting the findings so we don't redo this research in six months
