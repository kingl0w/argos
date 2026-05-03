"""Auto-fix retry (ARG1-013).

When a session's verifier returns ``decision: fail``, the orchestrator
re-dispatches the inner planner→coder→watchdog→verifier loop **once**
in the same worktree. If the second verifier still emits
``decision: fail`` (or no parseable verifier-output), the orchestrator
writes a single blocking escalation file and stops. No third attempt.

Cap-1 is hard-coded per ARCHITECTURE.md §Invariants ("Auto-fix retry
cap is 1. Hard cap, not configurable beyond enabled/disabled."). The
``verifier.auto_fix_retries`` config key controls only enabled-vs-
disabled — any value ``>= 1`` enables one retry, ``0`` disables.

Architectural pins (locked in the ticket's ``## Plan``):

1. **Trigger == ``decision: fail``.** Reading the literal keeps the
   classification in one place (the verifier-output schema's
   invariants already encode "critical OR major OR tests_ran:false").
2. **Same-worktree retry.** The retry runner spawns the harness
   directly via :func:`argos.cli.worktree.spawn_session` against the
   existing worktree path. ``argos run-session`` is bypassed because
   it refuses to reuse worktrees by contract.
3. **Escalation on first fail when retries are disabled.** AC#5 is
   explicit: ``verifier.auto_fix_retries = 0`` produces an escalation
   immediately after the first fail. Disabled does not mean "ignore".
4. **No STATE.md writes from this module.** The verifier inside each
   session is still the sole STATE.md writer (orchestrator agent
   §Auto-fix retry behavior). This module writes the dispatch log
   ``retry`` event and the escalation file only.

ADR-001 stdlib-only. Imports limited to the ARG1-064 lint-imports
allowlist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from argos.cli import dispatch_log, escalation, worktree
from argos.cli.orchestrator.dispatch import SessionRequest, SessionRunner
from argos.cli.verifier_parser import (
    SchemaError,
    parse_block,
    validate,
)

__all__ = [
    "DEFAULT_TICKET_DIR_IN_WORKTREE",
    "DEFAULT_ESCALATION_DIR",
    "RetryConfig",
    "RetryOutcome",
    "compose_retry_session_id",
    "default_retry_runner",
    "find_ticket_file",
    "maybe_retry",
    "read_decision",
    "read_latest_verifier_output",
    "write_retry_event",
    "write_retry_failed_escalation",
]


# Per the verifier-output schema (`argos/specs/v1.0/schemas/verifier-output.md`
# §Location): the verifier appends its block inside the ticket file. Worktrees
# share the v1.0 layout, so the same relative path works in any worktree.
DEFAULT_TICKET_DIR_IN_WORKTREE = "argos/specs/v1.0/tickets"

# Per the escalation writer (ARG1-041): default escalation dir is
# `argos/specs/escalations/`. Re-export so callers don't need to import
# both modules.
DEFAULT_ESCALATION_DIR = escalation.DEFAULT_ESCALATION_DIR

_VERIFIER_BLOCK_OPEN = "<!-- argos:verifier-output -->"
_VERIFIER_BLOCK_CLOSE = "<!-- /argos:verifier-output -->"


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryConfig:
    """Static configuration for a dispatch's retry behaviour.

    ``enabled`` collapses ``verifier.auto_fix_retries`` to a boolean: any
    value ``>= 1`` enables one retry, ``0`` (or unset) disables. The
    ticket spec hard-caps the count at 1 regardless of the config value.
    """

    enabled: bool
    escalation_dir: Path
    ticket_dir_in_worktree: str = DEFAULT_TICKET_DIR_IN_WORKTREE


@dataclass(frozen=True)
class RetryOutcome:
    """The result of a :func:`maybe_retry` call.

    ``retried`` is True iff the retry runner was actually invoked.
    ``escalation_path`` is the file written by ARG1-041's writer when a
    blocking escalation was raised, or ``None`` when no escalation was
    needed.
    """

    final_returncode: int
    final_decision: Optional[str]
    retried: bool
    escalation_path: Optional[Path]


# ---------------------------------------------------------------------------
# Verifier-output reader
# ---------------------------------------------------------------------------


def read_latest_verifier_output(text: str) -> Optional[dict]:
    """Parse the **last** ``<!-- argos:verifier-output -->`` block in ``text``.

    The verifier-output schema §Location ratifies multiple blocks per
    ticket file across retries: "consumers parse the last one as
    authoritative." Returns ``None`` when no block is present (or the
    open marker is unmatched). Raises :class:`SchemaError` on a
    malformed last block; callers may downgrade that to ``None`` if
    they want a conservative "no decision" reading.
    """
    last_open = text.rfind(_VERIFIER_BLOCK_OPEN)
    if last_open == -1:
        return None
    body_start = last_open + len(_VERIFIER_BLOCK_OPEN)
    last_close = text.find(_VERIFIER_BLOCK_CLOSE, body_start)
    if last_close == -1:
        return None
    block = text[body_start:last_close].strip("\n")
    parsed = parse_block(block)
    validate(parsed)
    return parsed


def find_ticket_file(
    worktree_path: Path,
    ticket_id: str,
    ticket_dir: str = DEFAULT_TICKET_DIR_IN_WORKTREE,
) -> Optional[Path]:
    """Return the ticket file for ``ticket_id`` inside ``worktree_path``.

    Tickets are stored as ``{ticket-id}-{slug}.md`` (the prefix-with-slug
    convention used everywhere under ``argos/specs/v1.0/tickets/``). We
    glob ``{ticket_id}*.md`` and prefer the lexicographically first
    match — when only one ticket file exists per id (the invariant), the
    glob has exactly one result.
    """
    base = worktree_path / ticket_dir
    if not base.is_dir():
        return None
    for path in sorted(base.glob(f"{ticket_id}*.md")):
        return path
    return None


def read_decision(
    *,
    worktree_path: Path,
    ticket_id: str,
    ticket_dir: str = DEFAULT_TICKET_DIR_IN_WORKTREE,
) -> Optional[str]:
    """Return the latest verifier decision literal in ``ticket_id``'s file.

    Returns one of ``pass`` / ``pass-with-minors`` / ``fail`` when a
    parseable block is present. Returns ``None`` when:

    - The ticket file is missing or unreadable.
    - The file contains no verifier-output block.
    - The latest block is malformed (downgraded to ``None`` so the
      dispatcher's default action is conservative — no retry, no
      auto-escalation — rather than crashing on partial output).
    """
    path = find_ticket_file(worktree_path, ticket_id, ticket_dir)
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        parsed = read_latest_verifier_output(text)
    except SchemaError:
        return None
    if parsed is None:
        return None
    decision = parsed.get("decision")
    if decision in ("pass", "pass-with-minors", "fail"):
        return decision
    return None


# ---------------------------------------------------------------------------
# Session-id helpers
# ---------------------------------------------------------------------------


def compose_retry_session_id(original: str) -> str:
    """Compose the retry session id from ``original``.

    Shape: ``<original>-retry-1``. Conforms to dispatch_log's session-id
    slug (``^[A-Za-z0-9._:T-]+$``) as long as ``original`` already does.
    """
    if not original:
        raise ValueError("original session id must be non-empty")
    return f"{original}-retry-1"


# ---------------------------------------------------------------------------
# Dispatch-log + escalation writers
# ---------------------------------------------------------------------------


def write_retry_event(
    *,
    dispatch_file: Path,
    worktree_path: Path,
    batch_id: str,
    retry_session_id: str,
    at: Optional[datetime] = None,
) -> None:
    """Append a ``retry`` event to the dispatch log via ARG1-012's writer.

    The body lists the worktree, batch id, retry session id, and the
    ``attempt: 2`` marker. The body's ``- session: ...`` line is what
    makes a second distinct session id appear in the dispatch log file
    (AC#1, AC#3).
    """
    body = (
        f"- worktree: `{worktree_path}`\n"
        f"- batch: `{batch_id}`\n"
        f"- session: `{retry_session_id}`\n"
        f"- attempt: 2"
    )
    dispatch_log.append_event(
        dispatch_file=dispatch_file,
        event_type=dispatch_log.EVENT_RETRY,
        body=body,
        at=at,
    )


def _compose_escalation_body(
    *,
    ticket_id: str,
    worktree_path: Path,
    dispatch_file: Path,
    decision_first: str,
    decision_second: str,
    retried: bool,
) -> str:
    """Compose the escalation body. All four required H2 sections present.

    Validated against ``argos/specs/v1.0/schemas/escalation.md`` §Body
    sections; the writer (ARG1-041) wraps any missing sections with
    placeholders, but we ship them in source so the file reads cleanly.
    """
    if retried:
        question = (
            f"Auto-fix retry exhausted for `{ticket_id}`. The verifier "
            f"emitted `decision: fail` on the initial pass and again on "
            f"the retry. The orchestrator will not attempt a third "
            f"dispatch (cap-1 hard limit per ARCHITECTURE.md §Invariants). "
            f"Operator decision is required."
        )
        options = (
            "- Re-dispatch the inner loop again — rejected: cap-1 hard "
            "limit per ARCHITECTURE.md §Invariants and orchestrator agent "
            "§Auto-fix retry behavior.\n"
            "- Mark the ticket failed without escalating — rejected: the "
            "contract on retry exhaustion is a blocking escalation, not "
            "silent failure."
        )
        why = (
            "Two consecutive `decision: fail` outcomes from the verifier. "
            "This is the contract-defined exit point per "
            "`argos/specs/v1.0/agents/orchestrator.md` §Auto-fix retry "
            "behavior. The operator decides via `argos attend` whether "
            "to fix the work, re-scope the ticket, or abandon it."
        )
    else:
        question = (
            f"The verifier returned `decision: fail` for `{ticket_id}` "
            f"and auto-fix retry is disabled "
            f"(`verifier.auto_fix_retries = 0`). The orchestrator did "
            f"not attempt a retry. Operator decision is required."
        )
        options = (
            "- Enable auto-fix retry by setting "
            "`verifier.auto_fix_retries = 1` in `argos/config.toml` and "
            "re-running. Note that the cap is still 1 — a single retry "
            "is the maximum.\n"
            "- Inspect the worktree, fix the work manually, and merge.\n"
            "- Re-scope or abandon the ticket via `argos attend`."
        )
        why = (
            "The retry path is gated on `verifier.auto_fix_retries >= 1`. "
            "With retry disabled, any `decision: fail` is the contract-"
            "defined exit point per `argos/specs/v1.0/agents/orchestrator.md` "
            "§Auto-fix retry behavior."
        )
    return (
        "## Question\n\n"
        f"{question}\n\n"
        "## Context\n\n"
        f"- Ticket: `{ticket_id}`\n"
        f"- Worktree: `{worktree_path}` (preserved for inspection)\n"
        f"- Dispatch log: `{dispatch_file}`\n"
        f"- First-attempt decision: `{decision_first}`\n"
        f"- Retry decision: `{decision_second}`\n\n"
        "## Options considered\n\n"
        f"{options}\n\n"
        "## Why escalated\n\n"
        f"{why}\n"
    )


def write_retry_failed_escalation(
    *,
    ticket_id: str,
    session_id: str,
    worktree_path: Path,
    dispatch_file: Path,
    decision_first: str,
    decision_second: str,
    escalation_dir: Path,
    retried: bool,
    now: Optional[datetime] = None,
) -> Path:
    """Write a single blocking escalation via ARG1-041's writer.

    ``raised_by`` is hard-coded to ``orchestrator`` because retry
    exhaustion is, by definition, an orchestrator-authored escalation
    (the verifier's two fails are evidence; the *escalation* is the
    orchestrator's signal that the cap is reached).
    """
    body = _compose_escalation_body(
        ticket_id=ticket_id,
        worktree_path=worktree_path,
        dispatch_file=dispatch_file,
        decision_first=decision_first,
        decision_second=decision_second,
        retried=retried,
    )
    return escalation.write_escalation(
        ticket_id=ticket_id,
        severity="blocking",
        raised_by="orchestrator",
        body=body,
        dest_dir=escalation_dir,
        session_id=session_id,
        now=now,
    )


# ---------------------------------------------------------------------------
# Production retry runner
# ---------------------------------------------------------------------------


def _load_configured_binary() -> Optional[str]:
    """Best-effort load of ``harness.claude_code_binary`` from ARG1-053.

    Mirrors ``run_session._load_configured_binary``: errors are swallowed
    so a missing config file does not block the retry path. The env
    override (``ARGOS_RUN_SESSION_HARNESS_BIN``) and the ``claude``-on-
    PATH fallback inside :func:`worktree.resolve_harness_binary` keep the
    contract working when no config is initialized yet.
    """
    try:
        from argos.cli.config import KeyNotFoundError, load
    except Exception:
        return None
    try:
        cfg = load()
    except Exception:
        return None
    try:
        return cfg.get("harness.claude_code_binary")
    except KeyNotFoundError:
        return None
    except Exception:
        return None


def default_retry_runner(req: SessionRequest) -> int:
    """Production retry runner — re-spawn the harness in the existing worktree.

    The first attempt's worktree is preserved (orchestrator agent: "do
    not spawn a new worktree; the partial state is informative for the
    retry"). We bypass ``argos run-session`` because its
    ``WorktreeAlreadyExistsError`` is a load-bearing safety on the
    initial dispatch — reuse here is intentional, not accidental.

    Stdio is inherited so the interactive harness keeps its tty, just
    like the initial dispatch.
    """
    binary = worktree.resolve_harness_binary(configured=_load_configured_binary())
    return worktree.spawn_session(
        binary,
        req.worktree_path,
        ticket=req.ticket_id,
        epic=req.epic_id,
    )


# ---------------------------------------------------------------------------
# The decision function
# ---------------------------------------------------------------------------


def maybe_retry(
    *,
    req: SessionRequest,
    initial_returncode: int,
    dispatch_file: Path,
    config: RetryConfig,
    retry_runner: Optional[SessionRunner] = None,
    now_factory: Optional[Callable[[], datetime]] = None,
) -> RetryOutcome:
    """Read the verifier decision and (if needed) run a single retry.

    Decision tree:

    1. Read the latest verifier-output block from the worktree's ticket
       file. If decision is None, ``pass``, or ``pass-with-minors`` →
       no action; return the initial returncode + decision.
    2. If decision is ``fail`` and ``config.enabled`` is False → write a
       blocking escalation immediately (AC#5); return initial returncode
       + decision.
    3. If decision is ``fail`` and ``config.enabled`` is True → append a
       ``retry`` event to the dispatch log, invoke ``retry_runner``
       (defaults to :func:`default_retry_runner`) with a new
       session id, re-read the decision, and:
       a. If retry decision is ``pass`` or ``pass-with-minors`` →
          return the retry's returncode + decision; no escalation.
       b. If retry decision is ``fail`` (or unreadable) → write a single
          blocking escalation; return the retry's returncode + decision.

    The dispatch_log retry event is appended exactly when a retry
    actually runs; the escalation file is written exactly when the
    contract demands it (case 2 or case 3b).
    """
    if retry_runner is None:
        retry_runner = default_retry_runner

    initial_decision = read_decision(
        worktree_path=req.worktree_path,
        ticket_id=req.ticket_id,
        ticket_dir=config.ticket_dir_in_worktree,
    )
    if initial_decision != "fail":
        return RetryOutcome(
            final_returncode=initial_returncode,
            final_decision=initial_decision,
            retried=False,
            escalation_path=None,
        )

    if not config.enabled:
        esc_path = write_retry_failed_escalation(
            ticket_id=req.ticket_id,
            session_id=req.session_id,
            worktree_path=req.worktree_path,
            dispatch_file=dispatch_file,
            decision_first=initial_decision,
            decision_second="(retry disabled)",
            escalation_dir=config.escalation_dir,
            retried=False,
            now=(now_factory() if now_factory else None),
        )
        return RetryOutcome(
            final_returncode=initial_returncode,
            final_decision=initial_decision,
            retried=False,
            escalation_path=esc_path,
        )

    retry_session_id = compose_retry_session_id(req.session_id)
    write_retry_event(
        dispatch_file=dispatch_file,
        worktree_path=req.worktree_path,
        batch_id=req.batch_id,
        retry_session_id=retry_session_id,
        at=(now_factory() if now_factory else None),
    )

    retry_req = SessionRequest(
        ticket_id=req.ticket_id,
        epic_id=req.epic_id,
        batch_id=req.batch_id,
        worktree_path=req.worktree_path,
        branch=req.branch,
        repo_root=req.repo_root,
        session_id=retry_session_id,
    )
    retry_rc = retry_runner(retry_req)
    retry_decision = read_decision(
        worktree_path=req.worktree_path,
        ticket_id=req.ticket_id,
        ticket_dir=config.ticket_dir_in_worktree,
    )

    if retry_decision in ("pass", "pass-with-minors"):
        return RetryOutcome(
            final_returncode=retry_rc,
            final_decision=retry_decision,
            retried=True,
            escalation_path=None,
        )

    esc_path = write_retry_failed_escalation(
        ticket_id=req.ticket_id,
        session_id=retry_session_id,
        worktree_path=req.worktree_path,
        dispatch_file=dispatch_file,
        decision_first=initial_decision,
        decision_second=retry_decision or "(no verifier output)",
        escalation_dir=config.escalation_dir,
        retried=True,
        now=(now_factory() if now_factory else None),
    )
    return RetryOutcome(
        final_returncode=retry_rc,
        final_decision=retry_decision,
        retried=True,
        escalation_path=esc_path,
    )
