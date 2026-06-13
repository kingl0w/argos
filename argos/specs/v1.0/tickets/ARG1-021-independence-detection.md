# ARG1-021 — Independence detection via file-overlap analysis

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 3 (Parallel session manager)

## Intent

Implement file-overlap independence detection. The planner subagent gains a required `files_touched:` field in its Plan-section output; the orchestrator parses this field across candidate tickets and computes pairwise disjointness. Two tickets are independent iff their `files_touched:` sets are disjoint AND neither lists the other in `depends_on:` frontmatter. Output is a list of independence groups feeding ARG1-022.

## Context

ARCHITECTURE.md §Components/Parallel Session Manager § "Independence detection" specifies file-overlap as the v1.0 strategy. PRD success criterion #4 (≥2x parallel speedup) depends on detection being good enough to find genuinely independent tickets — and conservative enough not to falsely parallelize colliding ones.

## Non-goals

- No directory-prefix overlap heuristics (TODO in ARCHITECTURE.md — left for follow-up).
- No import-graph analysis (a ticket's `files_touched` may transitively conflict via imports; v1.0 accepts this risk).
- No dynamic re-evaluation mid-batch (independence is computed once per batch).
- No dry-plan caching (ARCHITECTURE.md TODO — follow-up).

## Acceptance criteria

- [ ] `argos independence ARG1-099 ARG1-100` (two synthetic tickets with disjoint `files_touched`) exits 0; stdout contains `independent`.
- [ ] `argos independence ARG1-099 ARG1-101` (synthetic tickets sharing one file in `files_touched`) exits 0; stdout contains `dependent` and names the conflicting file path.
- [ ] `argos independence ARG1-099 ARG1-102` (synthetic ticket where ARG1-102 has `depends_on: [ARG1-099]` in frontmatter) exits 0; stdout contains `dependent` and the reason `depends_on`.
- [ ] On a ticket whose Plan section is missing `files_touched:`, `argos independence` exits non-zero; stderr names the ticket ID and contains `missing files_touched`.
- [ ] `argos independence --json ARG1-099 ARG1-100 ARG1-101` emits a JSON object on stdout with key `groups` whose value is a list of lists of ticket IDs (each inner list a maximal independent group).
- [ ] `.claude/agents/planner.md` body contains the literal string `files_touched:` (planner instructed to emit the field).

## Depends on

- ARG1-010 (orchestrator agent — consumer)
- ARG1-020 (worktree spawn — needed to invoke planner in dry mode)

## Touches

- `argos/cli/orchestrator/independence.py` (or equivalent — new)
- `.claude/agents/planner.md` (modify — add `files_touched:` requirement)
- `argos/specs/v1.0/agents/planner.md` (new — canonical mirror)
- `argos/cli/tests/test_independence.py` (or equivalent)

## Parallelizable with

- ARG1-003 (status)
- ARG1-005 (attend)
- ARG1-012 (dispatch log writer — different module)
- ARG1-023 (worktree merge — different module)
- ARG1-031 (verifier structured decision)
- ARG1-041 (escalation writer)
- ARG1-052 (merge driver)

## Plan

files_touched:
  - argos/cli/orchestrator/__init__.py
  - argos/cli/orchestrator/independence.py
  - argos/cli/commands/independence.py
  - argos/cli/__main__.py
  - argos/cli/tests/test_independence.py
  - .claude/agents/planner.md
  - argos/specs/v1.0/agents/planner.md
  - argos/specs/v1.0/tickets/ARG1-021-independence-detection.md
  - argos/specs/escalations/ARG1-021-2026-05-02T15-49-14Z.md
  - argos/specs/v1.0/STATE.md

### Files touched

| Path | Status | Purpose |
|------|--------|---------|
| `argos/cli/orchestrator/__init__.py` | new | Package marker for the orchestrator-side helper modules consumed by ARG1-022. |
| `argos/cli/orchestrator/independence.py` | new | Library: `Ticket` / `PairResult` dataclasses, `load_ticket`, `is_independent`, `partition`. Strict file-disjointness criterion per ARCHITECTURE.md §Independence detection. |
| `argos/cli/commands/independence.py` | new | argparse shim for `argos independence ARG1-099 ARG1-100 ... [--json] [--ticket-dir DIR]`. Maps library exceptions to AC-grep-shaped stderr. |
| `argos/cli/__main__.py` | edit | Registered `independence` in `PUBLIC_SUBCOMMANDS`, dispatcher branch, `--help` line. Three localized edits, keep-both-registrations pattern. |
| `argos/cli/tests/test_independence.py` | new | unittest tests across `LoadTicketTests` / `IsIndependentTests` / `PartitionTests` / `CLIAcceptanceTests` / `CLIRoundTripTests` / `PlannerMirrorTests`. 28 tests. |
| `.claude/agents/planner.md` | edit | Added `files_touched:` requirement to the planner's ## Plan output contract. Required by AC#6. |
| `argos/specs/v1.0/agents/planner.md` | new | Byte-identical canonical mirror of `.claude/agents/planner.md` (precedent: ARG1-010, ARG1-030, ARG1-031). |
| `argos/specs/v1.0/tickets/ARG1-021-independence-detection.md` | edit | Plan + Verification sections appended (this file). |
| `argos/specs/escalations/ARG1-021-2026-05-02T15-49-14Z.md` | new | Advisory escalation flagging the strict-vs-relaxed criterion question (see Verification §Criterion choice below). |
| `argos/specs/v1.0/STATE.md` | append | v1.0-format verifier block on pass via `argos state-append --suffix done`. |

### Criterion choice (load-bearing — reasoned in this Plan)

Three canonical sources pin the criterion:

1. ARG1-021 §Intent: *"Two tickets are independent iff their `files_touched:` sets are disjoint AND neither lists the other in `depends_on:` frontmatter."*
2. ARCHITECTURE.md §Independence detection line 106 (verbatim): *"Two tickets are independent iff their file sets are disjoint AND neither lists the other in `depends_on:` frontmatter."*
3. `argos/specs/v1.0/agents/orchestrator.md` lines 89–94 (verbatim): *"Both conditions must hold. If either is unknown or ambiguous for a candidate pair, treat the pair as **dependent** and serialize."*

All three are aligned on **strict file-set disjointness**, no carve-outs. ARCHITECTURE.md §Invariants line 274 reinforces this: *"if independence analysis fails or is unavailable, the orchestrator falls back to serial dispatch (degraded but correct)."*

**Empirical counter-evidence acknowledged:** ARG1-011 / ARG1-012 (and Layer-2 ARG1-020 / ARG1-031 / ARG1-041) shipped successfully despite all touching `argos/cli/__main__.py`. STATE.md `Done this cycle` entries document the merges succeeded under the *"keep both registrations"* pattern. The strict criterion would have falsely serialized those batches.

**This ticket ships the strict criterion** because:

- Anything else is an ADR amendment to ARCHITECTURE.md §Independence detection — out of scope for ARG1-021.
- The strict criterion satisfies the explicit "degraded but correct" invariant.
- Two viable relaxations (hard-coded carve-out allowlist; merge-strategy-aware criterion) exist but choosing between them is an operator decision, not a coder one.

**Escalation filed**: `argos/specs/escalations/ARG1-021-2026-05-02T15-49-14Z.md` (advisory severity, raised_by coder). The escalation lays out the empirical evidence, two relaxation options (Option A — hard-coded carve-out; Option B — merge-strategy-aware), and recommends a follow-up ADR/ticket if the operator wants ARG1-022 to consume a relaxed criterion. Until that ADR lands, ARG1-021 + ARG1-022 run on strict.

### Changes per file

#### `argos/cli/orchestrator/independence.py` (new — library)

Public API:

- `load_ticket(ticket_id, ticket_dir=DEFAULT_TICKET_DIR) -> Ticket` — locates the ticket file under `ticket_dir` (glob `<id>*.md`, accepts both `<id>.md` and `<id>-<slug>.md`), parses the frontmatter `depends_on:` field (block-sequence form OR `[A, B]` flow-style — the AC#3 example uses flow-style and ADR-002's strict frontmatter parser would reject it, so this module hand-rolls a small `depends_on`-only flow-style parser scoped to this one field), parses the `## Plan` section's `files_touched:` block sequence, and returns a frozen `Ticket(ticket_id, path, depends_on, files_touched)`. Raises `MissingFilesTouchedError` (with `ticket_id` attribute and `missing files_touched` substring in message) when the field or the Plan section is absent. Raises `TicketNotFoundError` when no file matches. Raises `TicketParseError` on structural problems.
- `is_independent(a, b) -> PairResult` — returns a `PairResult(a, b, independent, reason, shared_files)`. Reason ordering is `depends_on` first, then `shared file: <path>[, <path>...]`, so the reason string is deterministic when both conditions would fire.
- `partition(tickets) -> list[list[str]]` — first-fit greedy partition into independence groups. Locally maximal under input ordering (a ticket is added to the earliest existing group that accepts it; a new group opens only when no existing group does). Deterministic. Optimality not guaranteed (graph-coloring is NP-hard); v1.0 favors a simple, predictable partition over an optimal one.

#### `argos/cli/commands/independence.py` (new — CLI shim)

argparse for `tickets` (nargs='+'), `--json`, `--ticket-dir`. Loads every ticket; on the first parse failure writes `independence: <ticket_id>: <reason>` to stderr and returns exit 2. On success, computes pairwise `is_independent` results across all C(N, 2) pairs, computes the partition, and emits text or JSON per `--json`.

Output contracts:

- Text: one `independent: A B` or `dependent: A B (<reason>)` line per pair, plus one `group N: T1 T2 ...` line per group.
- JSON: `{"groups": [[...], [...]], "pairs": [{a, b, independent, reason, shared_files}, ...]}` (sorted keys, indent=2).
- Exit 0 on parse success (regardless of independent vs dependent verdict). Exit 2 on parse failure or usage error.

#### `argos/cli/__main__.py` (edit)

Three localized edits per the precedent set by ARG1-011 / ARG1-012 / ARG1-020 / ARG1-031 / ARG1-041:

1. Add `"independence"` to `PUBLIC_SUBCOMMANDS` (now an 8-tuple).
2. Add a one-line entry under the `Public subcommands:` section of `_print_usage`.
3. Add a dispatcher branch `if head == "independence": from argos.cli.commands.independence import main as independence_main; return independence_main(rest)`.

This is the file that ARG1-011 / ARG1-012 / ARG1-020 / ARG1-031 / ARG1-041 all also edited under the "keep both registrations" merge pattern. Per the strict criterion ARG1-021 ships, this would *not* have been parallelizable with those tickets — see the escalation for the trade-off.

#### `.claude/agents/planner.md` + `argos/specs/v1.0/agents/planner.md` (mirror pair)

Added a `files_touched:` requirement to the planner's ## Plan output contract:

- One bullet under "Produce a ## Plan section" pointing at the new field as the ARG1-021 contract.
- A new `### `files_touched:` field (required)` subsection documenting:
  - The exact format (ADR-002 §3 block sequence, repo-relative paths).
  - The "edits not reads" rule.
  - The empty-list-allowed convention for spec-only tickets.
  - That the existing human-readable "Files touched" table is kept; the new field is the machine-parseable mirror.

Mirror invariant: `diff -q .claude/agents/planner.md argos/specs/v1.0/agents/planner.md` exits 0. Verified.

### Acceptance criteria mapping

- AC#1 — `argos independence ARG1-099 ARG1-100` (disjoint) → exits 0; stdout contains `independent`. ✅ Implemented + verified live.
- AC#2 — `argos independence ARG1-099 ARG1-101` (shared) → exits 0; stdout contains `dependent` AND the conflicting file path. ✅ Implemented + verified live.
- AC#3 — `argos independence ARG1-099 ARG1-102` (depends_on flow-style) → exits 0; stdout contains `dependent` AND `depends_on`. ✅ Implemented + verified live (flow-style parser added inside the module, scoped to `depends_on:` only).
- AC#4 — Plan section without `files_touched:` → exits non-zero; stderr names ticket id AND contains `missing files_touched`. ✅ Implemented + verified live (exit code 2, message `independence: ARG1-103: missing files_touched in ## Plan section`).
- AC#5 — `--json ARG1-099 ARG1-100 ARG1-101` → JSON object with key `groups` whose value is a list of lists of ticket ids. ✅ Implemented + verified live.
- AC#6 — `.claude/agents/planner.md` body contains literal `files_touched:`. ✅ `grep -F` finds 7 matches; `diff -q` against the mirror exits 0.

### Test strategy

`argos/cli/tests/test_independence.py` — 28 tests across:

- `LoadTicketTests` (8 tests) — block-sequence parsing, flow-style depends_on, missing field detection, empty-list validity, ticket-not-found, and the "extra Plan content does not swallow files_touched" round-trip.
- `IsIndependentTests` (5 tests) — disjoint/independent, shared file/dependent, depends_on/dependent (both directions), depends_on takes priority over shared file (deterministic reason ordering).
- `PartitionTests` (4 tests) — three independent tickets one group, two share third independent (greedy first-fit assignment), depends_on chain, deterministic.
- `CLIAcceptanceTests` (6 tests) — one test per AC, invokes the real CLI binary via subprocess.
- `CLIRoundTripTests` (3 tests) — no-args/usage, unknown ticket, subcommand-in-main-help.
- `PlannerMirrorTests` (2 tests) — mirror byte-identical, mirror contains `files_touched:`.

Run: `python3 -m unittest argos.cli.tests.test_independence -v` → 28/28 OK.
Regression: `python3 -m unittest discover -s argos/cli/tests` → 210/210 OK (was 166 before this ticket; ARG1-011 + ARG1-012 added another 16 in their merges, this ticket adds 28).

## Verification

<!-- argos:verifier-output schema=verifier-output@1 -->

```yaml
ticket: ARG1-021
session: arg1-021-worktree
verified_at: 2026-05-02T15:49:14Z
decision: pass
findings: []
acceptance_criteria:
  - id: AC#1
    state: pass
    evidence: |
      argos independence --ticket-dir <tmp> ARG1-099 ARG1-100 → exit 0; stdout
      "independent: ARG1-099 ARG1-100\ngroup 1: ARG1-099 ARG1-100\n".
  - id: AC#2
    state: pass
    evidence: |
      argos independence --ticket-dir <tmp> ARG1-099 ARG1-101 → exit 0; stdout
      "dependent: ARG1-099 ARG1-101 (shared file: argos/cli/a.py)" — names the
      conflicting path verbatim.
  - id: AC#3
    state: pass
    evidence: |
      argos independence --ticket-dir <tmp> ARG1-099 ARG1-102 → exit 0; stdout
      "dependent: ARG1-099 ARG1-102 (depends_on)" with ARG1-102 frontmatter
      "depends_on: [ARG1-099]" (flow-style, matches the AC literal text).
  - id: AC#4
    state: pass
    evidence: |
      argos independence --ticket-dir <tmp> ARG1-099 ARG1-103 (where ARG1-103's
      Plan omits files_touched:) → exit 2; stderr "independence: ARG1-103:
      missing files_touched in ## Plan section". Contains both the ticket id
      and the literal "missing files_touched".
  - id: AC#5
    state: pass
    evidence: |
      argos independence --json --ticket-dir <tmp> ARG1-099 ARG1-100 ARG1-101 →
      exit 0; JSON parses; payload["groups"] is [["ARG1-099","ARG1-100"],
      ["ARG1-101"]] — list of lists of strings, ARG1-099 and ARG1-101 (which
      share argos/cli/a.py) correctly placed in different groups.
  - id: AC#6
    state: pass
    evidence: |
      grep -F 'files_touched:' .claude/agents/planner.md → 7 matches; diff -q
      .claude/agents/planner.md argos/specs/v1.0/agents/planner.md → exit 0
      (byte-identical mirror).
tests:
  - command: python3 -m unittest argos.cli.tests.test_independence -v
    result: "Ran 28 tests in 0.216s — OK"
  - command: python3 -m unittest discover -s argos/cli/tests
    result: "Ran 210 tests in 4.893s — OK (regression sweep)"
escalations:
  - file: argos/specs/escalations/ARG1-021-2026-05-02T15-49-14Z.md
    severity: advisory
    summary: |
      Strict file-disjointness criterion ships per spec; empirical evidence
      (ARG1-011/012 + Layer-2 batches all touched argos/cli/__main__.py and
      merged cleanly) suggests a relaxation may be desirable. Two options
      (carve-out allowlist; merge-strategy-aware criterion) require operator
      decision + ADR amendment to ARCHITECTURE.md §Independence detection.
      Advisory because ARG1-021 is fully shipped against the canonical specs;
      the gap is "throughput floor under strict" not "broken dispatch."
out_of_scope_confirmed:
  - No directory-prefix overlap heuristics (ARG1-021 §Non-goals).
  - No import-graph analysis (ARG1-021 §Non-goals).
  - No content-aware merge-strategy carve-outs (escalated above).
  - No dynamic re-evaluation mid-batch (ARG1-021 §Non-goals).
  - No dry-plan caching (ARG1-021 §Non-goals).
  - No edits to ARCHITECTURE.md or the orchestrator agent doc (those would be
    the venues for any criterion relaxation, gated by the escalation).
```

<!-- /argos:verifier-output -->

## Superseded by ARG1-066

The strict file-set disjointness criterion shipped by this ticket is **superseded
by ARG1-066** (merge-aware independence detection), per the ratified operator
decision `argos/specs/v1.0/decisions/ESC-ARG1-021-independence-criterion.md`.

ARG1-066 replaces the static file-overlap check with a dynamic dry-run
`git merge --no-commit --no-ff` (both directions, in a throwaway staging
worktree) that exercises the actual configured merge — subsuming both the
custom-driver case (STATE.md via the ARG1-052 driver) and the registration
pattern (`argos/cli/__main__.py`) that this strict criterion falsely serialized.
The strict criterion is **not deleted**: ARG1-066 demotes it to the
degraded-but-correct fallback used when a pair's branches do not yet exist.

The implementation lives in the same module (`argos/cli/orchestrator/independence.py`),
shipped on branch `ticket/ARG1-066`; see that ticket
(`argos/specs/v1.0/tickets/ARG1-066-merge-aware-independence.md`) and its commit
for the full change. ARCHITECTURE.md §Independence detection and
`argos/specs/v1.0/agents/orchestrator.md` §Parallel dispatch were amended by
ARG1-066 to describe the merge-dryrun mechanism (replacing the strict-criterion
wording this ticket established).

