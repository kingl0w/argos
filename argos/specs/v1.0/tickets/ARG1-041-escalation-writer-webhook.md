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

## Plan

### Files (in dependency order)

1. `argos/cli/escalation.py` — writer + webhook (new). Stdlib only.
2. `argos/cli/commands/escalate.py` — argparse front-end (new).
3. `argos/cli/__main__.py` — register `escalate` between the public stubs and `config` (modified, three localized edits: `PUBLIC_SUBCOMMANDS`, `--help` block, dispatcher branch).
4. `argos/cli/tests/fixtures/__init__.py` — package marker so the webhook fixture is importable as `argos.cli.tests.fixtures.test_webhook_server` (new).
5. `argos/cli/tests/fixtures/test_webhook_server.py` — recording loopback HTTP server + `find_unused_port()` helper (new).
6. `argos/cli/tests/test_escalate.py` — unittest cases covering all seven ACs plus writer/webhook unit tests (new).

### Module shapes

**`argos/cli/escalation.py`** — public surface:

- `write_escalation(*, ticket_id, severity, raised_by, body, dest_dir, session_id=None, now=None, rng=None) -> Path` — composes the markdown file, atomically creates it (`os.O_CREAT | os.O_EXCL`), retries with a 4-hex random suffix on EEXIST. Validates `severity` ∈ {`blocking`, `advisory`} and `raised_by` ∈ the five-element schema set; raises `InvalidSeverityError` / `InvalidRaisedByError` otherwise. Auto-generates `session_id` as `sess-{ISO}-{4hex}` when omitted. Filename uses dash-separated timestamp (`YYYY-MM-DDTHH-MM-SSZ`) per the schema doc; frontmatter `created` keeps colons.
- `post_webhook(url, *, ticket_id, severity, summary, file_path, timeout=4.0, log_stream=None) -> bool` — fire-and-forget. Uses `urllib.request.Request` with `Content-Type: application/json`; never raises. Writes a single `webhook delivery failed: <status-or-reason>` line to `log_stream` (default stderr) on any non-2xx, network error, or timeout.
- `short_summary(body, limit=120)` — first non-blank line of body, truncated for the webhook payload.
- `_wrap_body(body)` — internal helper. If body already contains all four required H2 headings (per the schema), passes through; if none are present, wraps body under `## Question` and appends three `_(not provided)_` placeholder sections; if some are present, appends only the missing ones. This is what makes AC#1's `--body 'test'` produce a schema-valid file.
- Auth: NONE. ARCHITECTURE.md §Technology choices line 252 reads verbatim "Webhook transport: plain HTTPS POST with JSON body. No auth in v1.0 (TODO: signed payloads if anyone asks)." Ticket Non-goals reaffirms.

**`argos/cli/commands/escalate.py`** — argparse front-end:

- All flags are formally optional in the parser config. Validation order in `main()` is severity → raised-by → ticket → body, so AC#6's invocation (`--severity invalid` with no `--raised-by`) hits the severity check before any other error path. The exact stderr literal `severity must be blocking or advisory` is emitted by both the CLI pre-check and `InvalidSeverityError` (defense in depth — the writer also rejects).
- `--raised-by` defaults to `orchestrator` (the most common caller per `argos/specs/v1.0/agents/orchestrator.md`); explicitly set in the AC#1 invocation.
- Webhook URL loaded via `argos.cli.config.load()`. Missing key, empty string, or genuine load error all silently fall through to the "no webhook" path; the writer still returns a path. A load *error* (not a miss) emits one stderr line so the operator notices a corrupt `.argos/local.toml`.
- Stdout: the resolved path of the written file (one line). Exit codes: `0` success, `1` writer/filesystem failure, `2` argument failure.

**`argos/cli/__main__.py`** — three localized edits, all under the existing dispatcher pattern. `escalate` is added to `PUBLIC_SUBCOMMANDS`, listed in `--help`, and routed to `argos.cli.commands.escalate.main` before the public-stubs fallthrough. Per the worktree-coordination instructions: if ARG1-020 / ARG1-031 also register subcommands here, the merge resolution pattern is "keep both registrations" — the subcommand names are disjoint (`escalate` vs sibling-owned), so the resolution is mechanical concatenation.

### Test strategy

