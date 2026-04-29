# Argos v1.0 — State

**Format:** append-mostly timestamped blocks per `argos/specs/v1.0/ARCHITECTURE.md` §Contracts/STATE.md format. Verifier-only writes during the loop; out-of-loop edits are append-only and signed below the entry.

## Current focus

Epic 4 — severity-tiered verifier. ARG1-030 (rubric + structured output) is the foundation; ARG1-031 (consumer) and ARG1-013 (auto-fix retry) build on it.

## Queue

_(populated as tickets are queued for dispatch; orchestrator reads this section)_

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


<<<<<<< HEAD
<!-- argos:entry id=2026-04-29T17:52:25Z-ARG1-010 ticket=ARG1-010 author=orchestrator session=arg1-010-worktree -->
- **[2026-04-29T00:00:00Z] ARG1-010 — orchestrator agent definition committed** (worktree `argos-v1-arg1-010`, branch `ticket/ARG1-010`)
  - Files changed: `argos/specs/v1.0/agents/orchestrator.md` (new), `.claude/agents/orchestrator.md` (new — byte-identical mirror).
  - ACs: 5/5 met. AC#1 `.claude/agents/orchestrator.md` exists. AC#2 v1.0 mirror exists; `diff -q` exits 0. AC#3 frontmatter parses as YAML; both `allowed_tools` and `denied_paths` keys present (verified with system `python3` + `pyyaml`). AC#4 `denied_paths` includes literal `argos/specs/PRD.md`, `argos/specs/ARCHITECTURE.md`, `argos/specs/STATE.md` (counts 2/2/2 across legacy + v1.0 paths). AC#5 body contains `dispatcher` (2), `reconciler` (2), `escalation` (15), `cannot mutate code` (1).
  - Definition covers: role/scope, inputs, outputs, decision authority, interaction contract with planner/coder/watchdog/verifier, parallel-dispatch contract (file-disjointness only — no content-level conflict detection), auto-fix retry contract (cap 1; ARG1-013 implements), escalation triggers calibrated to the three load-bearing precedents (ADR-001, tomllib-vs-tomli, .gitignore precedence) plus merge-time semantic conflict on disjoint sessions, termination conditions tied to `argos status` exit code, boundaries.
  - Out of scope per ticket: no CLI subcommand bodies, no worktree mechanics, no dispatch log writer, no `/orchestrate` slash command, no code.
=======
<!-- argos:entry id=2026-04-29T18:13:12Z-ARG1-058 ticket=ARG1-058 author=coder session=arg1-058-worktree -->
- **[2026-04-29T00:00:00Z] ARG1-058 — narrowed STATE.md sidecar lock ignore** (worktree `argos-v1-arg1-058`, branch `ticket/ARG1-058`, branched from `main`)
  - Files changed: `.gitignore` (+1 line, `**/STATE.md.lock` under the `# Argos` block).
  - Supersedes ARG1-056's broader `*.lock` pattern. Project convention is per-file ignores for lockfiles (`Cargo.lock` is already explicit); a glob would silently swallow `yarn.lock` / `pnpm-lock.yaml` / `package-lock.json` if a JS component ever lands.
  - Verified: `git check-ignore -v` resolves both `argos/specs/STATE.md.lock` and `argos/specs/v1.0/STATE.md.lock` to `.gitignore:5:**/STATE.md.lock`. `git check-ignore -v yarn.lock` exits non-zero (not ignored); `package-lock.json` and `pnpm-lock.yaml` likewise not ignored. After `argos state-append`, the v1.0 sidecar lock is created and `git status` is clean modulo the STATE entry.
  - Branched from main, not from ARG1-056 — diff is reviewable independently. Operator handles merge order between ARG1-056 and ARG1-058 (recommendation: merge only ARG1-058, or merge ARG1-056 first then ARG1-058 will conflict on the .gitignore line and the narrower pattern wins).
  - Out of scope: no other .gitignore edits, no changes to ARG1-051 locking mechanism.
>>>>>>> ticket/ARG1-058
  - Decision: pass
<!-- /argos:entry -->

## Open decisions

_none_

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
