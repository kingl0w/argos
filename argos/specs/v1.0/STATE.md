# Argos v1.0 — State

**Format:** append-mostly timestamped blocks per `argos/specs/v1.0/ARCHITECTURE.md` §Contracts/STATE.md format. Verifier-only writes during the loop; out-of-loop edits are append-only and signed below the entry.

## Current focus

Epic 4 — severity-tiered verifier. ARG1-030 (rubric + structured output) is the foundation; ARG1-031 (consumer) and ARG1-013 (auto-fix retry) build on it.

## Queue

- _none_ (2026-07-01, human out-of-loop edit: ARG1-003 / ARG1-004 / ARG1-005 removed from the queue — all three verified and merged; see their entries below and the root `argos/specs/STATE.md`)

## In progress

_none_

## Done this cycle

<!-- argos:entry id=2026-04-26T00:00:00Z-ARG1-030 ticket=ARG1-030 author=verifier session=arg1-030-worktree -->
- **[2026-04-26T00:00:00Z] ARG1-030 — verified** (worktree `argos-v1-arg1-030`, branch `ticket/ARG1-030`)
  - Files changed: `.claude/agents/verifier.md`, `argos/specs/v1.0/agents/verifier.md` (new), `argos/specs/v1.0/schemas/verifier-output.md` (new), `argos/cli/verifier_parser.py` (new), `argos/cli/argos` (new), `argos/cli/tests/test_verifier_parser.py` (new), `argos/__init__.py` / `argos/cli/__init__.py` / `argos/cli/tests/__init__.py` (new package-init files), `argos/specs/v1.0/tickets/ARG1-030-verifier-severity-rubric.md` (Plan + Verification sections)
  - ACs: 6/6 met. AC#1 six literals present (counts 9/6/6/3/3/1). AC#2 both MUST strings present (1/1). AC#3 mirror diff exits 0. AC#4 `findings:` count 5 in schema doc. AC#5 `argos verifier-parse` exits 0 on canonical example, JSON has `findings` (list) and `decision` (string). AC#6 `pass` / `pass-with-minors` / `fail` all present (counts 7/3/7).
  - Findings: 0 critical, 0 major, 0 minor.
  - Tests: `python3 -m unittest argos.cli.tests.test_verifier_parser -v` → 3 tests, all OK (Ran 3 tests in 0.046s).
  - Decision: pass
<!-- /argos:entry -->


<!-- argos:entry id=2026-04-26T22:57:57Z-ARG1-051 ticket=ARG1-051 author=verifier session=arg1-051-worktree -->
- **[2026-04-26T23:00:00Z] ARG1-051 — verified** (worktree `argos-v1-arg1-051`, branch `ticket/ARG1-051`)
  - Files changed: `argos/cli/state_append.py` (new), `argos/cli/commands/state_append.py` (new), `argos/cli/__main__.py` (registered `state-append` subcommand), `argos/cli/tests/test_state_append.py` (new), `argos/specs/v1.0/tickets/ARG1-051-state-append-helper.md` (Plan + Verification appended).
  - ACs: 7/7 met. AC#1 basic append produces a block with `id` matching the regex and attrs from flags. AC#2 block lands under `## Done this cycle` with no other `## ` heading between. AC#3 two concurrent calls (distinct tickets) both succeed via `fcntl.flock(LOCK_EX)` on sidecar `STATE.md.lock`. AC#4 same-ticket-same-second collisions resolve via 6-hex-char random suffix. AC#5 `--section "Nonexistent"` exits non-zero with `section not found` in stderr. AC#6 SIGKILL during pre-rename delay leaves STATE.md byte-identical and parser-clean (atomic write via `tempfile.mkstemp` + `os.replace`). AC#7 `--dry-run` prints block to stdout, file SHA-256 unchanged.
  - Findings: 0 critical, 0 major, 0 minor.
  - Tests: `python3 -m unittest argos.cli.tests.test_state_append -v` → 12 tests, all OK (Ran 12 tests in 1.231s). Regression: `python3 -m unittest argos.cli.tests.test_version argos.cli.tests.test_verifier_parser argos.cli.tests.test_escalation_validator argos.cli.tests.test_state_append -v` → 27 tests, all OK (Ran 27 tests in 1.347s). ADR-001 stdlib-only contract preserved (pyproject.toml unchanged).
  - Decision: pass
<!-- /argos:entry -->


<!-- argos:entry id=2026-04-26T23:18:08Z-ARG1-050 ticket=ARG1-050 author=backfill session=arg1-050-backfill -->
- **[2026-04-26T00:00:00Z] ARG1-050 — verified** (backfilled — original verifier ran before the v1.0 writer existed)
  - Files: argos/specs/v1.0/schemas/state-block.md, argos/specs/v1.0/schemas/examples/state-{valid,duplicate-id,missing-attr,unclosed-block}.md, argos/cli/state_parser.py, argos/cli/commands/state_parse.py, argos/cli/__main__.py, argos/cli/__init__.py, argos/cli/tests/test_state_parser.py.
  - ACs: 8/8 met. 13/13 pytest tests pass.
  - Findings: 0 critical, 0 major, 0 minor.
  - Decision: pass
<!-- /argos:entry -->

<!-- argos:entry id=2026-04-29T17:52:25Z-ARG1-010 ticket=ARG1-010 author=orchestrator session=arg1-010-worktree -->
- **[2026-04-29T00:00:00Z] ARG1-010 — orchestrator agent definition committed** (worktree `argos-v1-arg1-010`, branch `ticket/ARG1-010`)
  - Files changed: `argos/specs/v1.0/agents/orchestrator.md` (new), `.claude/agents/orchestrator.md` (new — byte-identical mirror).
  - ACs: 5/5 met. AC#1 `.claude/agents/orchestrator.md` exists. AC#2 v1.0 mirror exists; `diff -q` exits 0. AC#3 frontmatter parses as YAML; both `allowed_tools` and `denied_paths` keys present (verified with system `python3` + `pyyaml`). AC#4 `denied_paths` includes literal `argos/specs/PRD.md`, `argos/specs/ARCHITECTURE.md`, `argos/specs/STATE.md` (counts 2/2/2 across legacy + v1.0 paths). AC#5 body contains `dispatcher` (2), `reconciler` (2), `escalation` (15), `cannot mutate code` (1).
  - Definition covers: role/scope, inputs, outputs, decision authority, interaction contract with planner/coder/watchdog/verifier, parallel-dispatch contract (file-disjointness only — no content-level conflict detection), auto-fix retry contract (cap 1; ARG1-013 implements), escalation triggers calibrated to the three load-bearing precedents (ADR-001, tomllib-vs-tomli, .gitignore precedence) plus merge-time semantic conflict on disjoint sessions, termination conditions tied to `argos status` exit code, boundaries.
  - Out of scope per ticket: no CLI subcommand bodies, no worktree mechanics, no dispatch log writer, no `/orchestrate` slash command, no code.
  - Decision: pass
<!-- /argos:entry -->


<!-- argos:entry id=2026-04-29T18:13:12Z-ARG1-058 ticket=ARG1-058 author=coder session=arg1-058-worktree -->
- **[2026-04-29T00:00:00Z] ARG1-058 — narrowed STATE.md sidecar lock ignore** (worktree `argos-v1-arg1-058`, branch `ticket/ARG1-058`, branched from `main`)
  - Files changed: `.gitignore` (+1 line, `**/STATE.md.lock` under the `# Argos` block).
  - Supersedes ARG1-056's broader `*.lock` pattern. Project convention is per-file ignores for lockfiles (`Cargo.lock` is already explicit); a glob would silently swallow `yarn.lock` / `pnpm-lock.yaml` / `package-lock.json` if a JS component ever lands.
  - Verified: `git check-ignore -v` resolves both `argos/specs/STATE.md.lock` and `argos/specs/v1.0/STATE.md.lock` to `.gitignore:5:**/STATE.md.lock`. `git check-ignore -v yarn.lock` exits non-zero (not ignored); `package-lock.json` and `pnpm-lock.yaml` likewise not ignored. After `argos state-append`, the v1.0 sidecar lock is created and `git status` is clean modulo the STATE entry.
  - Branched from main, not from ARG1-056 — diff is reviewable independently. Operator handles merge order between ARG1-056 and ARG1-058 (recommendation: merge only ARG1-058, or merge ARG1-056 first then ARG1-058 will conflict on the .gitignore line and the narrower pattern wins).
  - Out of scope: no other .gitignore edits, no changes to ARG1-051 locking mechanism.
  - Decision: pass
<!-- /argos:entry -->

_none_