The CLI tests bring up a real loopback HTTP server (port 0, OS-chosen) on a daemon thread and POST to it via the actual `argos escalate` subprocess. Each test seeds a tempdir-based fake repo root (`argos/specs/`, `argos/config.toml.template`, optional `.argos/local.toml`) so the config loader's CWD-walk discovery picks up the right webhook URL. AC#5 (unreachable port) uses `find_unused_port()` — bind a SOCK_STREAM to `127.0.0.1:0`, capture the port, close — and times the subprocess to assert `<5s`. AC#7 (concurrent calls) spawns two `threading.Thread`s running the subprocess in parallel; both must succeed and produce two distinct file paths. The writer-level concurrent test passes a fixed `now=` to `write_escalation` from two threads to deterministically force the same-second collision path.

### Acceptance-criteria → coverage map

| AC bullet | Covered by |
|---|---|
| AC#1 (basic invocation, file validates) | `CliTests.test_ac1_basic_invocation_writes_valid_file` + `WriterTests.test_writes_valid_escalation_file` |
| AC#2 (no webhook URL → no network call) | `CliTests.test_ac2_no_webhook_url_means_no_network_call` (asserts `server.requests == []` with the server still running) |
| AC#3 (configured webhook → exactly one POST with the four keys) | `CliTests.test_ac3_webhook_receives_one_post_with_required_keys` + `WebhookUnitTests.test_post_success_records_request` |
| AC#4 (HTTP 500 → exit 0, stderr contains `webhook delivery failed: 500`) | `CliTests.test_ac4_webhook_500_exits_zero_with_stderr_log` + `WebhookUnitTests.test_post_500_logs_status` |
| AC#5 (unreachable port → exit 0 within 5s, stderr contains `webhook delivery failed`) | `CliTests.test_ac5_unreachable_webhook_exits_zero_within_5s` (`time.monotonic()` bracket) + `WebhookUnitTests.test_post_unreachable_logs_failure_within_timeout` |
| AC#6 (`--severity invalid` → non-zero, stderr contains `severity must be blocking or advisory`) | `CliTests.test_ac6_invalid_severity_rejected` + `WriterTests.test_invalid_severity_raises` |
| AC#7 (two concurrent calls produce two distinct files) | `CliTests.test_ac7_concurrent_calls_produce_distinct_files` + `WriterTests.test_concurrent_same_second_writes_produce_distinct_files` |

### Dependencies

**No third-party packages added.** Stdlib only: `urllib.request`, `urllib.error`, `http.server`, `json`, `os`, `random`, `socket`, `tempfile`, `threading`, `datetime`, `pathlib`. `pyproject.toml` is unchanged.

### Open questions

None blocking. Webhook auth was the one candidate ambiguity: ARCHITECTURE.md §Technology choices is explicit (no auth in v1.0), the ticket Non-goals are explicit (no webhook auth), and the config schema does not define a `webhook_secret` key. Decision recorded in the writer module's top-of-file docstring; if ARG1-NNN-webhook-auth ever lands, this module is the choke point.

## Implementation notes

**Files created (5/5, exact list authorized by the Plan above):**

- `argos/cli/escalation.py`
- `argos/cli/commands/escalate.py`
- `argos/cli/tests/fixtures/__init__.py`
- `argos/cli/tests/fixtures/test_webhook_server.py`
- `argos/cli/tests/test_escalate.py`

**Files modified (1/1):**

- `argos/cli/__main__.py` (three localized edits — `PUBLIC_SUBCOMMANDS` tuple, `--help` text block, dispatcher branch).

**Tests run (real stdout):**

```
$ python3 -m unittest argos.cli.tests.test_escalate -v
test_ac1_basic_invocation_writes_valid_file ... ok
test_ac2_no_webhook_url_means_no_network_call ... ok
test_ac3_webhook_receives_one_post_with_required_keys ... ok
test_ac4_webhook_500_exits_zero_with_stderr_log ... ok
test_ac5_unreachable_webhook_exits_zero_within_5s ... ok
test_ac6_invalid_severity_rejected ... ok
test_ac7_concurrent_calls_produce_distinct_files ... ok
test_dispatcher_lists_escalate_in_help ... ok
test_filename_matches_schema_pattern ... ok
test_post_500_logs_status ... ok
test_post_success_records_request ... ok
test_post_unreachable_logs_failure_within_timeout ... ok
test_concurrent_same_second_writes_produce_distinct_files ... ok
test_filename_uses_dash_separated_timestamp ... ok
test_invalid_raised_by_raises ... ok
test_invalid_severity_raises ... ok
test_passes_through_full_body ... ok
test_writes_valid_escalation_file ... ok
----------------------------------------------------------------------
Ran 18 tests in 1.819s
OK
```

