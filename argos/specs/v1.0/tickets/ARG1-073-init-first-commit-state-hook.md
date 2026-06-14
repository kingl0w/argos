# ARG1-073 — init's first commit trips the STATE.md append-only hook

## Intent

The pre-commit hook (ARG1-032, `argos/scripts/hooks/pre-commit-state-write.sh`)
enforces append-only STATE.md writes. On `argos init` of a fresh repo, STATE.md
goes from untracked to scaffolded — a creation, not a modification — but the
hook treats it as an append-violation and blocks the first commit. Every fresh
`argos init` therefore fails its first commit and requires the
`ARGOS_CYCLE_CLOSE=1` bypass, which is the wrong UX for first-run.

## Context

Discovered during the jobhunter dogfood. `argos init` installs the hook into the
target's `.git/hooks` **and** scaffolds `argos/specs/STATE.md`; the hook then
rejects committing the very scaffold init produced. Because the file is brand
new, the staged diff is entirely `+` lines of prose (headings, the
`**Last updated:**` line, the placeholder bullets) with no `argos:entry`
blocks — exactly the shape the hook flags as `STATE.md modified outside
append-block`.

Fix shape: the hook should allow a STATE.md that is **not yet tracked** in git
(e.g. `git ls-files --error-unmatch <path>` fails, or no HEAD blob exists for
it) — treat first-appearance as creation and allow it; enforce append-only only
on an already-tracked STATE.md. The `ARGOS_CYCLE_CLOSE=1` bypass and the
existing append-only enforcement on tracked files are unchanged.

## Acceptance criteria

Verifiable via the existing POSIX-shell harness (extending the existing harness
`argos/scripts/hooks/tests/test_pre_commit.sh`, mirroring its sandbox style):

- [ ] committing a STATE.md that is not yet git-tracked succeeds without `ARGOS_CYCLE_CLOSE`
- [ ] committing a non-append modification to an ALREADY-tracked STATE.md still fails
- [ ] the `ARGOS_CYCLE_CLOSE=1` bypass still works as before

## Touches

- `argos/scripts/hooks/pre-commit-state-write.sh`
- `argos/scripts/hooks/tests/test_pre_commit.sh` (its tests)

## Depends on

- (none)
