# Argos — State

**Last updated:** 2026-07-12
**Updated by:** human (audit cleanup batch — see Done this cycle)

This file is the project's short-term memory. Every subagent reads it first. Only the verifier writes it during the loop; humans write it on out-of-loop edits.

## Current focus

v0.5 layout consolidation shipped (commit `330ec3f`); init guard regression fixed in `d409774`. Argos now self-hosts — tickets tracked under `argos/specs/tickets/`, starting with ARG-001 and ARG-002. v1.0 spec tree work in progress: ARG1-040 (escalation schema) verified.

## Queue

Tickets ready to be worked, in rough priority order. The planner picks the top one on `/next` unless told otherwise.

- ARG-003 — Ship editor config for visual collapse of harness-required directories (P2)
- ARG-004 — Investigate relocatable config for Cursor / Codex / Gemini (P2)
- ARG-005 — Scan-report generator for retrofit onto existing codebases (P2)

## In progress

Tickets currently being executed by the loop or paused mid-cycle. At most one per operator.

- [ ] _none_

## Done this cycle

Tickets completed since the last cycle close. Cleared when you close a cycle (weekly, by default). Append-only within a cycle.

- v0.5 consolidation — runtime files moved under `argos/`; migration script for v0.4 users shipped (commit `330ec3f`)
- Init guard fix — removed redundant `STATE.md` heuristic; sentinel is sole source of truth for "already initialized" (commit `d409774`). Resolves the drift flagged after `7cd81f2`.
- ARG1-050 (2026-04-26) — STATE.md append-mostly block schema doc + reference parser shipped; 13/13 pytest tests pass; 12 files added under `argos/specs/v1.0/schemas/` and `argos/cli/`.
- ARG1-040 — Escalation file schema and `escalations/` directory contract verified 2026-04-26 (manual session, no worktree dispatch — v0.5 loop run on the v1.0 spec tree). New files: `argos/specs/v1.0/schemas/escalation.md`, `argos/specs/v1.0/schemas/examples/escalation-{blocking,malformed}.md`, `argos/specs/escalations/{.gitkeep,README.md}`, `argos/cli/{__init__.py,escalation_validator.py,escalation-validate,tests/__init__.py,tests/test_escalation_validator.py}`. 7 unit tests pass; all 6 acceptance criteria covered. 0 critical / 0 major / 0 minor findings. Decision: pass. Validator language is provisional Python pending ADR-001; stdlib only, no deps added.
- **[2026-07-12] ARG-006 — bare CLI commands from any directory** (human-directed, out-of-loop; ticket filed and closed same day). `spec_paths.py` `_anchor()`: bare default-path calls from a repo subdirectory ascend to the nearest ancestor with `argos/specs/` or `.git`; explicit roots and root-cwd calls unchanged. Fixes `orchestrate`/`queue`/`state-append`/`independence` failing with "STATE.md not found" outside the repo root. +4 tests (`test_spec_paths.py`); suite 437/437; verified live from `docs/`.
- **[2026-07-12] Audit cleanup batch** (human-directed, out-of-loop; explicit one-off per RULES §off-ticket work — full-repo audit findings; ARG-001 / ARG-002 closed as tickets)
  - ARG-001 closed: premise no longer reproduced (accepted ADR-001 on disk → `argos-status.sh` exit 0). Disposition: deleted `argos-status.sh`, `argos-sync.sh`, `argos-init.sh` — superseded by `argos status` / `sync` / `init`. `install-hooks.sh` / `install-merge-driver.sh` retained (exercised by the shell test harnesses; installed at runtime). References updated in README, `.github/ISSUE_TEMPLATE/ticket.yml`, and `reconcile.py` docstrings.
  - ARG-002 closed: README gained "Self-hosting: the two spec trees" and "Installing the CLI" sections (spec-tree probe rule, ticket placement, pipx / pip / `python3 -m` install paths).
  - `argos orchestrate` now prints a stderr note when it auto-selects the versioned `argos/specs/v1.0/` tree (footgun: bare `orchestrate` in this repo never sees the flat-tree ARG-* queue); +2 tests in `test_orchestrate.py`.
  - Fixed unclosed `Popen` pipes in `test_parallel_dispatch.py`; suite is clean under `-W error::ResourceWarning`.
  - Untracked residue removed: `build/`, both `*.egg-info/`, `.pytest_cache/` dirs, stale `argos/specs/dispatch/EPIC-001/` (June dispatch locks/logs).
  - Verification: unit suite 433/433 pass; `lint-imports argos/` clean; `argos status` all four checks pass; pre-commit hook tests 14/14; merge-driver tests 11/11; build-drift clean.
- [2026-07-07] Off-ticket hotfix (explicit user request, outside the loop) — argos-graph viz now auto-centers: `fitView()` + initial origin-centering in `tools/argos-graph/argos_graph/viz_template.html` (force mode centers immediately and refits on simulation settle; hierarchy fits synchronously; auto-fit stops once the user pans/zooms). 22/22 argos-graph pytest tests pass. Also added `scripts/build-docs.sh` (regenerates `docs/graph.html` for the GitHub Pages showcase and injects a back-to-landing link; the tool template stays landing-page-agnostic).


