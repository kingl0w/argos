# ARG1-023 — Worktree merge-on-pass, preserve-on-fail

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P1
**Epic:** 3 (Parallel session manager)

## Intent

After a session's verifier returns `pass` or `pass-with-minors`, attempt fast-forward merge of the worktree's branch (`argos/{ticket-id}`) back to base; on conflict, halt the merge and write a blocking escalation (the verifier already passed — conflicts are an integration-level concern). On `fail`, leave the worktree and branch in place untouched for operator inspection. Return a structured result so the orchestrator can update the dispatch log.

## Context

ARCHITECTURE.md §Components/Parallel Session Manager specifies fast-forward-or-three-way-merge on pass, preserve-on-fail. Worktree pruning of merged branches is `argos sync`'s job (ARG1-004), not this ticket.

## Non-goals

- No worktree deletion on pass (operator may want to inspect; pruning is `argos sync`).
- No conflict resolution. Conflicts always escalate.
- No rebase strategy. v1.0 uses fast-forward when possible, three-way merge otherwise.
- No revert of merged work on subsequent failures.

## Acceptance criteria

- [ ] With a worktree branch one commit ahead of base, `argos worktree-finalize --ticket ARG1-099 --result pass` exits 0; `git log --oneline base..argos/ARG1-099` is empty after merge (fast-forwarded).
- [ ] With a worktree branch where base has moved but no conflicts exist, `argos worktree-finalize --ticket ARG1-099 --result pass` exits 0; `git log --first-parent base | head -1` shows a merge commit.
- [ ] With a worktree branch that conflicts with base, `argos worktree-finalize --ticket ARG1-099 --result pass` exits non-zero; the merge is aborted (`git status` in base shows clean tree); a file under `argos/specs/escalations/ARG1-099-*.md` exists with `severity: blocking` and body containing `merge conflict`.
- [ ] With result `fail`, `argos worktree-finalize --ticket ARG1-099 --result fail` exits 0; `test -d .argos/worktrees/ARG1-099-*` exits 0 (preserved); the branch `argos/ARG1-099` still exists (`git branch --list 'argos/ARG1-099'` non-empty).
- [ ] With result `pass-with-minors`, behavior is identical to `pass` (merge attempted).
- [ ] `argos worktree-finalize --json --ticket ARG1-099 --result pass` emits a JSON object with keys `merged`, `merge_strategy` (`ff` or `three-way`), `conflicts`, `worktree_preserved`.

## Depends on

- ARG1-020 (worktree spawn — produces the worktrees this ticket finalizes)

## Touches

- `argos/cli/orchestrator/merge.py` (or equivalent — new)
- `argos/cli/commands/worktree_finalize.py` (or equivalent — new)
- `argos/cli/tests/test_worktree_finalize.py` (or equivalent)

## Parallelizable with

- ARG1-003 (status)
- ARG1-004 (sync)
- ARG1-013 (auto-fix retry — different module)
- ARG1-021 (independence — different module)
- ARG1-022 (parallel dispatch — different module)
- ARG1-031 (verifier structured decision)
- ARG1-041 (escalation writer)
- ARG1-054 (cycle close)

## Plan

files_touched:
  - argos/cli/orchestrator/merge.py
  - argos/cli/commands/worktree_finalize.py
  - argos/cli/__main__.py
  - argos/cli/tests/test_worktree_finalize.py
  - argos/specs/v1.0/tickets/ARG1-023-worktree-merge-preserve.md

### Architectural choices (locked)

