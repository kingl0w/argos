# ARG1-061 — `argos state-append --suffix` for entry id disambiguation

**Status:** Queued
**Created:** 2026-04-29
**Priority:** P2
**Epic:** 6 (STATE.md migration + config split) — extends ARG1-051

## Intent

Add an optional `--suffix <slug>` flag to `argos state-append`. When set, the helper appends `-{suffix}` to the auto-generated entry id, after the ticket-id segment and before any collision-retry hex. Format becomes `{ISO-timestamp}-{ticket-id}-{suffix}[-{collision-hex}]`. Restores the disambiguation expressiveness used by the legacy `ARG1-052-drift` entry, which the helper-based ARG1-010 drift entry (`c5c0c20`) could not match because the helper had no suffix slot.

## Context

ARG1-051 introduced `argos state-append` with auto-generated ids `{ISO-timestamp}-{ticket-id}`, plus a 6-hex random suffix only on same-second collisions. The legacy ARG1-052-drift entry (predating the helper) used a manual `-drift` id suffix to distinguish the known-limitation entry from the verified entry on the same ticket. That convention was lost when the c5c0c20 ARG1-010 drift entry was appended via the helper. Drift entries are still findable by section heading (`## Known drift`) and body content, but tools that filter blocks by id pattern alone lose a layer of expressiveness.

## Non-goals

- No retroactive renaming of c5c0c20's ARG1-010 entry id.
- No changes to the existing entry-id grammar beyond adding the suffix slot.
- No changes to non-suffix call sites — existing flagless invocations must produce identical ids byte-for-byte.
- No changes to the parser (`argos/cli/state_parser.py`); the parser already accepts arbitrary id strings via `(\w+)=(\S+)` capture.
- No changes to the merge driver; entries with suffix-extended ids merge identically to non-suffix entries.

## Acceptance criteria

- [ ] `python3 -m argos.cli state-append --section "Known drift" --ticket ARG1-099 --author coder --session sess-test --body-file <body> --state-file <state> --suffix drift --dry-run` exits 0; stdout block's open tag has `id=` value matching `^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]+Z-ARG1-099-drift$`.
- [ ] `--suffix bad space` exits non-zero; stderr contains `invalid suffix` and the offending value.
- [ ] `--suffix BAD` (uppercase) exits non-zero; stderr contains `invalid suffix`.
- [ ] `--suffix ""` exits non-zero; stderr contains `invalid suffix`.
- [ ] `--suffix "valid-slug-123"` exits 0; id ends in `-valid-slug-123`.
- [ ] Collision behavior: when an existing block has id `{ts}-{ticket}-{suffix}` and a second append at the same frozen timestamp uses the same `--suffix`, the second id matches `^{ts}-{ticket}-{suffix}-[0-9a-f]{6}$`.
- [ ] Regression: invocations without `--suffix` produce ids matching `^{ts}-{ticket}$` (no trailing dash, no empty suffix slot). The existing test `test_basic_append_creates_block_with_attrs` passes unmodified.
- [ ] Schema doc `argos/specs/v1.0/schemas/state-block.md` is updated to document the optional disambiguation-suffix slot and the collision-retry hex slot in the id grammar.
- [ ] `python3 -m unittest argos.cli.tests.test_state_append -v` passes including the new suffix tests; existing tests continue to pass with no changes to their assertions.

## Depends on

- ARG1-051 (`argos state-append` helper) — extends its surface.

## Touches

- `argos/cli/state_append.py` (modify — add `suffix` kwarg to `generate_id` and `append_block`, validation regex, `InvalidSuffixError`)
- `argos/cli/commands/state_append.py` (modify — `--suffix` argparse flag, error mapping)
- `argos/specs/v1.0/schemas/state-block.md` (modify — id grammar table row, plus a one-paragraph note on the optional suffix slot)
- `argos/cli/tests/test_state_append.py` (modify — append a `StateAppendSuffixTests` class)

## Parallelizable with

- All Layer 2 tickets (ARG1-020 / ARG1-031 / ARG1-041) — strictly additive surface; existing call sites untouched.
- ARG1-059 / ARG1-060 — different module surfaces.

## Out of scope

- Retro-renaming the c5c0c20 ARG1-010 drift entry (would require an out-of-band STATE.md edit, which the append-only invariant forbids).
- A `--suffix` mode that *replaces* the timestamp (always after ticket-id, never before).
- Renaming the existing 6-hex collision suffix or making its alphabet configurable.
- Documenting the helper's behavior in ADR form. The schema doc update covers the contract; an ADR is not warranted for a strictly additive optional flag.
