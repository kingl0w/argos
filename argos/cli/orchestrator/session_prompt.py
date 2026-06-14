"""Build the headless instruction prompt for a dispatched session (ARG1-069).

``spawn_session`` (ARG1-020) runs the Claude Code harness headlessly::

    claude -p "<prompt>" --dangerously-skip-permissions

Without a prompt the spawned session lands in a fresh worktree with no
instruction — the gap this ticket closes. This module assembles that prompt
from the ticket file plus the standing argos rules every dispatched session is
bound by.

The builder is pure (strings in, string out) so it is unit-testable without a
live ``claude`` invocation; :func:`build_prompt_for_ticket` is the thin I/O
wrapper that locates and reads the ticket file.

ADR-001: Python ≥3.9, stdlib only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from argos.cli import escalation
from argos.cli.orchestrator import independence

__all__ = [
    "DEFAULT_PERMISSION_ARG",
    "CONVENTIONS_REL",
    "CONTRACT_RULES",
    "MissingConventionsError",
    "build_prompt",
    "build_prompt_for_ticket",
]


# The permission mode used for headless dispatch (ARG1-069 AC#2; flag
# confirmed present in ``claude --help``).
DEFAULT_PERMISSION_ARG = "--dangerously-skip-permissions"


# Where the target repo's conventions live, relative to the target root. These
# are the *target* repo's language / dependency / test conventions, sourced
# from the repo under work rather than hardcoded into argos.
CONVENTIONS_REL = Path("argos") / "conventions.md"


# The Argos-contract rules, binding on every dispatched session regardless of
# the ticket's own text or the target repo. Unlike target conventions (which
# are read from the repo under work), these are part of the Argos protocol and
# stay hardcoded. Each rule names the literal token (`argos state-append`,
# STATE.md, merge, escalation.md) that downstream consumers and tests grep for.
CONTRACT_RULES = (
    "Verify every acceptance criterion before you commit. Run the AC "
    "commands via the shell and quote their real output -- never assert a "
    "check passed without having run it.",
    "All STATE.md writes go through `argos state-append` (e.g. "
    "`python3 -m argos.cli state-append --suffix done`). Never edit a "
    "STATE.md file directly.",
    "Push your work to origin/<branch> for the ticket's branch. Do NOT "
    "merge -- the orchestrator owns the merge decision.",
    "Escalate genuine ambiguity (a product or architecture call you cannot "
    "resolve from the ticket, the code, or sensible defaults) by writing an "
    "escalation file conforming to argos/specs/v1.0/schemas/escalation.md. "
    "Do not invent the decision.",
)


def build_prompt(
    ticket_id: str,
    ticket_text: Optional[str] = None,
    *,
    ticket_path: Optional[Path] = None,
    target_conventions: Optional[str] = None,
) -> str:
    """Return the complete headless prompt string for ``ticket_id``.

    Pure: no filesystem access, no subprocess. The returned string contains
    the ticket id, an instruction to read the ticket and implement it, the
    Argos-contract rules (:data:`CONTRACT_RULES`), and — when supplied — the
    target repo's conventions and the ticket's full text inlined between
    fenced markers.

    ``ticket_text`` is the ticket file's full contents. When it is ``None``
    or blank (the file could not be located in the worktree), the prompt
    instead instructs the session to read the ticket from ``ticket_path``
    (or the canonical tickets directory) before implementing.

    ``target_conventions`` is the verbatim text of the target repo's
    ``argos/conventions.md`` (language / dependency / test conventions sourced
    from the repo under work). When it is ``None`` or blank the conventions
    section is omitted entirely; when present it is inlined ahead of the
    contract rules.
    """
    if not ticket_id:
        raise ValueError("ticket_id must be non-empty")

    lines: list[str] = [
        f"You are an autonomous Argos coding session for ticket {ticket_id}.",
        "",
        "Read the ticket specification below and implement it end to end: "
        "plan, write the code and its tests, verify, and push. Stay strictly "
        "within the ticket's scope -- file a new ticket for anything else.",
        "",
    ]

    conventions = (target_conventions or "").strip()
    if conventions:
        lines.append("Target conventions (from this repo):")
        lines.append(conventions)
        lines.append("")

    lines.append(
        "Standing rules (binding on every Argos session, regardless of the "
        "ticket text):"
    )
    for index, rule in enumerate(CONTRACT_RULES, start=1):
        lines.append(f"{index}. {rule}")
    lines.append("")

    body = (ticket_text or "").strip()
    if body:
        lines.append(f"--- BEGIN TICKET {ticket_id} ---")
        lines.append(body)
        lines.append(f"--- END TICKET {ticket_id} ---")
    else:
        where = str(ticket_path) if ticket_path else "argos/specs/v1.0/tickets/"
        lines.append(
            f"Read the full specification for {ticket_id} from {where} "
            "before implementing."
        )

    return "\n".join(lines) + "\n"


class MissingConventionsError(Exception):
    """The target repo's ``argos/conventions.md`` is missing or empty.

    Raised by :func:`build_prompt_for_ticket` after a blocking escalation has
    been written, so the caller aborts the spawn rather than dispatching a
    session with no target conventions. ``escalation_path`` is the file the
    writer produced.
    """

    def __init__(
        self,
        ticket_id: str,
        conventions_path: Path,
        escalation_path: Path,
    ) -> None:
        self.ticket_id = ticket_id
        self.conventions_path = conventions_path
        self.escalation_path = escalation_path
        super().__init__(
            f"target conventions missing or empty for {ticket_id}: "
            f"{conventions_path} (blocking escalation written to "
            f"{escalation_path})"
        )


def _compose_missing_conventions_body(
    ticket_id: str, conventions_path: Path
) -> str:
    """Escalation body (four required H2 sections per the escalation schema)."""
    return (
        "## Question\n\n"
        f"Dispatch for {ticket_id} requires the target repo's conventions at "
        f"`{conventions_path}`, but the file is missing or empty. Should the "
        "operator populate it before this ticket is dispatched?\n\n"
        "## Context\n\n"
        "Argos sources each session's language / dependency / test "
        "conventions from the target repo (`argos/conventions.md`) rather "
        "than hardcoding them. The file was absent or blank at dispatch "
        "time, so the session would otherwise have run with no target "
        "conventions.\n\n"
        "## Options considered\n\n"
        f"- Block dispatch and ask the operator to fill in `{conventions_path}` "
        "(chosen — this escalation).\n"
        "- Dispatch with no conventions (rejected — silent, drops the target "
        "repo's binding constraints).\n\n"
        "## Why escalated\n\n"
        "Whether to proceed without conventions is an operator decision, not "
        "one the orchestrator may make silently.\n"
    )


def build_prompt_for_ticket(
    ticket_id: str,
    *,
    ticket_dir: Path | str,
    target_root: Path | str,
    escalation_dir: Optional[Path | str] = None,
) -> str:
    """Locate ``ticket_id`` under ``ticket_dir``, read it, and build the prompt.

    I/O wrapper over :func:`build_prompt`. ``ticket_dir`` is the tickets
    directory inside the worktree (e.g.
    ``<worktree>/argos/specs/v1.0/tickets``). ``target_root`` is the root of
    the repo under work (the worktree checkout); the target conventions are
    read from ``<target_root>/argos/conventions.md`` and inlined into the
    prompt.

    If that conventions file is **missing or empty**, this does not dispatch
    silently: it writes a blocking escalation (via the same
    :func:`argos.cli.escalation.write_escalation` writer the orchestrator uses
    elsewhere) into ``escalation_dir`` — defaulting to
    ``<target_root>/argos/specs/escalations`` — and raises
    :class:`MissingConventionsError` to surface the condition to the caller.

    If the ticket file itself cannot be located or read (it is absent from
    this branch, or the worktree predates it), the prompt degrades gracefully
    to a read-the-file instruction rather than failing the spawn — the session
    still gets the id, the conventions, and the rules.
    """
    conventions_path = Path(target_root) / CONVENTIONS_REL
    try:
        conventions_text = conventions_path.read_text(encoding="utf-8")
    except OSError:
        conventions_text = ""
    if not conventions_text.strip():
        if escalation_dir is None:
            dest_dir = Path(target_root) / escalation.DEFAULT_ESCALATION_DIR
        else:
            dest_dir = Path(escalation_dir)
        escalation_path = escalation.write_escalation(
            ticket_id=ticket_id,
            severity="blocking",
            raised_by="orchestrator",
            body=_compose_missing_conventions_body(ticket_id, conventions_path),
            dest_dir=dest_dir,
        )
        raise MissingConventionsError(
            ticket_id, conventions_path, escalation_path
        )

    try:
        path = independence.find_ticket_path(ticket_id, ticket_dir)
        text = path.read_text(encoding="utf-8")
        return build_prompt(
            ticket_id, text, ticket_path=path, target_conventions=conventions_text
        )
    except (independence.IndependenceError, OSError):
        return build_prompt(
            ticket_id,
            None,
            ticket_path=Path(ticket_dir),
            target_conventions=conventions_text,
        )