1. **Single-ticket primitive (Q1 — merge order).** `argos worktree-finalize`
   takes `--ticket` (singular). Group-merge ordering is the orchestrator's
   authority per `agents/orchestrator.md` §Decision authority ("When to
   merge a verifier-passed worktree back to base"). The orchestrator
   invokes finalize repeatedly in whatever order it picks — input order,
   completion order, or anything else. ARG1-023 expresses no opinion.
   Batch-merge atomicity, if ever required, is a follow-up ticket.

2. **Failed disposition — always preserve (Q2).** `result=fail` is a
   no-op merge: worktree, branch, and base branch are untouched. AC#4 is
   unconditional ("With result `fail`, … `test -d .argos/worktrees/...` exits 0;
   the branch `argos/ARG1-099` still exists"). ARG1-013's auto-fix retry
   contract says "do not spawn a new worktree; the partial state is
   informative for the retry" (`agents/orchestrator.md` §Auto-fix retry),
   so removal here would defeat the retry. First-failure-only preservation
   is rejected: the AC has no "first time" carve-out and ARG1-013 may need
   the worktree across both retries.

3. **Conflict — abort + escalate (Q3).** Three-way merge that produces
   conflicts is rolled back via `git merge --abort`, restoring the base
   branch to its pre-merge state. A `severity: blocking` escalation
   (`raised_by: orchestrator`) is written under
   `argos/specs/escalations/`; the body opens with the literal substring
   `merge conflict` (AC#3). The merge does not partial-apply; the
   worktree and branch stay for operator inspection.
   Per `agents/orchestrator.md` §Escalation triggers item 6:
   "merge-time semantic conflict on file-disjoint sessions" is the
   orchestrator's escalation surface — finalize is the writer.

4. **No `--dry-run` (Q4).** Spec is silent and the AC list does not
   include it. `--json` covers post-execution machine-readable output.
   YAGNI; if a downstream caller needs preview semantics, file an
   amendment ticket.

5. **Merge-strategy ordering — ff first, three-way fallback.** Linear
   history is preferred when achievable (ARCHITECTURE.md §Components/
   Parallel Session Manager pins fast-forward-or-three-way). Rebase is
   explicitly out of scope per Non-goals. `--ff-only` leaves the working
   tree untouched on failure, so the fallback to `--no-ff --no-edit`
   does not need a separate stash/restore step.

6. **Repository scope — main worktree.** Branches are repository-scoped
   so finalize must run in the main worktree (where `main` is checked
   out and the merge can advance it). `find_main_repo_root` parses
   `git worktree list --porcelain` and resolves to the first listed
   worktree, which is git's canonical main. The CLI accepts an explicit
   `--repo-root` override for tests and for unusual operator setups.

7. **Working-tree dirty guard — tracked files only.** A pre-merge guard
   refuses to merge when `git status --porcelain --untracked-files=no`
   is non-empty, mirroring `git merge`'s own contract. Untracked files
   (registered sibling worktrees under `.argos/worktrees/`, the
   escalation we are about to write) do not count toward dirtiness.

8. **Pre-commit hook (ARG1-032) — no bypass.** Three-way merge auto-commits
   trigger the pre-commit hook. With the ARG1-052 `argos-state` merge
   driver registered (via `.gitattributes`), STATE.md merges in-place
   producing a diff that contains only verifier-author `argos:entry`
   blocks, which the hook accepts. Confirmed empirically by
   `FinalizeWithStateAndHookTests.test_merge_with_state_changes_and_hook_succeeds`.
   No `ARGOS_CYCLE_CLOSE` bypass is set, no `--no-verify` is passed.

### Module shape

`argos/cli/orchestrator/merge.py` exposes the library:

- `FinalizeResult` (frozen dataclass): `ticket_id`, `result`, `branch`,
  `base_branch`, `merged`, `merge_strategy` (`"ff"` | `"three-way"` |
  `None`), `conflicts`, `worktree_preserved`, `escalation_path`.
- `FinalizeError` / `InvalidResultError` / `DirtyWorkingTreeError` /
  `MissingBranchError` — error hierarchy.
- `finalize(*, ticket_id, result, repo_root=None, base_branch="main",
  escalation_dir=None, now=None) -> FinalizeResult` — the public entry
  point. Side-effects: at most one `git checkout`, one `git merge`
  (potentially two attempts: ff then three-way), one `git merge --abort`
  on conflict, and one escalation file write on conflict.
- `find_main_repo_root(start=None) -> Path` — resolves the canonical
  main worktree via `git worktree list --porcelain`.

`argos/cli/commands/worktree_finalize.py` is the CLI:

- `argos worktree-finalize --ticket ARG1-099 --result pass [--json]
  [--base main] [--escalation-dir <dir>] [--repo-root <path>]`
- Exit codes: `0` on success (pass merged or fail preserved); `1` on
  conflict (escalation written) or operational failure (dirty base,
  missing branch, git plumbing); `2` on argument errors.

### Test plan

`argos/cli/tests/test_worktree_finalize.py` (12 tests, stdlib `unittest`):

- Library-level (`finalize` direct calls): one test per AC plus the
  empirical state-and-hook coexistence test.
  - `FinalizeFastForwardTests` — AC#1 ff merge.
  - `FinalizeThreeWayTests` — AC#2 three-way merge.
  - `FinalizeConflictTests` — AC#3 conflict aborts and escalates.
  - `FinalizeFailPreservesTests` — AC#4 fail no-op preserves.
  - `FinalizePassWithMinorsTests` — AC#5 pass-with-minors == pass.
  - `FinalizeWithStateAndHookTests` — empirical: ARG1-032 hook +
    ARG1-052 driver coexist on auto-merge of STATE.md.
- CLI-surface (`python3 argos/cli/argos worktree-finalize ...` as
  subprocess): one test per AC.
  - `FinalizeCLIFastForwardTests` — AC#1 via CLI.
  - `FinalizeCLIThreeWayTests` — AC#2 via CLI.
  - `FinalizeCLIConflictTests` — AC#3 via CLI.
  - `FinalizeCLIFailTests` — AC#4 via CLI (with a real `git worktree add`
    so the AC's `test -d` glob has something to find).
  - `FinalizeCLIPassWithMinorsTests` — AC#5 via CLI.
  - `FinalizeCLIJSONTests` — AC#6 JSON keys.

### What is NOT in scope

- Auto-fix retry (ARG1-013).
- Worktree pruning on pass (`argos sync`).
- Branch deletion of merged branches (`argos sync`).
- Multi-ticket batch finalize (no ticket; orchestrator drives one-at-a-time).
- Rebase strategy (Non-goals).
- Conflict resolution (Non-goals).

## Verification

**Branch:** `ticket/ARG1-023` (worktree `argos-v1-arg1-023`).
**Author:** verifier.
**Stdlib-only:** preserved — `argos lint-imports argos/` exits 0.

ACs: 6/6 met (verified literally against the AC text via fresh tmp
git repos plus a 12-test stdlib `unittest` suite).

- **AC#1** (ff merge: branch one ahead of base, log empty after).

  ```text
  worktree-finalize: ARG1-099: merged (ff) into main
  exit=0
  $ git log --oneline main..argos/ARG1-099
  (empty)
  ```

  Reproduced in `FinalizeFastForwardTests.test_ff_merges_and_log_empty`
  and `FinalizeCLIFastForwardTests.test_cli_ff_exit_zero_log_empty`.

- **AC#2** (three-way merge: base ahead, no conflict, merge commit
  appears as the most recent first-parent on main).

  ```text
  worktree-finalize: ARG1-099: merged (three-way) into main
  exit=0
  $ git log --first-parent --oneline main | head -1
  7ba1fe3 Merge branch 'argos/ARG1-099'
  ```

  Reproduced in `FinalizeThreeWayTests.test_three_way_merge_creates_merge_commit`
  and `FinalizeCLIThreeWayTests.test_cli_three_way_first_parent_is_merge`.

- **AC#3** (conflict: exit non-zero, base clean, blocking escalation
  with `merge conflict` body).

  ```text
  worktree-finalize: ARG1-099: merge conflict; merge aborted; escalation written to /tmp/.../argos/specs/escalations/ARG1-099-2026-05-03T18-01-52Z.md
  exit=1
  $ git status --porcelain --untracked-files=no
  (empty)
  $ test -e .git/MERGE_HEAD; echo $?
  1
  $ grep -c '^severity: blocking' argos/specs/escalations/ARG1-099-*.md
  1
  $ grep -c 'merge conflict' argos/specs/escalations/ARG1-099-*.md
  1
  ```

  "Clean tree" is interpreted in the merge-state sense: no
  `MERGE_HEAD`, no staged or unstaged changes to *tracked* files.
  The escalation file is a new untracked artifact (the AC's same
  sentence asserts it must exist), so an `--untracked-files=no`
  status is the correct check. Reproduced in
  `FinalizeConflictTests` and `FinalizeCLIConflictTests`.

- **AC#4** (fail: exit 0, worktree dir preserved, branch preserved).

  ```text
  worktree-finalize: ARG1-099: result=fail; worktree and branch preserved
  exit=0
  $ test -d .argos/worktrees/ARG1-099-deadbee; echo $?
  0
  $ git branch --list 'argos/ARG1-099'
  + argos/ARG1-099
  ```

  Reproduced in `FinalizeFailPreservesTests` and `FinalizeCLIFailTests`
  (the CLI test creates a real `git worktree add` so the AC's
  `test -d .argos/worktrees/ARG1-099-*` glob has a target).

- **AC#5** (pass-with-minors behaves identically to pass).

  ```text
  worktree-finalize: ARG1-099: merged (ff) into main
  exit=0
  $ git log --oneline main..argos/ARG1-099
  (empty)
  ```

  Reproduced in `FinalizePassWithMinorsTests` and
  `FinalizeCLIPassWithMinorsTests`.

- **AC#6** (`--json` emits the four required keys).

  ```text
  $ argos worktree-finalize --json --ticket ARG1-100 --result pass
  {"ticket_id":"ARG1-100","result":"pass","branch":"argos/ARG1-100",
   "base_branch":"main","merged":true,"merge_strategy":"ff",
   "conflicts":false,"worktree_preserved":true,"escalation_path":null}
  ```

  Required keys (`merged`, `merge_strategy`, `conflicts`,
  `worktree_preserved`) all present, all four typed as the AC dictates.
  Reproduced in `FinalizeCLIJSONTests.test_cli_json_contains_required_keys`.

**Empirical confirmation of the brief's pre-commit-hook claim.**
`FinalizeWithStateAndHookTests.test_merge_with_state_changes_and_hook_succeeds`
constructs a tmp repo with both the ARG1-052 merge driver registered
and the ARG1-032 pre-commit hook installed, then runs a three-way
merge whose worktree branch and main branch each appended a new
`<!-- argos:entry author=verifier -->` block to STATE.md. The
auto-merge commit's pre-commit hook fires and accepts the merge
(no `--no-verify`, no `ARGOS_CYCLE_CLOSE` bypass). The merged STATE.md
contains all three blocks (seed + branch + main) — the merge driver
correctly produced their union.

**Tests:**

- `python3 -m unittest argos.cli.tests.test_worktree_finalize -v` →
  **Ran 12 tests in 0.62s, OK**.
- `python3 -m unittest discover -s argos/cli/tests` →
  **Ran 260 tests in 9.70s, OK**. Zero regressions.

**Lint:** `python3 -m argos.cli lint-imports argos/` → exit 0.

**Architectural choices locked (per session brief Q1–Q4).**

1. **Q1 — Merge order.** Single-ticket primitive; ordering is the
   orchestrator's authority, not ARG1-023's.
2. **Q2 — Failed disposition.** Always preserve worktree + branch on
   `fail`. ARG1-013 reuses the same worktree for retry.
3. **Q3 — Conflict.** Abort with `git merge --abort`, write a
   `severity: blocking` escalation, exit non-zero. Worktree + branch
   preserved.
4. **Q4 — Dry-run.** Not in spec, not implemented. `--json` covers
   machine-readable output.

No escalations filed.

Decision: **pass**.
