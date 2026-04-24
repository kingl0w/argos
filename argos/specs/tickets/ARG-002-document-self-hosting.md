# ARG-002 — Document self-hosting setup in README

**Status:** Queued
**Created:** 2026-04-24
**Priority:** P2

## Intent

Explain in README why `argos/specs/STATE.md`, `argos/specs/tickets/`, and `argos/specs/decisions/` are committed in the template repo. Answer: Argos self-hosts on itself for dogfooding; these track the Argos project's own development, not a placeholder for fork users.

## Context

Discovered during v0.5 dogfooding: maintainers who fork the template might be confused by the committed `STATE.md` and wonder if they're supposed to keep or delete it. The sentinel-based guard (fixed in commit `d409774`) makes it functionally correct — `argos-init.sh` on a fresh retrofit ignores the committed files and renders templates over them — but the *reason* it works should be documented so the setup doesn't read as an accident.

## Non-goals

- No changes to `argos-init.sh` or the sentinel logic. That guard is correct as of `d409774`.
- No restructure of `argos/specs/` in the template repo. The files stay where they are.
- No new convention for other forks to follow. Self-hosting is an Argos-repo-specific practice, not a pattern we're recommending.

## Acceptance criteria (draft)

- [ ] README gains a section (e.g. "Self-hosting Argos on Argos") that explains why `argos/specs/STATE.md`, rendered tickets, and rendered ADRs exist in the template repo.
- [ ] The section notes that `argos-init.sh` on a fresh retrofit ignores them thanks to the sentinel guard, so fork users do not need to delete anything before running init.
- [ ] The section links to ARG-001 and ARG-002 (this ticket) as examples of what self-hosting captures.
- [ ] No regressions in the existing Quickstart or "Upgrading from v0.4" sections.
