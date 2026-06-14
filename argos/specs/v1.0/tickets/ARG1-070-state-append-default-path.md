---
id: ARG1-070
title: Reconcile argos state-append default path with active self-hosted STATE.md
status: ready
layer: followup
depends_on: []
---

## Context

`argos state-append` defaults its target to `argos/specs/v1.0/STATE.md`, but the
active self-hosted STATE.md is `argos/specs/STATE.md`. During the Layer 3
autonomous run (ARG1-003), the session had to pass `--state-file` explicitly to
write to the right file. Surfaced by the ARG1-003 verifier as a flagged
follow-up, not fixed in-ticket.

The mismatch is a foot-gun: a session that forgets `--state-file` writes its
block to the wrong (v1.0) STATE.md, splitting state across two files silently.

## Goal

Make the default target correct for this repo's layout, OR make the default
resolve dynamically (e.g. prefer `argos/specs/STATE.md` when it exists, fall
back to the v1.0 path). Decide which is canonical as part of the broader
v0.5/v1.0 STATE.md split reconciliation.

## Acceptance criteria

- [ ] `argos state-append` with no `--state-file` writes to the same STATE.md
      that `argos status` and the merge driver treat as canonical.
- [ ] The choice (fixed default vs dynamic resolution) is documented in the
      state-append command help and/or the STATE.md schema doc.
- [ ] Existing tests that pass `--state-file` explicitly still pass.
- [ ] Full sweep green; lint-imports clean.

## Notes

Related to the unfiled v0.5/v1.0 reconciliation debt (two STATE.md files, two
ADR path conventions). May be folded into ARG1-055 (state-migrate-v05) if that
ticket subsumes the split decision.
