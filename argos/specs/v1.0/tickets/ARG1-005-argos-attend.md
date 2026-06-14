# ARG1-005 — `argos attend` drains the escalation queue

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 1 (CLI installer)

## Intent

Implement `argos attend`: read every file under `argos/specs/escalations/`, present each to the operator one at a time (chronological order by frontmatter `created` field), capture the operator's free-form decision, append the decision to the originating ticket's `## Decisions` section, and remove the escalation file. `--list` mode shows pending escalations without prompting. `--ticket ARG1-NNN` filters to one ticket's escalations.

## Context

ARCHITECTURE.md §Components/Escalation Channel names `argos attend` as the v1.0 minimum surface for resolving operator-bound questions. PRD success criterion #1 (≤15 min walk-away) depends on attend being fast to drain — operators should not have to context-switch into individual files.

## Non-goals

- No re-routing. Attend handles whatever is in the directory; routing decisions belong to the webhook (ARG1-041) or upstream tooling.
- No partial-decision saving. If attend is interrupted, unresolved escalations stay in place for the next run.
- No ticket-status mutation. Recording a decision does not mark the ticket Done — the verifier still owns that.

## Acceptance criteria

- [ ] With no files in `argos/specs/escalations/`, `argos attend; echo $?` prints `0` and stdout contains `no pending escalations`.
- [ ] With one well-formed escalation file present, `argos attend --list` exits 0 and stdout contains the ticket ID and the `created` timestamp from the frontmatter.
- [ ] In `--list` mode, two files with different `created` timestamps appear in chronological order (oldest first); verified by `argos attend --list | head -1` matching the older ticket.
- [ ] After `echo "use option A" | argos attend --ticket ARG1-099`, the file `argos/specs/escalations/ARG1-099-*.md` no longer exists and `grep -F "use option A" argos/specs/tickets/ARG1-099-*.md` exits 0.
- [ ] With one malformed escalation file (missing required frontmatter), `argos attend --list` exits non-zero and stderr names the file path.
- [ ] `argos attend --ticket NONEXISTENT` exits 0 and stdout contains `no pending escalations for NONEXISTENT`.

## Depends on

- ARG1-001 (CLI scaffold)
- ARG1-040 (escalation schema)
- ARG1-041 (escalation writer — produces the files attend reads)

## Touches

- `argos/cli/commands/attend.py` (or equivalent)
- `argos/cli/tests/test_attend.py` (or equivalent)

## Parallelizable with

- ARG1-002 (init)
- ARG1-003 (status)
- ARG1-004 (sync)
- ARG1-011 (/orchestrate slash command)
- ARG1-020 (worktree spawn)
- ARG1-052 (merge driver)

## Plan

**New files**
- `argos/cli/commands/attend.py` — the `argos attend` subcommand.
- `argos/cli/tests/test_attend.py` — stdlib `unittest` coverage.

**Edit**
- `argos/cli/__main__.py` — route `attend` to the new module (remove it from the
  stub list).

**Behaviour**
- Default escalations dir = `argos/specs/escalations/`, tickets dir =
  `argos/specs/tickets/`, both resolved from the repo root (walk up for an
  `argos/specs` marker, mirroring `commands/escalate.py`). `--dir` /
  `--tickets-dir` override for tests.
- A "pending" escalation is a file under the escalations dir whose body has **no
  `## Resolution` heading** (drained files carry that section and are an audit
  trail — see `argos/specs/escalations/README.md` and the two existing files).
  This is what lets AC#1 pass against the real repo: both files there are
  drained, so the queue reads as empty.
- Each non-drained file is parsed + validated with
  `argos.cli.escalation_validator` (`parse_frontmatter` + `validate`). Any
  malformed file makes the scan fail fast: exit non-zero, one stderr line per
  bad path (AC#5).
- Pending escalations are ordered by frontmatter `created` (oldest first;
  `Z` normalised to `+00:00` for 3.9 `fromisoformat`).
- `--list`: one line per pending escalation (`ticket_id  created  severity
  filename`); empty queue prints `no pending escalations[ for <TICKET>]`; exit 0.
- drain (default): for each pending escalation in order, present it on stdout,
  read one line of decision from stdin (EOF stops the drain — no partial save),
  append the decision to the ticket's `## Decisions` section (created if absent),
  then delete the escalation file. Empty decision = skip (leave file). Missing
  ticket file = stderr error, leave file, exit non-zero.
- `--ticket` filters by frontmatter `ticket_id` in both modes.

**AC mapping**: #1 drained-skip → empty queue message; #2/#3 `--list` content +
chronological order; #4 stdin decision → ticket `## Decisions` + file removed;
#5 malformed → non-zero + path on stderr; #6 filtered empty queue message.
