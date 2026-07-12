# ARG-006 — Bare CLI commands work from any directory inside the repo

**Status:** Done
**Created:** 2026-07-12
**Priority:** P2
**Closed:** 2026-07-12

## Intent

`orchestrate`, `queue`, `state-append`, and `independence` resolved their default spec paths relative to the current directory, so bare invocations failed with "STATE.md not found" from any subdirectory — while `status`, `sync`, and `attend` locate the repo root themselves. Anchor the shared resolver (`argos/cli/spec_paths.py`) at the nearest enclosing repo root so an installed `argos` works from anywhere inside a repo.

## Context

Surfaced during the 2026-07-12 audit follow-up. The `spec_paths.py` probe is already marked INTERIM pending the `project.specs_root` config key (ARG1-075); this fix layers a repo-root ascent onto the interim probe without changing the eventual model.

## Non-goals

- The `project.specs_root` config key (ARG1-075's eventual model).
- Changing explicit `--state-file` / `--ticket-dir` flags or explicit `repo_root` arguments — those keep the historical relative-path contract byte-for-byte.
- CLI distribution/packaging (still deliberately open per ADR-001 §Scope).

## Acceptance criteria

- [x] Bare `argos orchestrate --dry-run` and `argos queue` succeed from a repo subdirectory (verified live from `docs/`).
- [x] Bare calls made at the repo root return the same relative paths as before.
- [x] Explicit `repo_root` callers (`sync`, `attend`, `clean-queue`, `cycle-close`) are unchanged.
- [x] The ascent stops at a `.git` boundary — a bare call inside an unscaffolded repo never escapes into a parent project's spec tree.

## Resolution

Closed 2026-07-12 (implemented same day; explicit user request, out-of-loop per RULES §off-ticket work). `spec_paths.py` gained `_anchor()`: a bare `'.'` call made from a subdirectory walks up to the nearest ancestor containing `argos/specs/` or `.git` and returns absolute paths anchored there; all other calls are untouched. 4 new tests in `test_spec_paths.py` (subdir anchor, root-stays-relative, `.git` boundary, explicit-root regression); full suite 437 pass.
