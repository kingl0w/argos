---
id: ARG1-066
title: Merge-aware independence detection (replace strict criterion)
status: ready
layer: 2
depends_on: [ARG1-021, ARG1-022, ARG1-023, ARG1-013, ARG1-054]
blocks: []
allowed_tools: [Read, Edit, Write, Bash, Grep, Glob]
denied_paths: ["argos/specs/v1.0/PRD.md"]
---

## Context

ARG1-021 shipped strict file-set disjointness as the independence criterion,
per three aligned canonical specs (ARG1-021 §Intent, ARCHITECTURE.md
§Independence detection L106, orchestrator agent doc §Parallel dispatch L89–94).
Implementation lives at `argos/cli/orchestrator/independence.py`.

The strict criterion is correct-but-conservative. Empirical evidence from
Layer 2 bootstrap (escalation ARG1-021-2026-05-02T15-49-14Z) shows real
parallel-safe batches — concretely ARG1-011/012 sharing `argos/cli/__main__.py`,
plus ARG1-020/031/041 — would be falsely serialized. PRD success criterion #4
(≥2× speedup) is harder to hit under strict.

Operator decision ESC-ARG1-021 ratified Option B (merge-aware) as the eventual
direction, **explicitly via dynamic dry-run merge** rather than static
`.gitattributes` inspection. The escalation correctly noted that reading
`.gitattributes` alone does not capture `__main__.py` (which uses the default
`text` driver and merges cleanly only because of the human-chosen registration
pattern). The dry-run mechanism subsumes both the merge-driver case (STATE.md)
and the registration-pattern case (`__main__.py`) by exercising the actual
merge configuration rather than predicting from static metadata.

Three known shared-file patterns this ticket must handle:

1. `argos/cli/__main__.py` — registration-style edits, `ort` resolves cleanly
   via keep-both pattern at distinct line ranges. Default `text` driver.
2. `argos/specs/v1.0/STATE.md` — handled by the ARG1-052 custom merge driver
   (`argos/scripts/state-merge-driver.sh`) via `.gitattributes`. The dry-run
   must exercise the configured driver, not bypass it.
3. `.claude/agents/<name>.md` ↔ `argos/specs/v1.0/agents/<name>.md` mirror
   pair — no concurrent edits to date but structurally similar to #1.

This ticket is **queued**. Promote to `ready` after ARG1-054 lands on main,
before Layer 3 dogfood validation begins.

## Goal

Replace ARG1-021's strict file-overlap check with a dynamic merge-dryrun check.
Two ticket branches are independent iff `git merge --no-commit --no-ff` of one
onto the other (in both directions, in a clean staging area) produces no
conflicts and exits cleanly.

The detector continues to honor the existing `depends_on:` exclusion —
explicitly declared dependencies are still dependent regardless of merge
outcome. `depends_on` is checked first; the dry-run is the second-pass check.

## Acceptance criteria

AC#1 — `argos independence` retains its existing CLI surface (positional
       ticket arguments, `--json` flag, exit codes). The calling pattern from
       ARG1-022 must continue to work without change.

AC#2 — Detection mechanism: for each candidate pair (after `depends_on:`
       exclusion), the detector creates a temporary worktree, attempts
       `git merge --no-commit --no-ff <branch-b>` from `<branch-a>`, records
       the outcome, aborts the merge, attempts the reverse direction,
       records, aborts. The pair is independent iff both directions succeed
       without conflicts. Cleanup of the temporary worktree is guaranteed
       even on crash (atexit + signal handlers).

AC#3 — Performance: pairwise check completes in <2s wall-clock on a
       reference machine for typical Layer-2-shaped tickets (3–10 file
       changes per branch). Worst-case batch decision (10 pending tickets,
       45 pairwise checks) completes in <60s.

AC#4 — Merge driver compatibility: a synthetic test fixture creates two
       branches that both append distinct entries to `argos/specs/v1.0/STATE.md`,
       configures the project's state-merge-driver, runs the detector, and
       confirms the pair is reported as independent. The dry-run must exercise
       the configured driver, not a default merge strategy.

AC#5 — Hook interaction: a synthetic test fixture confirms the detector's
       internal `git merge` invocations do NOT trigger the ARG1-032 pre-commit
       hook. The dry-run must reach a clean test outcome without firing
       commit-time hooks. Implementation choice (—no-verify, hook-disable
       env var, or staying pre-commit) is the planner's, but must be
       documented in the Plan section.

AC#6 — Registration-pattern coverage: a synthetic test fixture creates two
       branches that both add distinct entries to a `__main__.py`-style file
       (additions at distinct line ranges within the same logical region) and
       confirms the detector reports the pair as independent. This is the
       primary case the strict criterion got wrong.

AC#7 — depends_on precedence: a pair where ticket B's `depends_on:` includes
       ticket A is reported as dependent without running the merge dry-run.
       depends_on is the cheap first-pass check.

AC#8 — Rollback discipline: after a successful run, `git status` in the
       parent worktree is byte-equivalent to its pre-run state. No leaked
       temporary worktrees. A test fixture asserts this.

AC#9 — Documentation amendment: ARCHITECTURE.md §Independence detection
       (L104–109 region) and `argos/specs/v1.0/agents/orchestrator.md`
       §Parallel dispatch (L89–94 region) updated to describe the
       merge-dryrun mechanism. The strict criterion description is replaced,
       not appended — this is a semantics replacement.

AC#10 — ARG1-021 ticket file annotated with a `## Superseded by ARG1-066`
        section pointing to this ticket's commit. Follows the supersession
        pattern from ARG1-056→058 and ARG1-060→062.

AC#11 — Test count: existing 28 tests for ARG1-021 are migrated/replaced as
        appropriate (the strict criterion tests become merge-dryrun tests
        with the same intent). New tests cover merge-driver compatibility
        (AC#4), hook interaction (AC#5), registration-pattern coverage (AC#6),
        and rollback discipline (AC#8). Total test count for the
        independence module ≥35.

AC#12 — Full sweep clean: `python3 -m unittest discover -s argos/cli/tests`
        exits 0.

## Non-goals

- Not a merge driver change. The ARG1-052 driver is consumed by this detector,
  not modified.
- Not an orchestrator behavior change. ARG1-022's dispatch logic continues
  to consume `argos independence`'s output unchanged; only the implementation
  behind that surface changes.
- Not an allowlist (Option A from ESC-ARG1-021). Explicitly rejected.
- Not `.gitattributes`-only inspection (escalation's Option B framing).
  Explicitly superseded by dry-run merge.
- Not a CI integration. Detector runs locally as part of orchestrator
  decision-making.
- Not an ADR. The decision lives in ESC-ARG1-021; promoting to an ADR is
  a separate operator call if future contributor onboarding warrants it.

## State on completion

Append via `python3 -m argos.cli state-append --suffix done`.
