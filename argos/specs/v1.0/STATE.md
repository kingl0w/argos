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
