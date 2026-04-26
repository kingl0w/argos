# ARG1-041 — Escalation writer + optional webhook POST

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 5 (Escalation channel)

## Intent

Implement `argos escalate` (callable by any agent or operator script): given a ticket ID, severity, raised_by, and body content, write a well-formed escalation file under `argos/specs/escalations/{ticket-id}-{ISO-timestamp}.md` and, if `escalation.webhook_url` is set in `.argos/local.toml`, POST a JSON summary `{ticket_id, severity, summary, file_path}` to that URL (fire-and-forget; no retries; non-zero HTTP status logged but does not fail the command).

## Context

ARCHITECTURE.md §Components/Escalation Channel specifies the two-channel minimum: file-based queue + optional webhook. PRD success criterion #1 (operator walk-away) depends on escalations actually reaching the operator without polling the directory by hand.

## Non-goals

- No webhook auth (TODO in ARCHITECTURE.md — follow-up if needed).
- No retry on webhook failure (fire-and-forget by design).
- No queuing of webhook deliveries (synchronous best-effort).
- No notification routing rules.

## Acceptance criteria

- [ ] `argos escalate --ticket ARG1-099 --severity blocking --raised-by orchestrator --body 'test'` exits 0; a file matching `argos/specs/escalations/ARG1-099-*.md` is created and validates against ARG1-040's schema.
- [ ] With `escalation.webhook_url` unset in `.argos/local.toml`, `argos escalate` makes no network calls (verified by setting `webhook_url = ""` and confirming no `connect()` syscall to a non-loopback address — TODO: pick a portable check).
- [ ] With `escalation.webhook_url = "http://127.0.0.1:PORT/hook"` pointing to a test HTTP server, `argos escalate ...` results in exactly one POST request to that URL within 5 seconds; the request body is JSON with keys `ticket_id`, `severity`, `summary`, `file_path`.
- [ ] When the webhook returns HTTP 500, `argos escalate` still exits 0; stderr contains `webhook delivery failed: 500`.
- [ ] When the webhook URL is unreachable (port closed), `argos escalate` exits 0 within 5 seconds (no infinite hang); stderr contains `webhook delivery failed`.
- [ ] `argos escalate --ticket ARG1-099 --severity invalid --body x; echo $?` prints non-zero; stderr contains `severity must be blocking or advisory`.
- [ ] Two concurrent `argos escalate` calls for the same ticket produce two distinct files (timestamps differ at second resolution; tiebreaker via random suffix if needed); no file is overwritten.

## Depends on

- ARG1-040 (escalation schema)
- ARG1-053 (config split — reads `escalation.webhook_url`)

## Touches

- `argos/cli/commands/escalate.py` (or equivalent — new)
- `argos/cli/escalation.py` (or equivalent — writer + webhook)
- `argos/cli/tests/test_escalate.py` (or equivalent)
- `argos/cli/tests/fixtures/test_webhook_server.py` (or equivalent)

## Parallelizable with

- ARG1-003 (status)
- ARG1-004 (sync)
- ARG1-005 (attend — different command file)
- ARG1-011 (orchestrate slash command)
- ARG1-012 (dispatch log writer)
- ARG1-013 (auto-fix retry)
- ARG1-021 (independence detection)
- ARG1-022 (parallel dispatch)
- ARG1-023 (worktree merge)
- ARG1-031 (verifier writeback)
- ARG1-052 (merge driver)