<!-- argos:entry id=2026-05-03T16:56:21Z-ARG1-032-verify ticket=ARG1-032 author=verifier session=local-2026-05-03 -->
- **[2026-05-03] ARG1-032 — verified** (session local-2026-05-03, worktree `argos-v1-arg1-032`)
  - Files added: `argos/scripts/hooks/pre-commit-state-write.sh`, `argos/scripts/install-hooks.sh`, `argos/scripts/hooks/tests/test_pre_commit.sh`
  - Files edited: `argos/scripts/argos-init.sh`, `argos/specs/v1.0/tickets/ARG1-032-pre-commit-verifier-only-state.md`
  - AC harness: 8 pass, 0 fail, 0 warn (`sh argos/scripts/hooks/tests/test_pre_commit.sh`)
  - Findings: 0 critical, 0 major, 0 minor
  - Decision: pass
<!-- /argos:entry -->

<!-- argos:entry id=2026-06-14T00:33:20Z-ARG1-003 ticket=ARG1-003 author=verifier session=local-arg1-003 -->
- **[2026-06-13] ARG1-003 — verified** (session local-arg1-003, worktree `.argos/worktrees/ARG1-003-c5f1c8c/`)
  - Implemented `argos status` integrity oracle: `argos/cli/integrity.py` (four checks: state_md, config, escalations, git_alignment) + `argos/cli/commands/status.py` (`--json`, `--repo-root`), wired into `argos/cli/__main__.py` (status no longer a stub).
  - Tests: `argos/cli/tests/test_status.py` (20 cases incl. all 6 ACs); retargeted obsolete `status` stub guard in `argos/cli/tests/test_version.py` to `attend`.
  - AC harness: all 6 ACs verified live (clean init→exit 0; unclosed block→STATE.md+`unclosed entry`; malformed escalation names path; undrained blocking→`undrained escalation`; `--json` 4 keys pass/fail + matching exit; `time` user+sys=0.041s < 2.0). Full suite 361 pass; lint-imports clean (stdlib-only, ADR-001).
  - Findings: 0 critical, 0 major, 0 minor
  - Decision: pass
  - _Relocated 2026-07-01: this block was originally appended under `## Known drift`._
<!-- /argos:entry -->

<!-- argos:entry id=2026-06-14T00:41:22Z-ARG1-005 ticket=ARG1-005 author=verifier session=autonomous-2026-06-13 -->
**[2026-06-13] ARG1-005 — verified** (autonomous session, worktree `ARG1-005-c5f1c8c`)
  - Implements `argos attend`: drains `argos/specs/escalations/`, presents each pending escalation oldest-first, records the operator's decision in the ticket's `## Decisions` section, removes the file. `--list` shows pending without prompting; `--ticket` filters by `ticket_id`. Drained files (carrying `## Resolution`) and the `README.md` sentinel are skipped.
  - Files added: `argos/cli/commands/attend.py`, `argos/cli/tests/test_attend.py`. Edited: `argos/cli/__main__.py` (route `attend`, drop from stub map).
  - Tests: `python3 -m unittest argos.cli.tests.test_attend` → 20 pass; full suite 361 pass. `lint-imports` clean (stdlib only, ADR-001).
  - AC harness: all 6 acceptance criteria run and quoted (AC#1 against the live repo, AC#2-#6 in sandbox fixtures); 0 critical / 0 major / 0 minor.
  - Decision: pass
  - _Relocated 2026-07-01: this block was originally appended under `## Known drift`._
<!-- /argos:entry -->

- **[2026-07-01] Repo-consistency hotfix batch** (human, out-of-loop; no ticket — explicit one-off per RULES §off-ticket work)
  - CI: spec-lint code filter fixed (previously exempted all of `argos/`, i.e. the entire CLI); added jobs running the unit test suite, `argos lint-imports`, `argos status`, and a build-drift check (`scripts/build.sh && git diff --exit-code`).
  - Build drift healed: newer `.claude/agents/{coder,planner,verifier}.md` back-ported into `source/agents/` (canonical again); `orchestrator.md` added to `source/agents/` and now builds into all four harness dirs; README updated.
  - Specs made self-consistent: real `argos/specs/ARCHITECTURE.md` written (was template-only); queue tickets ARG-001…ARG-005 backfilled as files under `argos/specs/tickets/`; stale ADR-001 drift entry closed; v1.0 STATE queue reconciled (ARG1-003/004/005 shipped).
  - `argos status` extended: `state_md` check now also verifies every `## Queue` entry resolves to a ticket file (+2 tests in `test_status.py`).
  - Packaging: `[tool.setuptools.package-data]` added to make `argos/cli/templates/` inclusion explicit (verified `pip install` + `argos init` in a clean venv works both before and after — the fix guards against setuptools `include-package-data` default changes, not a live breakage).
  - Deleted dead `argos/cli/escalation-validate` shim (dispatcher subcommand landed with ARG1-001); removed a stale zero-byte `argos/specs/v1.0/STATE.md.lock` (already gitignored).

## Open decisions

Product or architecture calls that are pending and block one or more queued tickets. Each becomes an ADR once decided.

- _none_

## Known drift

Places the code and `argos/specs/ARCHITECTURE.md` disagree. Each entry should name the file or module, one sentence on the mismatch, and a disposition (fix code, update docs, file ADR).

- _none_ (2026-07-01: the `escalation_validator.py` provisional-language entry closed — ADR-001 is Accepted on Python; the ARG1-003 / ARG1-005 verification blocks that had been appended here were relocated to `## Done this cycle` where they belong.)

## Backlog

- `tools/argos-graph/` — optional, read-only RDF projection of the specs into a knowledge graph (own `pyproject.toml` + rdflib; not part of the stdlib-only argos core). v1.1 items: `{nodes,edges}` JSON visualizer (pending); effective-status reconciliation query (landed).