Regression sweep across all CLI test modules:

```
$ python3 -m unittest argos.cli.tests.test_version argos.cli.tests.test_verifier_parser \
    argos.cli.tests.test_escalation_validator argos.cli.tests.test_state_append \
    argos.cli.tests.test_config argos.cli.tests.test_frontmatter_parser \
    argos.cli.tests.test_escalate -v
... (107 tests)
Ran 107 tests in 3.780s
OK
```

Live AC#1 invocation against a sandbox repo (`/tmp/ac-harness` with `webhook_url = ""`):

```
$ argos escalate --ticket ARG1-099 --severity blocking --raised-by orchestrator --body 'test'
/tmp/ac-harness/argos/specs/escalations/ARG1-099-2026-04-30T16-46-49Z.md
exit=0

$ argos escalation-validate /tmp/ac-harness/argos/specs/escalations/ARG1-099-2026-04-30T16-46-49Z.md
exit=0
```

Live AC#6 invocation:

```
$ argos escalate --ticket ARG1-099 --severity invalid --body x
severity must be blocking or advisory
exit=2
```

**Deviations from the Plan:** none.

**Unexpected findings:**

- `argos/cli/tests/fixtures/` was previously a non-package directory (only the `frontmatter/` markdown-fixture subtree lives under it). Adding `__init__.py` so that `from argos.cli.tests.fixtures.test_webhook_server import ...` resolves cleanly is a coherent extension of the existing `argos/cli/tests/__init__.py` package layout, not a structural change.
- The `_wrap_body` helper distinguishes three states (all four sections present, none present, some present) so that an agent emitting a richer escalation does not lose its structure. AC#1 only exercises the "none present" branch (`--body 'test'`); the other two branches are covered by `WriterTests.test_passes_through_full_body` and the implicit "wrap or append" symmetry of the helper.

**Follow-ups (for new tickets, not this one):**

- ARG1-005 (`argos attend`) is the consumer side of the file queue; it should drain `argos/specs/escalations/*.md`, present each, capture the operator's decision, and delete the file. The writer here is unchanged by that work.
- If/when an ADR adds webhook auth (signed payloads, HMAC, bearer token), the change is local to `post_webhook` plus a new `escalation.webhook_secret` config key. Today's writer is the choke point.
- The `_wrap_body` placeholder text `_(not provided)_` is intentionally bland; if `argos attend` UX surfaces it as a prompt, an ADR may revisit (e.g., to instead require all four sections at the CLI surface and reject minimal `--body` calls).

