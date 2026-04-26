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

## Open decisions

_none_

## Known drift

<!-- argos:entry id=2026-04-26T00:00:00Z-ARG1-030-shim ticket=ARG1-030 author=verifier session=arg1-030-worktree -->
- **`argos/cli/argos` is a temporary bash shim**, not the real CLI binary. Implements only the `verifier-parse` subcommand to satisfy ARG1-030 AC#5 without prejudicing ARG1-001's CLI design. Disposition: ARG1-001 replaces this file with the real `argos` binary; the shim's TODO comment names that ticket.
- **`argos/__init__.py`, `argos/cli/__init__.py`, `argos/cli/tests/__init__.py`** turn the `argos/` directory into a Python package alongside its existing role as a docs tree (`argos/specs/`, `argos/RULES.md`, `argos/scripts/`). Disposition: revisit during ARG1-001 — the CLI ticket should decide whether the package layout stays under `argos/cli/` or moves to a dedicated `src/` layout; if it moves, the init files here are deleted.
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
