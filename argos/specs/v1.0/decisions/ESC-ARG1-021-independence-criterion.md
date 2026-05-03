# ESC-ARG1-021: Independence criterion direction

**Status:** Ratified
**Date:** 2026-05-02
**Drains escalation:** argos/specs/escalations/ARG1-021-2026-05-02T15-49-14Z.md
**Files ARG1-066:** yes (queued behind Layer 2)

## Question

ARG1-021's independence detector ships with strict file-set disjointness
(plus `depends_on:` exclusion), per three aligned canonical specs:
ARG1-021 §Intent, ARCHITECTURE.md §Independence detection L106, and
`argos/specs/v1.0/agents/orchestrator.md` §Parallel dispatch L89–94.

The escalation laid out empirical evidence that the strict criterion
falsely serializes real parallel-safe batches — concretely the ARG1-011/
ARG1-012 batch sharing `argos/cli/__main__.py` (STATE.md ids
`2026-04-30T17:42:38Z-ARG1-011-done` and `2026-04-30T17:40:38Z-ARG1-012-done`),
plus the ARG1-020/031/041 three-way batch and others, all of which
auto-merged under `ort` with the keep-both-registrations pattern. PRD
success criterion #4 (≥2× speedup) is harder to hit under strict.

The escalation laid out two relaxation options:
- Option A: hard-coded carve-out allowlist of known-safe shared files
- Option B (as escalation framed it): merge-strategy-aware via reading
  `.gitattributes` for custom merge drivers

## Decision

Option B is ratified as the eventual direction, **with the mechanism
generalized from `.gitattributes` inspection to dynamic dry-run merge.**
Shipped via a follow-up ticket (ARG1-066), queued behind the remaining
Layer 2 chain. ARG1-021 stays strict on main.

## Clarification on Option B mechanism

The escalation's Option B section noted (correctly) that reading
`.gitattributes` alone does not capture `argos/cli/__main__.py` — that
file uses the default `text` merge driver, and its clean concurrent
merges depend on the human-chosen registration pattern (additions at
distinct line ranges), not on any property git knows about. Static
prediction of clean merge from `files_touched:` lists alone requires a
line-range heuristic the planner doesn't currently surface.

ARG1-066 therefore implements Option B's *intent* (the criterion
corresponds to actual merge behavior, not a static heuristic) via a
**dynamic mechanism**: dry-run `git merge --no-commit --no-ff` of one
branch onto the other (in both directions, in a clean staging area)
and treat the pair as independent iff both directions succeed without
conflicts. This generalizes correctly to:

- Files using custom merge drivers (STATE.md via the ARG1-052 driver)
  — the dryrun exercises the configured driver.
- Registration-style files (`__main__.py`) — the dryrun observes
  whether `ort`'s actual conflict resolution succeeds.
- Future shared-file patterns we haven't seen yet — no allowlist or
  heuristic update needed.

The escalation's Option B (gitattributes-only) is rejected as
incomplete; this richer Option B is what's ratified.

## Reasoning (deferral)

ARG1-021 stays strict on main rather than blocking on ARG1-066 because:

1. ARG1-021 is correct under the strict criterion — false-conservative,
   never false-permissive. ARCHITECTURE.md §Invariants L274 explicitly
   sanctions "degraded but correct" as the safe failure mode.
2. ARG1-022 + ARG1-023 + ARG1-013 + ARG1-054 may surface additional
   patterns about how independence detection gets called in practice;
   ARG1-066's design benefits from that evidence.
3. ARG1-066 is a real architectural ticket (~200 lines, dry-run merge
   plumbing, rollback semantics, hook interaction with ARG1-032,
   merge-driver invocation correctness). It deserves focused work,
   not a quick amendment.
4. Layer 2 bootstrap has critical-path priority. The throughput cost
   of strict during the remaining bootstrap is bounded (~30–60 min
   wall-clock across the rest of Layer 2).

## Reasoning (rejecting Option A)

Option A's allowlist is a static heuristic that requires manual
maintenance every time a new shared-registration site appears, says
nothing about *why* a file is on the list (the rationale "ort merges
keep-both cleanly" lives outside the list itself), and would have to
special-case STATE.md's merge-driver behavior separately. ARG1-066's
dry-run mechanism subsumes Option A entirely with no allowlist to
maintain.

## Consequences

- Layer 2 remaining tickets that share `argos/cli/__main__.py`
  registrations will be dispatched serially under the strict criterion.
  Acceptable per ARCHITECTURE.md §Invariants.
- ARG1-066 is the binding commitment to ship richer Option B before
  Layer 3 dogfood validation.
- The §Independence detection sections of ARCHITECTURE.md and the
  orchestrator agent doc remain accurate under strict. ARG1-066 amends
  both as part of its scope.
- The four prior escalation precedents all landed ADRs or ticket-level
  decisions; this one lands a deferred ticket-level commitment, which
  is a slightly weaker artifact than an ADR. If the operator later
  decides ARG1-066's mechanism deserves an ADR (e.g. for distribution
  channel or future contributor onboarding), that's a separate amendment.
