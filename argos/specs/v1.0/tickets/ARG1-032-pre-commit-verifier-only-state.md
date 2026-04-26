# ARG1-032 — Pre-commit hook enforces "verifier-only writes STATE.md"

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P1
**Epic:** 4 (Severity-tiered verifier)

## Intent

Ship a pre-commit hook (`argos/scripts/hooks/pre-commit-state-write.sh`) that rejects any commit modifying `argos/specs/STATE.md` unless the modification consists entirely of new `<!-- argos:entry ... author=verifier ... -->` blocks (or new blocks under the cycle-close `--close-cycle` operation, identified by an env var). Registered by `argos init` (ARG1-002) into the local `.git/hooks/pre-commit` chain. Enforces the ARCHITECTURE.md §Invariants rule that the verifier is the sole writer.

## Context

ARCHITECTURE.md §Invariants names "verifier is the sole writer of STATE.md" and flags the enforcement question as TODO. This ticket answers that TODO by stamping the author in the block frontmatter and validating it at the hook layer. The hook is local (per-clone); CI re-runs the same validation on the PR.

## Non-goals

- No CI-side validation (separate, follow-up — same script can be reused).
- No author-identity verification (we trust the block's `author=` attribute; agent allowed-tools are the actual security boundary).
- No retroactive validation of historical commits.

## Acceptance criteria

- [ ] After `argos init`, `.git/hooks/pre-commit` contains a line invoking `argos/scripts/hooks/pre-commit-state-write.sh`.
- [ ] A commit that adds only `<!-- argos:entry ... author=verifier ... -->` blocks to STATE.md passes: `git commit -m test` exits 0 (in a synthetic test repo).
- [ ] A commit that modifies STATE.md content outside any `<!-- argos:entry -->` block fails: `git commit -m test; echo $?` prints non-zero; stderr contains `STATE.md modified outside append-block`.
- [ ] A commit that adds a block with `author=coder` fails: stderr contains `STATE.md author must be verifier`.
- [ ] A commit with `ARGOS_CYCLE_CLOSE=1` env set bypasses the hook (cycle-close operation): `ARGOS_CYCLE_CLOSE=1 git commit -m close` exits 0 even when STATE.md has block deletions.
- [ ] The hook exits 0 when the commit does not touch STATE.md (no false positives): `git commit -m unrelated` on an unrelated file change exits 0.

## Depends on

- ARG1-051 (state-append helper — defines the block format the hook validates)

## Touches

- `argos/scripts/hooks/pre-commit-state-write.sh` (new)
- `argos/scripts/hooks/tests/test_pre_commit.sh` (or equivalent — new)

## Parallelizable with

- ARG1-003 (status)
- ARG1-004 (sync)
- ARG1-005 (attend)
- ARG1-013 (auto-fix retry)
- ARG1-021 (independence detection)
- ARG1-022 (parallel dispatch)
- ARG1-023 (worktree merge)
- ARG1-041 (escalation writer)
- ARG1-052 (merge driver — different script)
- ARG1-054 (cycle close)