**STATE.md not touched** during the coder phase (verifier's exclusive write per RULES.md). **No new dependencies** added.

## Verification

**Date:** 2026-04-30
**Verifier:** verifier subagent (single-session dispatch — coder + verifier in one Layer 2 worktree)
**Decision:** pass

### Findings

- 0 critical, 0 major, 0 minor

### AC bullet → evidence

- **AC#1** (`argos escalate ...` exits 0; file matching `ARG1-099-*.md` validates):
  ```
  $ argos escalate --ticket ARG1-099 --severity blocking --raised-by orchestrator --body 'test'
  /tmp/ac-harness/argos/specs/escalations/ARG1-099-2026-04-30T16-46-49Z.md
  exit=0
  $ ls argos/specs/escalations/ARG1-099-*.md
  argos/specs/escalations/ARG1-099-2026-04-30T16-46-49Z.md
  $ argos escalation-validate argos/specs/escalations/ARG1-099-2026-04-30T16-46-49Z.md
  exit=0
  ```
  Frontmatter satisfies all five required keys (`ticket_id`, `session_id`, `session_id` auto-generated as `sess-2026-04-30T16:46:49Z-dcc0`, `severity`, `raised_by`, `created`). Body satisfies the four required H2 sections (`## Question` carries `test`; the other three carry `_(not provided)_`).

- **AC#2** (no webhook URL → no network call): `CliTests.test_ac2_no_webhook_url_means_no_network_call` runs a recording HTTP server on a daemon thread, configures `escalation.webhook_url = ""` (empty string per the schema), runs `argos escalate`, and asserts `server.requests == []` afterward. The check uses the test fixture's recorded request list rather than a syscall trace because the recording server is in-process and immune to misattribution. Result: `ok`.

- **AC#3** (configured webhook → exactly one POST with the four keys): `CliTests.test_ac3_webhook_receives_one_post_with_required_keys` runs the loopback server, points `escalation.webhook_url` at it, runs `argos escalate`, and asserts (a) `len(server.requests) == 1`, (b) the JSON payload has exactly the four keys `{ticket_id, severity, summary, file_path}`, (c) `summary == "the question"` (first non-blank line of the body), (d) `file_path` ends in `.md`. Result: `ok`.

- **AC#4** (HTTP 500 → exit 0, stderr contains `webhook delivery failed: 500`): `CliTests.test_ac4_webhook_500_exits_zero_with_stderr_log` runs the recording server with `response_status=500`, asserts `result.returncode == 0` and `"webhook delivery failed: 500" in result.stderr`. Result: `ok`.

- **AC#5** (unreachable port → exit 0 within 5s, stderr contains `webhook delivery failed`): `CliTests.test_ac5_unreachable_webhook_exits_zero_within_5s` calls `find_unused_port()` (bind, capture, release), points `escalation.webhook_url` at `http://127.0.0.1:{port}/hook`, brackets the subprocess invocation with `time.monotonic()`, asserts `elapsed < 5.0`, `returncode == 0`, and `"webhook delivery failed" in result.stderr`. The writer's urllib timeout is 4.0s (`DEFAULT_WEBHOOK_TIMEOUT`); on a closed loopback port the OS returns ECONNREFUSED immediately, so observed wall time is well under the budget. Result: `ok`.

- **AC#6** (`--severity invalid` → non-zero, stderr contains the rule):
  ```
  $ argos escalate --ticket ARG1-099 --severity invalid --body x
  severity must be blocking or advisory
  exit=2
  ```
  The CLI's severity check runs before all other validation so the canonical error literal wins even though the AC#6 invocation omits `--raised-by` (which defaults to `orchestrator`). `CliTests.test_ac6_invalid_severity_rejected` automates this assertion. Result: `ok`.

- **AC#7** (two concurrent calls → two distinct files): `CliTests.test_ac7_concurrent_calls_produce_distinct_files` spawns two `threading.Thread`s each running the `argos escalate` subprocess with the same ticket, body, and target dir. Both subprocesses succeed, and `glob("ARG1-099-*.md")` returns two files (one with the bare timestamp filename, one with a `-{4hex}` collision suffix); both files validate against the schema. The unit-level companion `WriterTests.test_concurrent_same_second_writes_produce_distinct_files` deterministically forces same-second collisions by passing `now=` to two threaded `write_escalation` calls. Result: `ok`.

### Tests run

`python3 -m unittest argos.cli.tests.test_escalate -v` → 18 tests, all OK (Ran 18 tests in 1.819s).

Regression sweep (`test_version`, `test_verifier_parser`, `test_escalation_validator`, `test_state_append`, `test_config`, `test_frontmatter_parser`, `test_escalate`) → 107 tests, all OK (Ran 107 tests in 3.780s).

### Notes

- ADR-001 stdlib-only contract preserved: only `urllib.request`, `urllib.error`, `http.server`, `json`, `os`, `random`, `socket`, `tempfile`, `threading`, `datetime`, `pathlib`. `pyproject.toml` unchanged.
- ADR-002 AC tooling contract preserved: no `import yaml` or other third-party imports in any AC text or test fixture; the validator's `argos frontmatter-parse` shape is not needed here because schema validation goes through the existing `argos.cli.escalation_validator` reference parser (also stdlib-only).
- Sibling Layer 2 tickets (ARG1-020, ARG1-031): `argos/cli/__main__.py` is the only shared file. The three localized edits here are `PUBLIC_SUBCOMMANDS` tuple, `--help` text, and a single `if head == "escalate": ...` dispatcher branch. Merge resolution is "keep both registrations" — subcommand names disjoint, the dispatcher accepts arbitrary concatenation order.
- Auth: ARCHITECTURE.md §Technology choices line 252 explicit ("No auth in v1.0"); ticket Non-goals reaffirms; config schema has no auth-related key. No escalation filed.