<!-- argos:entry id=2026-04-29T20:24:14Z-ARG1-061-done ticket=ARG1-061 author=coder session=arg1-061-worktree -->
- **[2026-04-29T20:30:00Z] ARG1-061 — `argos state-append --suffix` flag** (worktree `argos-v1-arg1-061`, branch `ticket/ARG1-061`)
  - Files changed: `argos/cli/state_append.py` (+`InvalidSuffixError`, `_DISAMBIG_SUFFIX_RE`, `suffix=` kwarg on `generate_id` and `append_block`), `argos/cli/commands/state_append.py` (+`--suffix` argparse option, `InvalidSuffixError` → exit 2), `argos/specs/v1.0/schemas/state-block.md` (id-format table row updated, new `### Id grammar (optional slots)` paragraph documenting both the disambiguation suffix and the collision-retry hex), `argos/cli/tests/test_state_append.py` (+`StateAppendSuffixTests`, 8 new tests), `argos/specs/v1.0/tickets/ARG1-061-state-append-suffix-flag.md` (new ticket file).
  - ACs: 9/9 met. AC#1 happy path id matches `^…Z-ARG1-099-drift$`. AC#2-#4 reject `bad space` / `BAD` / `""` with exit 2 + stderr `invalid suffix`. AC#5 `valid-slug-123` accepted. AC#6 collision-with-suffix produces `…-drift-{6hex}`. AC#7 regression: flagless invocation produces `…Z-ARG1-099` byte-identical to pre-ARG1-061. AC#8 schema doc updated. AC#9 test suite passes.
  - Tests: `python3 -m unittest argos.cli.tests.test_state_append -v` → 20 tests, all OK (12 prior + 8 new). Regression: `test_version test_verifier_parser test_escalation_validator test_config` → 44 tests, all OK.
  - Stdlib-only preserved (no new imports beyond `re`, already present); ADR-001 + ADR-002 contracts intact.
  - This block's id uses `--suffix done` to dogfood the new flag.
  - Decision: pass
<!-- /argos:entry -->


