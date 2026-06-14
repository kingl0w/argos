# ARG1-076 — STATE.md authorship: the hook forces every session to claim author=verifier

## Intent

**DESIGN QUESTION — do not prescribe a single fix; lay out the options.**

The pre-commit STATE.md hook enforces `author must be verifier` for "Done this
cycle" entries. A dispatched *coder* session that records completion via
`argos state-append` is therefore forced to write as `author=verifier` even
though it is not the verifier. This is functional but semantically wrong: the
session's role and its recorded authorship diverge. This ticket exists to settle
the authorship model, not to ship a predetermined patch.

## Context

Found in the jobhunter dogfood (JOBH-001 / JOBH-002 runs). Observed twice:
once a session tried `author=coder`, was rejected by the hook, and reverted;
once a session wrote `author=verifier` "as the commit hook requires" and
succeeded. Relates directly to the STATE.md ownership model in ARCHITECTURE.md
("Only the verifier writes it during the loop") and to the hook shipped in
ARG1-032.

Question set this ticket must capture and answer:

1. Should a coder session write STATE.md at all, or is the "Done this cycle"
   entry solely the verifier/orchestrator's job to write post-verification?
2. If sessions may write, should the hook accept `author=coder` for completion
   lines?
3. Is git-author the right gate, or should authorship be a field validated
   differently (e.g. block frontmatter attribute, separate from committer)?
4. Does the single-session `run-session` path (no separate verifier step) change
   the answer versus the `orchestrate` path?

## Acceptance criteria

Open design ACs — the deliverable is a decision and the changes that follow from
it, not a fixed implementation:

- [ ] The decision on the STATE.md authorship model is recorded as an ADR.
- [ ] The hook and the session-prompt contract rule are mutually consistent — no role is forced to misattribute its authorship.
- [ ] Both the `run-session` and `orchestrate` paths are verified against the chosen model.
- [ ] The four context questions above are each answered (or explicitly deferred with a reason) in the ADR.

## Touches

- `argos/scripts/hooks/pre-commit-state-write.sh`
- `session_prompt.py` contract rules
- possibly a new ADR under `argos/specs/v1.0/decisions/`

## Depends on

- (none, but note ARG1-073 is adjacent — same hook file.)