<!-- argos:entry id=2026-04-29T21:17:11Z-ARG1-059-done ticket=ARG1-059 author=verifier session=arg1-059-worktree -->
- **[2026-04-29T22:30:00Z] ARG1-059 — yaml AC retrofit verified** (worktree `argos-v1-arg1-059`, branch `ticket/ARG1-059`)
  - Files changed: `argos/specs/v1.0/tickets/ARG1-010-orchestrator-agent-definition.md` (AC#3 only — pyyaml `import yaml` + `yaml.safe_load` replaced with `argos frontmatter-parse | python3 -c "import json,sys; ..."` stdlib pipeline; same two key-presence assertions); `argos/specs/v1.0/tickets/ARG1-012-dispatch-log-writer.md` (AC#1 only — same retrofit shape, six required dispatch-log keys); `argos/specs/v1.0/tickets/ARG1-059-retrofit-yaml-acs.md` (own ACs #1+#2 collapsed into a precise self-consistent check using `grep -nE '^- \[[ x]\] .*yaml\.safe_load' argos/specs/v1.0/tickets/*.md | grep -v 'ARG1-059-retrofit-yaml-acs'`; AC#5 prose reworded to remove embedded literal old-command quote).
  - Audit: `grep -rn 'import yaml\|yaml\.safe_load' argos/specs/v1.0/tickets/` — only AC checkbox lines containing `yaml.safe_load` were ARG1-010 line 27 and ARG1-012 line 25; both retrofitted. Remaining substring matches are non-AC prose (ARG1-030 plan-section narrative line 71 explaining why the verifier-output parser hand-rolls; ARG1-060 context line 14 quoting ARG1-010's prior state; ARG1-059's own scope description) — out of scope per ADR-002 §AC-text-only intent.
  - Verification: ARG1-010 retrofitted AC#3 run live against current `.claude/agents/orchestrator.md` exits 0 (both `allowed_tools` and `denied_paths` keys present in `argos frontmatter-parse` JSON output). ARG1-012 retrofitted AC#1 dry-passes against a synthetic dispatch-log fixture with all six required keys (exit 0; `frontmatter-parse` parses the synthetic frontmatter cleanly). ARG1-059's own AC#1 grep run on this branch returns no matches outside ARG1-059 (pipeline exits 1).
  - Tests: regression sweep `test_frontmatter_parser test_state_append test_version test_verifier_parser test_escalation_validator test_config` → 89 tests, all OK. No code changes; AC-text-only.
  - Out of scope confirmed: no edits to `.claude/agents/`, `argos/specs/v1.0/agents/`, `argos/cli/`, `argos/specs/v1.0/schemas/`, ADR-002, ARG1-060, or any Layer 2 ticket.
  - Closes the ARG1-010-drift block under §Known drift (sibling resolution entry follows).
  - Layer 2 unblocked: ARG1-020 / ARG1-031 / ARG1-041 are no longer at risk of inheriting the legacy `import yaml` AC pattern from shipped neighbors.
  - Decision: pass
<!-- /argos:entry -->


<!-- argos:entry id=2026-04-30T17:16:59Z-ARG1-063-done ticket=ARG1-063 author=verifier session=arg1-063-worktree -->
- **ARG1-063 — verified** (branch `ticket/ARG1-063`, worktree `argos-v1-arg1-063`)
  - Goal: convert `argos/cli/tests/test_state_parser.py` from pytest to unittest, restoring stdlib-only compliance per ADR-001 §Decision item 2 and ADR-002 §1.
  - Files changed: `argos/cli/tests/test_state_parser.py` (mechanical translation, 13 tests).
  - ACs: 6/6 met.
    - AC#1 `grep -E '^(import pytest|from pytest)' …` → exit 1 (no matches).
    - AC#2 `python3 -m unittest argos.cli.tests.test_state_parser -v` → Ran 13 tests, OK (0.104s). All 13 original test names preserved verbatim, now as methods on `ParseApiTests` (9) and `StateParseCLITests` (4).
    - AC#3 count parity: original 13 (`git show main:…|grep -cE '^def test_'`), new 13 (`grep -cE '^    def test_' …`).
    - AC#4 `python3 -m unittest discover -s argos/cli/tests` → Ran 148 tests, OK (4.983s). No collateral breakage.
    - AC#5 ast import-allowlist check → exit 0 (bad=[]). Allowlist used as written in the ticket spec; `__future__`, `json`, `subprocess`, `sys`, `unittest`, `pathlib`, and `argos` are the only top-level imports.
    - AC#6 `git diff main --name-only` → `argos/cli/tests/test_state_parser.py` only (this state-append produces the second expected path `argos/specs/v1.0/STATE.md`).
  - Translation notes: `pytest.raises` → `unittest.TestCase.assertRaises` with `cm.exception`; module-level functions → methods on `ParseApiTests` / `StateParseCLITests`; `assert` → `self.assertEqual` / `self.assertIn` / `self.assertGreaterEqual` / `self.assertNotEqual` / `self.assertIsInstance` / `self.assertTrue`. No subTest or setUp/tearDown needed — original tests had no fixtures or parametrize.
  - Findings: 0 critical, 0 major, 0 minor.
  - Decision: pass
  - Non-goal observation: this is the second planner-vs-shipped-spec deviation the verifier did not catch (first: ARG1-010 AC#3, drained via ARG1-057 + ADR-002 + ARG1-059). The ticket Non-goals section names ARG1-064 as the proposed follow-up to amend ARG1-030 with an import-allowlist AC; rubric NOT amended in this ticket.
<!-- /argos:entry -->


<!-- argos:entry id=2026-05-02T15:53:51Z-ARG1-021-done ticket=ARG1-021 author=verifier session=arg1-021-worktree -->
- **[2026-05-02T15:49:14Z] ARG1-021 — file-overlap independence detection** (worktree `argos-v1-arg1-021`, branch `ticket/ARG1-021`)
  - Files changed: `argos/cli/orchestrator/__init__.py` (new), `argos/cli/orchestrator/independence.py` (new — library; `Ticket` / `PairResult` / `load_ticket` / `is_independent` / `partition`), `argos/cli/commands/independence.py` (new — CLI shim), `argos/cli/__main__.py` (registered `independence` in `PUBLIC_SUBCOMMANDS`, `--help` line, dispatcher branch), `argos/cli/tests/test_independence.py` (new — 28 tests across 6 classes), `.claude/agents/planner.md` (added `files_touched:` requirement to the ## Plan output contract), `argos/specs/v1.0/agents/planner.md` (new — byte-identical mirror), `argos/specs/v1.0/tickets/ARG1-021-independence-detection.md` (Plan + Verification appended), `argos/specs/escalations/ARG1-021-2026-05-02T15-49-14Z.md` (new — advisory escalation).
  - Criterion: **strict file-set disjointness + depends_on exclusion**, exact wording from ARCHITECTURE.md §Independence detection line 106 and orchestrator agent doc lines 89–94. Three canonical sources aligned. The ticket spec, the architecture doc, and the orchestrator agent doc all forbid carve-outs at this layer.
  - ACs: 6/6 met (verified live in a tmp ticket-dir fixture via `python3 argos/cli/argos independence ...`). AC#1 disjoint → exit 0 stdout `independent`. AC#2 shared file → exit 0 stdout `dependent` + path. AC#3 depends_on flow-style → exit 0 stdout `dependent` + `depends_on`. AC#4 missing field → exit 2 stderr `ARG1-103: missing files_touched in ## Plan section`. AC#5 `--json` → JSON object with `groups` list-of-lists (ARG1-099 + ARG1-101 correctly placed in different groups since they share argos/cli/a.py). AC#6 `grep -F 'files_touched:' .claude/agents/planner.md` exit 0 (7 matches); `diff -q` against v1.0 mirror exit 0.
  - Findings: 0 critical, 0 major, 0 minor.
  - Tests: `python3 -m unittest argos.cli.tests.test_independence -v` → 28 tests, all OK (Ran 28 tests in 0.216s). Regression: `python3 -m unittest discover -s argos/cli/tests` → 210 tests, all OK (Ran 210 tests in 4.729s). Stdlib-only preserved (`re`, `json`, `argparse`, `sys`, `pathlib`, `dataclasses`, `typing` plus `__future__`); ADR-001 + ADR-002 contracts intact. `pyproject.toml` unchanged.
  - Escalation filed (advisory, not blocking): `argos/specs/escalations/ARG1-021-2026-05-02T15-49-14Z.md`. Empirical evidence (ARG1-011/012 + ARG1-020/031/041 all touched `argos/cli/__main__.py` and merged cleanly under "keep both registrations") suggests the strict criterion will falsely serialize Layer-2-shaped batches. Two relaxation options enumerated (Option A — hard-coded carve-out allowlist; Option B — merge-strategy-aware criterion); both require operator decision + ADR amendment to ARCHITECTURE.md §Independence detection. ARG1-022 inherits the strict criterion until that ADR lands; per ARCHITECTURE.md §Invariants line 274 this is "degraded but correct."
  - Sibling Layer-2 coordination: only `argos/cli/__main__.py` is shared with the cohort; three localized edits (`PUBLIC_SUBCOMMANDS` tuple, `_print_usage` line, dispatcher branch) under the keep-both-registrations precedent already established by ARG1-011 / ARG1-012 / ARG1-020 / ARG1-031 / ARG1-041.
  - Decision: pass
<!-- /argos:entry -->


<!-- argos:entry id=2026-05-03T16:53:42Z-ARG1-064-done ticket=ARG1-064 author=verifier session=arg1-064-worktree -->
- **[2026-05-03T00:00:00Z] ARG1-064 — verified** (worktree `argos-v1-arg1-064`, branch `ticket/ARG1-064`)
  - Files changed: `argos/cli/lint_imports.py` (new), `argos/cli/__main__.py` (registered `lint-imports` subcommand), `argos/cli/tests/test_lint_imports.py` (new, 19 tests), `argos/cli/tests/fixtures/lint_imports/bad_import.py` (new fixture), `.claude/agents/verifier.md` + `argos/specs/v1.0/agents/verifier.md` (Semantic check #4 added — `argos lint-imports argos/`), `argos/specs/v1.0/tickets/ARG1-030-verifier-severity-rubric.md` (Amendment (ARG1-064) appendix per AC#8).
  - ACs: 10/10 met. AC#1 `lint-imports --help` exits 0; subcommand listed under INTERNAL_SUBCOMMANDS. AC#2 module imports only the AC#2 allowlist (argparse, ast, sys, pathlib, __future__). AC#3 `argos lint-imports argos/` exits 0 against this branch — current tree clean. AC#4 fixture emits canonical `lint-imports: bad_import.py:1: forbidden import requests`, exit 1. AC#5 missing path emits `lint-imports: /nonexistent/path: not found`, exit 1. AC#6 `STDLIB_ALLOWLIST` literal with ADR-001 docstring pointer — required minimum (argparse, re, dataclasses, pathlib, json, datetime, __future__, argos) present. AC#7 verifier rubric updated in both canonical and Claude Code mirror, byte-identical (`diff -q` exits 0), tool allowlist unchanged. AC#8 Amendment (ARG1-064) appended to ARG1-030 with prose, ARG1-010/ARG1-050 precedent citation, branch reference. AC#9 19 tests covering stdlib pass / single forbidden / ImportFrom / dotted internal / multiple violations / recursion / not-found. AC#10 `python3 -m unittest discover -s argos/cli/tests` → 229 tests, all OK (≥154).
  - Findings: 0 critical, 0 major, 0 minor.
  - Tests: `python3 -m unittest argos.cli.tests.test_lint_imports -v` → 19 tests, all OK (Ran 19 tests in 0.179s). Full sweep: `python3 -m unittest discover -s argos/cli/tests` → 229 tests, all OK (Ran 229 tests in 4.915s). Pre-flight: `python3 -m argos.cli lint-imports argos/` exits 0.
  - Sibling: ARG1-032 holds the pre-commit-hook scope (file-disjoint per dispatch plan); this ticket is verifier-rubric enforcement only, no CI/hook surface touched.
  - Decision: pass
<!-- /argos:entry -->


<!-- argos:entry id=2026-05-03T17:24:16Z-ARG1-022-done ticket=ARG1-022 author=verifier session=arg1-022-worktree -->
- **[2026-05-03T17:30:00Z] ARG1-022 — verified** (worktree `argos-v1-arg1-022`, branch `ticket/ARG1-022`)
  - Files changed: `argos/cli/orchestrator/dispatch.py` (new — `DispatchEntry` / `DispatchPlan` / `SessionOutcome` / `BatchResult` / `SessionRequest` dataclasses; `plan_dispatch` / `render_dry_run_table` / `dispatch_batch` / `default_session_runner` / `default_repo_root` / `default_short_sha`), `argos/cli/commands/orchestrate.py` (rewrite — real dispatch added, `--dry-run` upgraded to emit AC#6 markdown table when plans exist, fallback to id-list when not, `--epic` / `--ticket-dir` / `--max-parallel` flags; reads `orchestrator.max_parallel` from config), `argos/cli/tests/test_parallel_dispatch.py` (new — 19 tests across 6 classes), `argos/cli/tests/test_orchestrate.py` (one prior placeholder test renamed `test_no_dry_run_rejected` → `test_no_dry_run_without_epic_rejected` to match new `--epic` requirement; all other tests untouched), `argos/specs/v1.0/tickets/ARG1-022-parallel-dispatch.md` (Plan + Verification appended).
  - ACs: 6/6 met. AC#1 live harness peak=3 concurrent `claude` PIDs (`ps -eo command` poll at 50 ms while orchestrate runs three sleep-1.5s sessions, max_parallel=3). AC#2 live harness wall=3.136s ≥ threshold 2.85s = 3 × 1.0s × 0.95. AC#3 live dispatch-log timestamps prove dependent (911,912) serialized + independent (913) overlaps with first dependent (911 dispatch=17:22:42Z, 913 dispatch=17:22:42Z, 912 dispatch=17:22:43Z). AC#4 stdout contains literal `independence detection failed; falling back to serial`. AC#5 4 worktrees post-dispatch = 1 main + 3 dispatched, no orphans. AC#6 `argos orchestrate --batch-size 5 --dry-run` emits canonical markdown table with `ticket_id | group | dispatch_order | parallel_with` columns.
  - Findings: 0 critical, 0 major, 0 minor.
  - Tests: `python3 -m unittest argos.cli.tests.test_parallel_dispatch -v` → 19 tests, all OK (Ran 19 tests in 4.114s). Full sweep: `python3 -m unittest discover -s argos/cli/tests` → 248 tests, all OK (Ran 248 tests in 9.670s). Pre-flight: `python3 -m argos.cli lint-imports argos/` → exit 0. Stdlib-only preserved (new imports limited to `subprocess`, `threading`, `os` — all in the ARG1-064 allowlist); ADR-001 + ADR-002 contracts intact. `pyproject.toml` unchanged.
  - Architectural choices (Q1–Q5 from session brief): (1) subprocess-managed concurrency via `threading.Thread` + `threading.Semaphore(max_parallel)` because `concurrent.futures` is not allowlisted; (2) partial-batch failure — option (a), peers continue, each outcome logged independently; auto-fix retry is ARG1-013's scope; (3) ARG1-032 pre-commit hook does not interact — dispatcher writes only to `argos/specs/dispatch/{epic}/{ticket}.md` via ARG1-012's writer, never STATE.md; (4) one-group-at-a-time hard barrier, no cross-group pipelining; (5) strict criterion consumed verbatim from `independence.partition` — false-serializations are ARG1-066's scope, no workarounds shipped.
  - Sibling: ARG1-066 (queued behind Layer 2) replaces strict file-set disjointness with dynamic dry-run merge per ESC-ARG1-021. ARG1-013 (auto-fix retry), ARG1-023 (worktree merge/preserve), and ARG1-054 (cycle close) all build on this dispatcher's BatchResult / dispatch-log surface.
  - Decision: pass
<!-- /argos:entry -->


<!-- argos:entry id=2026-05-03T18:05:43Z-ARG1-023 ticket=ARG1-023 author=verifier session=arg1-023-worktree -->
- **[2026-05-03T18:10:00Z] ARG1-023 — verified** (worktree `argos-v1-arg1-023`, branch `ticket/ARG1-023`)
  - Files changed: `argos/cli/orchestrator/merge.py` (new), `argos/cli/commands/worktree_finalize.py` (new), `argos/cli/__main__.py` (registered `worktree-finalize` subcommand), `argos/cli/tests/test_worktree_finalize.py` (new), `argos/specs/v1.0/tickets/ARG1-023-worktree-merge-preserve.md` (Plan + Verification appended).
  - ACs: 6/6 met. AC#1 ff merge: `git log --oneline main..argos/ARG1-099` empty after `worktree-finalize --result pass`. AC#2 three-way: first-parent log on main starts with `Merge branch 'argos/ARG1-099'`. AC#3 conflict: exit 1, `git merge --abort` cleared MERGE_HEAD, `argos/specs/escalations/ARG1-099-*.md` exists with `severity: blocking` and body containing `merge conflict`. AC#4 fail: exit 0, worktree dir + branch both preserved. AC#5 pass-with-minors: identical merge behavior to pass. AC#6 `--json` emits all four required keys (`merged`, `merge_strategy`, `conflicts`, `worktree_preserved`).
  - Empirical confirmation: ARG1-032 pre-commit hook accepts the three-way auto-merge commit when STATE.md changes on both sides are verifier-author argos:entry blocks (the ARG1-052 merge driver produces a clean union; no bypass needed).
  - Architectural choices Q1–Q4: single-ticket primitive (Q1); always preserve on fail (Q2); abort + blocking escalation (Q3); no `--dry-run`, `--json` covers programmatic inspection (Q4).
  - Findings: 0 critical, 0 major, 0 minor.
  - Tests: `python3 -m unittest argos.cli.tests.test_worktree_finalize -v` → 12 tests, all OK (Ran 12 tests in 0.62s). Full suite: `python3 -m unittest discover -s argos/cli/tests` → 260 tests, all OK (Ran 260 tests in 9.70s). Zero regressions. Lint: `python3 -m argos.cli lint-imports argos/` exits 0.
  - Decision: pass
<!-- /argos:entry -->


<!-- argos:entry id=2026-05-03T18:30:10Z-ARG1-067-done ticket=ARG1-067 author=verifier session=arg1-067 -->
- **[2026-05-03T00:00:00Z] ARG1-067 — `test_dry_run_lists_queue` updated for ARG1-022 markdown table format** (worktree `argos-v1-arg1-067`, branch `ticket/ARG1-067`)
  - Files changed: `argos/cli/tests/test_orchestrate.py` (only `test_dry_run_lists_queue`; pinned `--ticket-dir` to a tempdir with synthetic ARG1-022/ARG1-013/ARG1-023 frontmatter, replaced flat-id-list assertion with structural assertions over the AC#6 markdown table — header row with `ticket_id` / `group` / `dispatch_order` / `parallel_with`, plus three data rows whose `ticket_id` cell matches and `group` / `dispatch_order` cells are non-empty).
  - ACs: 6/6 met. AC#1 `python3 -m unittest argos.cli.tests.test_orchestrate.OrchestrateCLITests.test_dry_run_lists_queue` exits 0. AC#2 header row + per-ticket data row asserted; group/dispatch_order asserted non-empty (no specific values), so independence-detector internals (group numbers, dispatch order, parallel siblings) stay decoupled from the test. AC#3 `--ticket-dir` pinned to `tempdir/tickets/` containing `ARG1-022.md` / `ARG1-013.md` / `ARG1-023.md` with disjoint `files_touched:` lists; mirrors the pinning pattern of `test_dry_run_batch_size_caps_output` and `test_dry_run_batch_size_larger_than_queue`. AC#4 `python3 -m unittest discover -s argos/cli/tests` → 279 tests OK, count unchanged from main. AC#5 `python3 -m argos.cli lint-imports argos/` exit 0. AC#6 `git diff main -- argos/cli/tests/test_orchestrate.py` shows changes only to `test_dry_run_lists_queue` plus its synthetic-ticket fixture lines; no library code touched (`parse_queue_file`, `orchestrate.py`, `dispatch.py` untouched).
  - Unblocks ARG1-054 (cycle close) — the failing test was the last blocker on its merge gate.
<!-- /argos:entry -->


<!-- argos:entry id=2026-06-13T16:30:24Z-ARG1-068-done ticket=ARG1-068 author=verifier session=arg1-068-worktree -->
- **[2026-06-13T00:00:00Z] ARG1-068 — `argos sync --clean-queue` operator queue-cleanup primitive** (worktree `argos-v1-arg1-068`, branch `ticket/ARG1-068`)
  - Files changed: `argos/cli/commands/clean_queue.py` (new — `clean_queue()` library + `main()` shim, mirrors ARG1-054's cycle_close structural-edit discipline), `argos/cli/__main__.py` (modify — `sync --clean-queue` dispatch branch + `_STUB_TICKETS` comment), `argos/cli/tests/test_clean_queue.py` (new — 15 tests, hermetic temp-git-repo harness with the real ARG1-032 pre-commit hook), `argos/specs/v1.0/tickets/ARG1-068-queue-cleanup-after-merge.md` (Plan + Verification appended).
  - Subcommand name: `argos sync --clean-queue` (parallels `--close-cycle`).
  - Shipped-id source = live `## Done this cycle` ticket ids (exact-heading bound, suffixed historical archives excluded) ∪ `ticket=` ids across `argos/specs/cycles/*.md`. Removes exactly the matching `## Queue` bullets; unshipped bullets, placeholder, and blanks preserved verbatim.
  - ARGOS_CYCLE_CLOSE=1 bypass exported only on the single `git commit` subprocess (AC#4); `git add` + atomic `tempfile`+`os.replace` rewrite use unmodified env (AC#5). No-removal runs return None → idempotent (AC#3) and empty-queue no-op (AC#7).
  - ACs: 9/9 met. AC#8 `python3 -m unittest discover -s argos/cli/tests` → 304 tests OK (15 new). AC#9 `python3 -m argos.cli lint-imports argos/` → exit 0.
  - Did not touch `cycle_close.py`, the hook, or the orchestrator dispatch loop (ticket §Non-goals). Stdlib-only (ADR-001 / ADR-002).
  - Decision: pass
<!-- /argos:entry -->


<!-- argos:entry id=2026-06-13T20:36:39Z-ARG1-066-done ticket=ARG1-066 author=verifier session=arg1-066-worktree -->
- **[2026-06-13T10:00:00Z] ARG1-066 — verified** (worktree `argos-v1-arg1-066`, branch `ticket/ARG1-066`)
  - Replaces ARG1-021's strict file-set disjointness with merge-aware independence via dynamic dry-run `git merge --no-commit --no-ff` (both directions, throwaway staging worktree), per ratified decision ESC-ARG1-021. Strict criterion demoted to the degraded-but-correct fallback used when a pair's branches don't yet exist.
  - Files changed: `argos/cli/orchestrator/independence.py` (merge machinery + staging area + rewired criterion), `argos/cli/commands/independence.py` (CLI wires a shared staging area; surface unchanged), `argos/cli/tests/test_independence.py` (28→43 tests), `argos/cli/lint_imports.py` (+`atexit`,`signal` stdlib allowlist), `argos/specs/decisions/ADR-001-cli-language.md` (amendment trail for the two additions), `argos/specs/v1.0/ARCHITECTURE.md` §Independence detection (replaced), `argos/specs/v1.0/agents/orchestrator.md` + `.claude/agents/orchestrator.md` mirror §Parallel dispatch (replaced), `argos/specs/v1.0/tickets/ARG1-021-independence-detection.md` (`## Superseded by ARG1-066`), `argos/specs/v1.0/tickets/ARG1-066-merge-aware-independence.md` (Plan).
  - ACs: 12/12 met. AC#1 CLI surface (positional ids, `--json`, exit codes) unchanged — existing CLI tests pass verbatim. AC#2 per-pair staging worktree + bidirectional `--no-commit --no-ff` merge with guaranteed cleanup (context-manager + atexit + SIGINT/SIGTERM). AC#3 single reused warm worktree per run; depends_on short-circuits skip merges. AC#4 STATE.md dry-run exercises the real ARG1-052 driver (proved: same pair is dependent under default text merge, independent under the configured driver). AC#5 pre-commit hook never fires on `--no-commit` (sentinel-hook fixture). AC#6 registration-pattern pair (distinct line ranges) reported independent. AC#7 depends_on reported dependent with no merge run. AC#8 byte-equivalent parent `git status` + zero leaked worktrees after a run. AC#9 ARCHITECTURE.md + orchestrator.md replaced (not appended). AC#10 ARG1-021 supersession section. AC#11 43 ≥ 35 tests. AC#12 full sweep green.
  - Findings: 0 critical, 0 major, 0 minor.
  - Tests: `python3 -m unittest argos.cli.tests.test_independence` → 43 tests, OK. Full sweep `python3 -m unittest discover -s argos/cli/tests` → 319 tests, OK (was 304). `python3 -m argos.cli lint-imports argos/` exits 0.
  - Architectural choices (Q1–Q5): staging = one lazily-created `tempfile.mkdtemp` linked worktree outside the repo tree, reused across pairs, triple-guaranteed cleanup; hook avoidance via `--no-commit` (no commit → no commit-time hooks, empirically confirmed); merge-driver inherited because linked worktrees share `.git/config` and carry checked-out `.gitattributes`; depends_on checked first by set membership before any branch resolution; perf via worktree reuse. Enabling change: `atexit`/`signal` added to the ADR-001 stdlib allowlist (AC#2 mandates them) with a documented amendment-trail entry — stdlib-only, no third-party dependency.
  - Decision: pass
<!-- /argos:entry -->


<!-- argos:entry id=2026-06-13T21:47:08Z-ARG1-002 ticket=ARG1-002 author=verifier session=local-2026-06-13 -->
- **[2026-06-13] ARG1-002 — verified** (worktree `.argos/worktrees/ARG1-002-live`)
  - New: `argos/cli/commands/init.py`, `argos/cli/templates/` (5 scaffold sources copied as-is from ARG1-050/ARG1-053 templates), `argos/cli/tests/test_init.py`
  - Edited: `argos/cli/__main__.py` (dispatch `init` to the real impl; drop it from the stub table)
  - `argos init` scaffolds `argos/specs/{STATE,PRD,ARCHITECTURE}.md`, `argos/config.toml`, `.argos/local.toml`, ensures `.argos/` in `.gitignore`, registers the ARG1-052 STATE.md merge driver, installs the ARG1-032 pre-commit hook (best-effort), and is idempotent via a `.argos/.initialized` sentinel (`--force` re-scaffolds but never touches `argos/specs/tickets/`).
  - AC harness: `python3 -m unittest argos.cli.tests.test_init` → 8 pass, 0 fail. All 7 acceptance criteria verified end-to-end in a fresh `mktemp -d`. Regression: full `argos/cli/tests` suite 341 pass. `lint-imports` clean (ADR-001 stdlib-only; no dep adds).
  - Findings: 0 critical, 0 major, 0 minor. Decision: pass
<!-- /argos:entry -->


<!-- argos:entry id=2026-06-14T00:54:09Z-ARG1-004 ticket=ARG1-004 author=verifier session=arg1-004-worktree -->
- **[2026-06-13] ARG1-004 — verified** (autonomous session, worktree `ARG1-004-c5f1c8c`, branch `argos/ARG1-004`)
  - Files added: `argos/cli/reconcile.py`, `argos/cli/commands/sync.py`, `argos/cli/tests/test_sync.py`
  - Files edited: `argos/cli/__main__.py` (route `sync` to the full command), `argos/specs/v1.0/tickets/ARG1-004-argos-sync.md` (Plan section)
  - `argos sync` implements three reconciliations — ticket↔Issue re-render (network, `--no-issues`/gh-unavailable skips), STATE↔git first-parent check (mismatch → exit 1, no auto-fix), `.argos/worktrees/` prune (merged + deleted-on-origin) — plus `--close-cycle`/`--clean-queue` delegation.
  - ACs: 5/5 verified live via the `argos` launcher. AC#1 `sync --dry-run` exit 0, three phases OK/WOULD-FIX/MISMATCH. AC#2 merged+origin-deleted worktree pruned, gone from `git worktree list`. AC#3 done-this-cycle ticket without a main merge commit → exit 1, stderr names ticket id + `git log --first-parent main`. AC#4 `sync --close-cycle` archived 1 block, exit 0; idempotent re-run exit 0. AC#5 `sync --no-issues` with a PATH-shadow `gh` sentinel made zero gh invocations.
  - Tests: `python3 -m unittest argos.cli.tests.test_sync -v` → 21 tests OK. Regression: `python3 -m unittest discover -s argos/cli/tests` → 362 tests OK. `argos lint-imports` clean on all three new files (rc=0); stdlib only, no deps added (ADR-001/002).
  - Findings: 0 critical, 0 major, 0 minor.
  - Decision: pass
<!-- /argos:entry -->

## Known drift

<!-- argos:entry id=2026-04-26T00:00:00Z-ARG1-030-shim ticket=ARG1-030 author=verifier session=arg1-030-worktree -->
- **`argos/cli/argos` is a temporary bash shim**, not the real CLI binary. Implements only the `verifier-parse` subcommand to satisfy ARG1-030 AC#5 without prejudicing ARG1-001's CLI design. Disposition: ARG1-001 replaces this file with the real `argos` binary; the shim's TODO comment names that ticket.
- **`argos/__init__.py`, `argos/cli/__init__.py`, `argos/cli/tests/__init__.py`** turn the `argos/` directory into a Python package alongside its existing role as a docs tree (`argos/specs/`, `argos/RULES.md`, `argos/scripts/`). Disposition: revisit during ARG1-001 — the CLI ticket should decide whether the package layout stays under `argos/cli/` or moves to a dedicated `src/` layout; if it moves, the init files here are deleted.
<!-- /argos:entry -->

<!-- argos:entry id=2026-04-26T23:07:49Z-ARG1-053-ac7 ticket=ARG1-053 author=verifier session=arg1-053-worktree -->
- **ARG1-053 AC#7 wording is incompatible with AC#1 as written.** AC#7 requires `.gitignore` to contain the literal line `.argos/` (verified by `grep -Fxq '.argos/'` exit 0 and `grep -Fc '.argos/'` returning `1`). AC#1 requires `.argos/local.toml.template` to exist on a fresh checkout. Git's gitignore precedence rule ("It is not possible to re-include a file if a parent directory of that file is excluded") makes these mutually exclusive: a literal `.argos/` line ignores the directory wholesale and prevents the template from ever being tracked. The shipped fix changes line 3 of `.gitignore` from `.argos/` to `.argos/*` and adds `!.argos/local.toml.template` on line 4 — runtime content under `.argos/` (worktrees, scratch state) remains ignored, only the template is re-included. AC#7's *intent* (no duplicate runtime ignore for `.argos/`, idempotent across `argos init` re-runs) is preserved. Disposition: file follow-up ticket ARG1-NNN to revise AC#7 wording from `grep -Fxq '.argos/'` to a check that accepts either `.argos/` or `.argos/*` and that ignores any negation lines in the count. Until that ticket lands, ARG1-053's verifier output records AC#7 as `partial` (1 major finding) and the decision as `pass-with-minors`.
<!-- /argos:entry -->

<!-- argos:entry id=2026-04-26T15:45:00Z-ARG1-001 ticket=ARG1-001 author=verifier session=arg1-001-worktree -->
- **[2026-04-26T15:45:00Z] ARG1-001 — verified** (worktree `argos-v1-arg1-001`, branch `ticket/ARG1-001`)
  - Files changed: `argos/specs/decisions/ADR-001-cli-language.md` (new), `pyproject.toml` (new), `argos/cli/__init__.py` (added `__version__`), `argos/cli/__main__.py` (replaced minimal dispatcher with unified argparse-free dispatcher: `--version`, `--help`, four public stubs `init/sync/status/attend`, three internal delegates `state-parse/verifier-parse/escalation-validate`), `argos/cli/argos` (rewritten from bash shim to Python launcher), `argos/cli/tests/test_version.py` (new), `argos/specs/v1.0/tickets/ARG1-001-cli-binary-scaffold.md` (Plan section appended).
  - ADR-001 ratifies Python (≥3.9, stdlib-only, `pyproject.toml`/PEP-621 manifest) as the CLI implementation language. Floor 3.9 reasoned by PEP 585 builtin-generic annotations; explicitly NOT 3.10. ADR-001 explicitly does NOT close PRD §Distribution packaging-channel TODO — that decision is deferred to a follow-up ADR (ADR-NNN-packaging-channel) required before any 1.0.0 release.
  - ACs: 5/5 met. AC#1 ADR file present, Status `Accepted`, names Python + rejected alternatives (Rust/Go/Bash). AC#2 `argos --version` exits 0; stdout `argos 0.1.0` matches `^argos [0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?$`. AC#3 `argos --help` exits 0; stdout contains `init`, `sync`, `status`, `attend`. AC#4 `argos` (no args) exits 2; stderr contains `usage:`. AC#5 `argos nonexistent-subcommand` exits 2; stderr `argos: unknown subcommand: nonexistent-subcommand`.
  - Findings: 0 critical, 0 major, 0 minor.
  - Tests: `python3 -m unittest argos.cli.tests.test_version argos.cli.tests.test_verifier_parser argos.cli.tests.test_escalation_validator -v` → 15 tests, all OK (Ran 15 tests in 0.121s). Pre-existing `argos.cli.tests.test_state_parser` is gated on `pytest` from ARG1-050 and unchanged by this ticket.
  - Drift closed: STATE.md drift entry id=`2026-04-26T00:00:00Z-ARG1-030-shim` is resolved by this ticket — `argos/cli/argos` is now the real Python launcher and the `argos/cli/__init__.py` package layout is ratified by ADR-001.
  - Decision: pass
<!-- /argos:entry -->


<!-- argos:entry id=2026-04-29T19:59:59Z-ARG1-010 ticket=ARG1-010 author=coder session=arg1-057-drain -->
- **ARG1-010 AC#3 was satisfied via system `python3` + `pyyaml`, not via a portable AC harness.** ADR-002 ratifies stdlib-only AC tooling and pins the substitute pattern (`argos frontmatter-parse`). Disposition: ARG1-059 retrofits the AC; ARG1-010's shipped output files are not affected, only the AC text in the ticket file changes. Until ARG1-059 lands, AC#3 should be treated as provisionally satisfied.
<!-- /argos:entry -->


<!-- argos:entry id=2026-04-29T21:17:11Z-ARG1-010-drift-resolved ticket=ARG1-010 author=verifier session=arg1-059-worktree -->
- **ARG1-010 AC#3 drift resolved by ARG1-059.** The earlier provisional disposition (`STATE.md` Known-drift entry id `2026-04-29T19:59:59Z-ARG1-010` from commit `c5c0c20`) noted that AC#3 had been satisfied via system `python3` + `pyyaml` rather than via a portable AC harness. ARG1-059 retrofitted AC#3 to invoke `argos frontmatter-parse` (the stdlib substitute pinned by ADR-002), and the retrofitted command was re-run on the ARG1-059 branch against the current `.claude/agents/orchestrator.md` and exits 0. AC#3 is now satisfied via stdlib-only AC tooling end-to-end; the foot-gun cannot recur. Disposition: closed.
<!-- /argos:entry -->

## Done this cycle (ARG1-001)

<!-- argos:entry id=2026-04-26T15:45:00Z-ARG1-001-done ticket=ARG1-001 author=verifier session=arg1-001-worktree -->
- **[2026-04-26T15:45:00Z] ARG1-001 — completed** (CLI binary scaffold + ADR-001).
  - Public CLI surface (`argos init / sync / status / attend`) registered as stubs; bodies tracked by ARG1-002 / ARG1-004 / ARG1-003 / ARG1-005.
  - Internal subcommands (`state-parse`, `verifier-parse`, `escalation-validate`) routed through unified dispatcher; existing module entry points and tests untouched.
  - `pyproject.toml` declares zero runtime dependencies (stdlib-only contract per ADR-001). Console-script entry point registered for future `pip install` / `pipx install` flows.
  - Decision: pass
<!-- /argos:entry -->

<!-- argos:entry id=2026-04-26T16:30:00Z-ARG1-052 ticket=ARG1-052 author=verifier session=arg1-052-worktree -->
- **[2026-04-26T16:30:00Z] ARG1-052 — verified** (worktree `argos-v1-arg1-052`, branch `ticket/ARG1-052`)
  - Files changed: `argos/scripts/state-merge-driver.sh` (new, POSIX `/bin/sh` + awk merge driver), `argos/scripts/install-merge-driver.sh` (new, idempotent installer), `argos/scripts/tests/test_merge_driver.sh` (new, hermetic POSIX test harness), `.gitattributes` (new, two lines registering the driver for `argos/specs/v1.0/STATE.md` and `argos/specs/STATE.md`), `argos/specs/v1.0/tickets/ARG1-052-state-merge-driver.md` (Plan + Verification sections appended).
  - ACs: 7/7 met (decomposed into 11 sub-checks, all PASS). AC#1 installer registers `merge.argos-state.driver = argos/scripts/state-merge-driver.sh %O %A %B %P %L`. AC#2 `.gitattributes` contains both literal `argos/specs/STATE.md merge=argos-state` and the v1.0 path line. AC#3 two-branch parallel-block merge yields exit 0, two blocks present, no `<<<<<<<` markers. AC#4 same-id collision deduped to exactly one block. AC#5 body-modified violation exits non-zero with stderr containing `block body modified — append-only violated` and the offending id `2026-04-26T13:00:00Z-ARG-MOD`. AC#6 `python3 -m argos.cli state-parse <merged-fixture>` exits 0 (uses ARG1-050 reference parser; full JSON round-trip verified). AC#7 1000-block merge measured at 35–44 ms (≥25× under the 1.0 s budget) after refactoring the per-block awk loop into a single NR==FNR awk pass per side.
  - Findings: 0 critical, 0 major, 0 minor.
  - Tests: `sh argos/scripts/tests/test_merge_driver.sh` → `11 pass, 0 fail, 0 warn` (exit 0).
  - Decision: pass
<!-- /argos:entry -->

<!-- argos:entry id=2026-04-26T16:30:00Z-ARG1-052-drift ticket=ARG1-052 author=verifier session=arg1-052-worktree -->
- **Driver does not merge non-block prose between `%A` and `%B`.** The emission algorithm preserves `%O`'s base-file prose verbatim and appends each side's new blocks. Under the verifier-only-writer + append-only invariant this is correct, but a human hand-edit to base prose on one side concurrently with a verifier-appended block on the other side would be silently lost (the driver would emit `%O`'s prose and overwrite the human edit). Disposition: tracked as a known drift candidate; mitigation is a shell-equality preflight check that exits non-zero on prose divergence outside argos:entry blocks. Not blocking ARG1-052; file a follow-up if dogfooding surfaces the case.
<!-- /argos:entry -->

<!-- argos:entry id=2026-04-26T23:07:49Z-ARG1-053 ticket=ARG1-053 author=verifier session=arg1-053-worktree -->
- **[2026-04-26T23:07:49Z] ARG1-053 — verified** (worktree `argos-v1-arg1-053`, branch `ticket/ARG1-053`)
  - Files changed: `argos/config.toml.template` (new), `.argos/local.toml.template` (new), `argos/cli/config.py` (new — loader + `ensure_gitignore_entry` helper), `argos/cli/commands/config.py` (new — `get`/`validate` subcommands), `argos/cli/_config_schema.py` (new — `KNOWN_KEYS` table mirrored from schema doc), `argos/specs/v1.0/schemas/config.md` (new), `argos/cli/tests/test_config.py` (new — 29 tests across 7 classes), `argos/cli/__main__.py` (Plan-authorized: `"config"` added to `PUBLIC_SUBCOMMANDS`, dispatch branch added bypassing `_stub`), `.gitignore` (post-verify drift fix: `.argos/` → `.argos/*` + `!.argos/local.toml.template` so the template can be tracked while runtime `.argos/` content stays ignored), `argos/specs/v1.0/tickets/ARG1-053-config-split.md` (Plan + Implementation notes).
  - TOML strategy: `tomllib` gated by `sys.version_info >= (3, 11)` at `argos/cli/config.py:255`; in-house regex parser for 3.9/3.10 raises `ConfigParseError` on arrays / inline tables / multi-line strings. ADR-001 stdlib-only contract preserved (no `tomli`, no `pyproject.toml` dep changes).
  - ACs: 9/10 met, 1 partial. AC#1–#6, #8–#10 met. AC#7 partial: original literal `grep -Fxq '.argos/' .gitignore` no longer matches because the line is now `.argos/*` (required to make the negation rule for `local.toml.template` effective; Git's directory-ignore precedence prevents re-inclusion otherwise). AC#7's *intent* (no duplicate runtime ignore for `.argos/`) is preserved — `.argos/*` still ignores all runtime content.
  - Findings: 0 critical, 1 major (AC#7 literal-grep wording vs. AC#1 template-shipping requirement — irreconcilable as written), 0 minor.
  - Tests: `python3 -m unittest argos.cli.tests.test_config -v` → 29 tests, all OK (Ran 29 tests in 0.139s). Regression: `python3 -m unittest argos.cli.tests.test_version argos.cli.tests.test_verifier_parser argos.cli.tests.test_escalation_validator -v` → 15 tests, all OK.
  - Decision: pass-with-minors (AC#7 wording fix tracked as known drift below; intent satisfied, follow-up ticket required).
<!-- /argos:entry -->

<!-- argos:entry id=2026-04-26T23:07:49Z-ARG1-053-done ticket=ARG1-053 author=verifier session=arg1-053-worktree -->
- **[2026-04-26T23:07:49Z] ARG1-053 — completed** (config split: project + local TOML templates, loader, `argos config get/validate` subcommand, schema doc).
  - `argos/config.toml.template` ships project defaults (6 AC#2 keys + `orchestrator.dry_plan_cache`); `verifier.minor_lint_rules` deferred to ARG1-013 as commented array.
  - `.argos/local.toml.template` ships per-developer defaults (4 AC#3 keys + `operator.email`, `harness.session_timeout_seconds` as commented examples).
  - Loader: `argos.cli.config.load(...)` reads project + local, applies local-overrides-project, warns on unknown keys without failing.
  - Hybrid TOML parser: `tomllib` on 3.11+, in-house regex parser on 3.9/3.10 — both yield identical dicts (`tomllib` is the test-time oracle).
  - `argos config get <dotted.key>` and `argos config validate` wired into the unified dispatcher at `argos/cli/__main__.py`.
  - Decision: pass-with-minors
<!-- /argos:entry -->
<!-- argos:entry id=2026-04-29T20:53:39Z-ARG1-060 ticket=ARG1-060 author=verifier session=arg1-060-worktree -->
- **[2026-04-29T21:00:00Z] ARG1-060 — `argos frontmatter-parse` subcommand verified** (worktree `argos-v1-arg1-060`, branch `ticket/ARG1-060`)
  - Files changed: `argos/cli/frontmatter_parser.py` (new — ~330 lines, stdlib-only YAML-subset parser implementing ADR-002 §3 grammar and §4 rejection contract); `argos/cli/commands/frontmatter_parse.py` (new — thin shim parallel to `state_parse`); `argos/cli/__main__.py` (modify — added `frontmatter-parse` to `INTERNAL_SUBCOMMANDS`, dispatch branch, help line); `argos/cli/tests/test_frontmatter_parser.py` (new — 25 tests across 8 classes); `argos/cli/tests/fixtures/frontmatter/{flow-seq,flow-map,multiline-pipe,nested-deep,anchor,alias,tag,non-utf8,good-quoted,good-comments}.md` (new — one fixture per rejection AC plus two happy-path fixtures).
  - ACs: 16/16 met. AC#1 stdlib-only verified by `StdlibOnlyTests.test_module_imports_only_permitted_stdlib` (parses every `import`/`from` line; only `__future__` plus the eight permitted modules appear; `__future__` is sanctioned by ADR-001 §Decision item 1 as the project pattern). AC#2 / AC#3 round-trip the live shipped `orchestrator.md` and `verifier.md` frontmatter via the CLI; JSON contains all required keys, `allowed_tools` and `denied_paths` are arrays. AC#4 (the load-bearing test): the brace-glob `"**/*.{ts,tsx,js,jsx,py,...}"` quoted scalar in `denied_paths` round-trips verbatim through both CLI and library API. AC#5 leading + trailing comments are no-ops. AC#6–#13 every rejected feature exits 2 with `frontmatter-parse: line N: <reason>` matching the ADR-002 §4 contract. AC#14 missing file exits 1. AC#15 subcommand visible in `argos --help`; `argos frontmatter-parse --help` exits 0 with usage. AC#16 test suite passes (25 tests). AC#17 regression: `test_version test_state_append test_verifier_parser test_escalation_validator test_config` → 64/64 pass.
  - Tests: `python3 -m unittest argos.cli.tests.test_frontmatter_parser -v` → 25 OK; regression sweep → 64 OK; combined 89/89.
  - Stdlib-only preserved (no new imports beyond `re`, `sys`, `json`, `pathlib`, `argparse`, `dataclasses`, `typing`, plus `__future__`); ADR-001 + ADR-002 contracts intact. No third-party deps added; `pyproject.toml` unchanged.
  - Layer 2 unblocked. ARG1-059 (retrofit ARG1-010 / ARG1-012 ACs to invoke `argos frontmatter-parse`) is now ready to dispatch.
  - Decision: pass
<!-- /argos:entry -->

<!-- argos:entry id=2026-04-29T20:57:41Z-ARG1-062 ticket=ARG1-062 author=coder session=arg1-062-worktree -->
- **[2026-04-29T21:30:00Z] ARG1-062 — clarified ARG1-060 AC#1 stdlib import allowlist** (worktree `argos-v1-arg1-062`, branch `ticket/ARG1-062`)
  - Files changed: `argos/specs/v1.0/tickets/ARG1-060-frontmatter-parse-subcommand.md` (AC#1 only — added `__future__` to the permitted-imports list with a one-line ADR-001 §Decision item 1 citation noting the clarification was implicit and shipped `StdlibOnlyTests` already treated it as permitted).
  - Audit: ARG1-059's ticket text does not enumerate a permitted-import allowlist; only ARG1-060 has the AC#1 pattern. Single-file edit.
  - Out of scope: no code changes to `argos frontmatter-parse`; no test changes (the existing `StdlibOnlyTests.test_module_imports_only_permitted_stdlib` is correct as written and continues to pass); no ADR-001 amendment (ADR-001 already endorses `__future__`; the gap was downstream in ticket prose only).
  - This corrects ARG1-060's shipped ticket text; ARG1-060's commit (562fc69) and the shipped frontmatter_parser module are unaffected.
  - Decision: pass
<!-- /argos:entry -->

<!-- argos:entry id=2026-04-30T16:33:29Z-ARG1-031-verify ticket=ARG1-031 author=verifier session=arg1-031-worktree -->
- **[2026-04-30T16:32:19Z] ARG1-031 — verified** (session arg1-031-worktree, worktree `argos-v1-arg1-031`, branch `ticket/ARG1-031`)
  - Files changed: `argos/cli/verifier_writeback.py` (new — stdlib-only wrapper that translates a `<!-- argos:verifier-output -->` block into a STATE.md body and routes it through `argos state-append`), `argos/cli/__main__.py` (registered `verifier-writeback` in `INTERNAL_SUBCOMMANDS`, help text, dispatch chain, docstring), `.claude/agents/verifier.md` (added `## STATE.md write — through the helper, never by hand` section directing the verifier to invoke `argos state-append` via the writeback wrapper), `argos/specs/v1.0/agents/verifier.md` (byte-identical mirror), `argos/cli/tests/test_verifier_writeback.py` (new — 9 tests across `FormatBodyTests` + `WritebackCLITests`), `argos/specs/v1.0/tickets/ARG1-031-verifier-writes-structured-decision.md` (Plan + Verification sections).
  - ACs: 6/6 met. AC#1 pass case writes a `<!-- argos:entry ... author=verifier ... -->` block containing `ARG1-031` and the literal `verified`. AC#2 `pass-with-minors` with two minor findings emits `verified-with-minors`, both `file:line` refs, and `0 critical, 0 major, 2 minor`. AC#3 `fail` with `--stdout-file` embeds the verbatim test stdout fragment under a fenced `Test stdout:` block (`grep -Fc 'AssertionError: expected 0, got None'` = 2). AC#4 verifier's tool allowlist is `Read, Bash, Grep, Glob` — no Edit/Write; wrapper module imports only `append_block` for STATE.md writes. AC#5 `grep -Fc 'argos state-append' .claude/agents/verifier.md` = 4; mirror diff exits 0. AC#6 two concurrent `verifier-writeback` calls (different tickets) both append; 21 ids parsed, all unique; `argos state-parse` round-trips clean.
  - Findings: 0 critical, 0 major, 0 minor.
  - Tests: `python3 -m unittest argos.cli.tests.test_verifier_writeback -v` → 9 tests, all OK. Regression: `test_state_append test_verifier_parser test_frontmatter_parser test_escalation_validator test_version test_config test_verifier_writeback` → 98 tests, all OK. ADR-001 stdlib-only contract preserved (wrapper imports only `argparse`, `json`, `sys`, `pathlib`, `datetime` plus project modules); ADR-002 AC tooling stdlib-only (`grep -F`/`grep -E` + `python3 -c 'import json,sys; ...'` only).
  - This block was written via `argos state-append --suffix verify`, dogfooding the helper. The merge driver reconciles concurrent appends with sibling tickets ARG1-020 / ARG1-041.
  - Decision: pass
<!-- /argos:entry -->

<!-- argos:entry id=2026-04-30T16:51:07Z-ARG1-041-escalate-writer ticket=ARG1-041 author=verifier session=arg1-041-worktree -->
- **[2026-04-30T16:46:49Z] ARG1-041 — `argos escalate` writer + optional webhook** (worktree `argos-v1-arg1-041`, branch `ticket/ARG1-041`)
  - Files changed: `argos/cli/escalation.py` (new), `argos/cli/commands/escalate.py` (new), `argos/cli/tests/fixtures/__init__.py` (new), `argos/cli/tests/fixtures/test_webhook_server.py` (new), `argos/cli/tests/test_escalate.py` (new), `argos/cli/__main__.py` (registered `escalate` subcommand: `PUBLIC_SUBCOMMANDS` tuple, `--help` text, dispatcher branch), `argos/specs/v1.0/tickets/ARG1-041-escalation-writer-webhook.md` (Plan + Implementation notes + Verification appended).
  - ACs: 7/7 met. AC#1 `argos escalate --ticket ARG1-099 --severity blocking --raised-by orchestrator --body 'test'` exits 0; the resulting file matches `ARG1-099-*.md` and `argos escalation-validate` exits 0. AC#2 webhook URL empty → recording loopback server captures zero requests after the run. AC#3 webhook URL set → exactly one POST with JSON keys `{ticket_id, severity, summary, file_path}`. AC#4 server returns 500 → exit 0, stderr contains `webhook delivery failed: 500`. AC#5 closed-port URL → exit 0 in well under 5s (urllib timeout 4.0s; ECONNREFUSED returns immediately); stderr contains `webhook delivery failed`. AC#6 `--severity invalid` → exit 2, stderr `severity must be blocking or advisory`. AC#7 two concurrent threads invoking the CLI produce two distinct files (collision tiebreaker is a 4-hex random filename suffix added under `os.O_CREAT | os.O_EXCL`); both validate.
  - Findings: 0 critical, 0 major, 0 minor.
  - Tests: `python3 -m unittest argos.cli.tests.test_escalate -v` → 18 tests, all OK (Ran 18 tests in 1.819s). Regression sweep across `test_version test_verifier_parser test_escalation_validator test_state_append test_config test_frontmatter_parser test_escalate` → 107 tests, all OK (Ran 107 tests in 3.780s).
  - Stdlib-only preserved: webhook transport is `urllib.request` (no `requests`); config loaded via the ARG1-053 loader. No `pyproject.toml` change. ADR-001 + ADR-002 contracts intact.
  - Webhook auth: NONE. ARCHITECTURE.md §Technology choices line 252 explicit; config schema has no auth-related key; ticket Non-goals reaffirms. The `post_webhook` function is the choke point if a future ADR adds signed payloads.
  - Layer 2 sibling coordination: only `argos/cli/__main__.py` is shared with ARG1-020 / ARG1-031. Three localized edits, "keep both registrations" merge pattern; subcommand names disjoint.
  - Decision: pass
<!-- /argos:entry -->

<!-- argos:entry id=2026-04-30T16:15:51Z-ARG1-020-done ticket=ARG1-020 author=verifier session=arg1-020-worktree -->
- **[2026-04-30T00:00:00Z] ARG1-020 — verified** (worktree `argos-v1-arg1-020`, branch `ticket/ARG1-020`)
  - Files changed: `argos/cli/worktree.py` (new — library: `compute_branch_name`, `find_repo_root`, `validate_worktree_path`, `worktree_path_listed`, `add_worktree`, `resolve_harness_binary`, `spawn_session`, plus typed exception classes), `argos/cli/commands/run_session.py` (new — argparse shim mapping library exceptions to AC stderr substrings; loads `harness.claude_code_binary` via ARG1-053 config best-effort), `argos/cli/__main__.py` (modify — registered `run-session` in `INTERNAL_SUBCOMMANDS`, dispatch branch, help line), `argos/cli/tests/test_run_session.py` (new — 19 tests across 3 classes), `argos/specs/v1.0/tickets/ARG1-020-worktree-spawn-helper.md` (Plan + Verification sections appended).
  - ACs: 6/6 met (verified live in a hermetic temp git repo with `ARGOS_RUN_SESSION_HARNESS_BIN=/bin/true`). AC#1 `--dry-run` exits 0 with `branch: argos/ARG1-099` and absolute worktree path on stdout. AC#2 real run; `git worktree list` shows `ARG1-099-test`; `git branch --list argos/ARG1-099` non-empty. AC#3 worktree directory survives session exit (no auto-cleanup). AC#4 second dispatch exits 1 with `run-session: worktree already exists: <path>` on stderr; threaded concurrent-launch test confirms exactly one winner. AC#5 `/tmp/foo` exits 2 with `worktree must live under .argos/worktrees/`; relative paths outside `.argos/worktrees/` (`src/foo`) likewise rejected. AC#6 `--debug-print-cwd` prints exactly the absolute worktree path (not the repo root) and returns 0 without spawning the harness binary; regression test confirms the harness child observes `pwd == <worktree>` plus `ARGOS_TICKET` / `ARGOS_EPIC` / `ARGOS_WORKTREE` env vars.
  - Findings: 0 critical, 0 major, 0 minor.
  - Tests: `python3 -m unittest argos.cli.tests.test_run_session -v` → 19 tests, all OK (Ran 19 tests in 0.478s). Regression sweep: `test_version test_verifier_parser test_escalation_validator test_state_append test_frontmatter_parser test_config test_run_session` → 108/108 OK. Stdlib-only preserved; `pyproject.toml` unchanged.
  - Library / shim split mirrors ARG1-051's pattern so the orchestrator (ARG1-022) can call `argos.cli.worktree` primitives in-process without spawning a subprocess. Harness binary resolution order: `ARGOS_RUN_SESSION_HARNESS_BIN` env override → ARG1-053 `harness.claude_code_binary` → `claude` on PATH. Three context env vars (`ARGOS_TICKET`, `ARGOS_EPIC`, `ARGOS_WORKTREE`) exported to the spawned child so downstream tooling does not have to re-parse argv.
  - Out of scope confirmed: no independence detection (ARG1-021), no parallel orchestration (ARG1-022), no merge-on-pass / three-way merge / pruning (ARG1-023). The argv used to load the planner subagent inside Claude Code is intentionally not pinned here — ARG1-022 wires it; ARG1-020 commits only to the cwd-pinning + ARGOS_* env-var contract.
  - File scope: did not touch `argos/verifier/` (ARG1-031's domain), `argos/escalation/` (ARG1-041's domain), or any STATE.md file directly. Conflict on `argos/cli/__main__.py` with sibling Layer 2 tickets is expected; resolution per session brief is "keep both registrations".
  - Decision: pass
<!-- /argos:entry -->

<!-- argos:entry id=2026-04-30T17:40:38Z-ARG1-012-done ticket=ARG1-012 author=verifier session=sess-arg1-012-2026-04-30 -->
- **[2026-04-30T17:00:00Z] ARG1-012 — verified** (dispatch log writer landed)
  - Files changed: `argos/cli/dispatch_log.py` (new), `argos/cli/tests/test_dispatch_log.py` (new), `argos/specs/dispatch/.gitkeep` (new), `argos/specs/v1.0/tickets/ARG1-012-dispatch-log-writer.md` (Plan + Verification appended).
  - All five ACs from ticket pass: file at canonical path (AC#1), six-key frontmatter via `argos frontmatter-parse | python3 -c json check` (AC#2), append grows file with byte-equal frontmatter (AC#3), dry-run produces no files under `argos/specs/dispatch/` (AC#4), two concurrent dispatches produce two distinct files (AC#5).
  - Test suite: 164 unittest cases (16 new) green.
  - Concurrency model: per-ticket files via `O_CREAT | O_EXCL` (precedent ARG1-041); same-file appends via `fcntl.flock` + `tempfile` + `os.replace` (precedent ARG1-051). Frontmatter region byte-stable across appends.
  - Decision: pass
<!-- /argos:entry -->

<!-- argos:entry id=2026-04-30T17:42:38Z-ARG1-011-done ticket=ARG1-011 author=coder session=arg1-011-worktree -->
- **ARG1-011 — `/orchestrate` slash command + `argos orchestrate` queue read** (worktree `argos-v1-arg1-011`, branch `ticket/ARG1-011`)
  - Files changed: `.claude/commands/orchestrate.md` (new — slash command body referencing the orchestrator agent and the dispatch tool surface), `argos/specs/v1.0/commands/orchestrate.md` (new — byte-identical canonical mirror per the agent precedent), `argos/cli/queue.py` (new — stdlib-only `## Queue` section parser; `parse_queue` + `parse_queue_file`; `QueueSectionMissingError` / `StateFileNotFoundError`), `argos/cli/commands/orchestrate.py` (new — argparse shim; `--dry-run` is the only mode wired in v1.0 with non-`--dry-run` rejected since real dispatch is ARG1-022), `argos/cli/__main__.py` (modify — registered `orchestrate` in `PUBLIC_SUBCOMMANDS`, help line, dispatch branch; three localized edits, keep-both-registrations merge pattern), `argos/cli/tests/test_orchestrate.py` (new — 18 tests across `ParseQueueLibraryTests`, `OrchestrateCLITests`, `SlashCommandFileTests`), `argos/specs/v1.0/tickets/ARG1-011-orchestrate-slash-command.md` (Plan + Verification appended).
  - ACs: 6/6 met (verified live).
    - AC#1 `test -f .claude/commands/orchestrate.md` → exit 0.
    - AC#2 `argos orchestrate --dry-run --state-file <three-ticket-fixture>` → exit 0; stdout `ARG1-022\nARG1-013\nARG1-023\n` in queue order.
    - AC#3 `argos orchestrate --dry-run --state-file <empty-queue-fixture>` (placeholder italic only) → exit 0; stdout contains `queue empty`.
    - AC#4 `argos orchestrate --dry-run --state-file /nonexistent.md` → exit 1; stderr `orchestrate: STATE.md not found: …`.
    - AC#5 `grep -F 'orchestrator' .claude/commands/orchestrate.md` → exit 0.
    - AC#6 `argos orchestrate --dry-run --batch-size 2 …` against four-ticket queue → exit 0; stdout has exactly two ids (`ARG1-001`, `ARG1-002`).
  - Tests: `python3 -m unittest argos.cli.tests.test_orchestrate -v` → 18 tests, all OK (Ran 18 tests in 0.152s). Regression: `python3 -m unittest discover -s argos/cli/tests` → 166 tests, all OK (Ran 166 tests in 4.631s). No collateral breakage.
  - Stdlib-only preserved: `argos.cli.queue` imports `re`, `pathlib`; `argos.cli.commands.orchestrate` imports `argparse`, `sys`, plus the project module. `pyproject.toml` unchanged. ADR-001 + ADR-002 contracts intact.
  - Slash command mirror: `diff -q .claude/commands/orchestrate.md argos/specs/v1.0/commands/orchestrate.md` → exit 0 (byte-identical). Matches the established `.claude/agents/<name>.md` ↔ `argos/specs/v1.0/agents/<name>.md` mirror pattern (ARG1-010, ARG1-030).
  - Out of scope confirmed: no parallel dispatch (ARG1-022), no worktree creation (ARG1-020), no independence analysis (ARG1-021), no escalation file production (ARG1-041), no edits to `.claude/agents/orchestrator.md`, `argos/specs/v1.0/agents/orchestrator.md`, `argos/cli/dispatch.py`, `argos/cli/dispatch_log.py`, `argos/verifier/`, `argos/escalation/`, `argos/orchestrator/`.
  - Sibling Layer 2 coordination: only `argos/cli/__main__.py` is shared with the cohort; ARG1-012's `Touches` does not include `__main__.py`, so no sibling conflict expected. Per the keep-both-registrations precedent that ARG1-020 / ARG1-031 / ARG1-041 already merged.
  - Findings: 0 critical, 0 major, 0 minor.
  - Decision: pass
<!-- /argos:entry -->

<!-- argos:entry id=2026-06-13T21:25:52Z-ARG1-069-done ticket=ARG1-069 author=verifier session=local-2026-06-13 -->
- **[2026-06-13] ARG1-069 — done** (headless prompt injection into spawn_session)
  - New `argos/cli/orchestrator/session_prompt.py`: pure `build_prompt(ticket_id, ticket_text)` + I/O wrapper `build_prompt_for_ticket(ticket_id, ticket_dir=...)`. Codifies the six standing rules (ADR-001 stdlib, ADR-002 AC-stdlib, verify-before-commit, `argos state-append`/no direct STATE.md edit, push-don't-merge, escalate via escalation.md), inlines the ticket text, instructs read-and-implement.
  - `argos/cli/worktree.py` `spawn_session`: now invokes the harness headlessly as `[binary, "-p", prompt, "--allow-dangerously-skip-permissions"]` (permission flag overridable via `permission_arg`). Prompt auto-built from the ticket file under `<worktree>/argos/specs/v1.0/tickets`; degrades gracefully to a read-the-file instruction when absent. Still exports ARGOS_TICKET/EPIC/WORKTREE and returns the child exit code. Callers (run_session command, retry runner) unchanged.
  - Tests: `test_session_prompt.py` (9, pure builder) + `test_spawn_session.py` (5, argv-capturing stub binary asserts `-p` + prompt). Full sweep `python3 -m unittest discover -s argos/cli/tests` = 333 pass. `argos lint-imports argos/` exits 0 (stdlib only).
  - Decision: done.
<!-- /argos:entry -->

