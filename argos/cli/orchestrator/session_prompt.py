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

from argos.cli.orchestrator import independence

__all__ = [
    "DEFAULT_PERMISSION_ARG",
    "STANDING_RULES",
    "build_prompt",
    "build_prompt_for_ticket",
]


# The permission mode used for headless dispatch (ARG1-069 AC#2; flag
# confirmed present in ``claude --help``).
DEFAULT_PERMISSION_ARG = "--dangerously-skip-permissions"


# The standing per-ticket rules, codified verbatim per ARG1-069 AC#1. Every
# dispatched session is bound by these regardless of the ticket's own text.
# Each rule names the literal token (ADR-001, ADR-002, `argos state-append`,
# STATE.md, merge, escalation.md) that downstream consumers and tests grep for.
STANDING_RULES = (
    "Implementation is Python >=3.9, standard library only (ADR-001). "
    "Do not add any third-party runtime dependency; that is an ADR-level "
    "decision, not yours to make.",
    "Acceptance-criteria tooling is standard library only as well (ADR-002). "
    "Every AC command must run under a fresh python3 >=3.9 with no "
    "`pip install` step.",
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
) -> str:
    """Return the complete headless prompt string for ``ticket_id``.

    Pure: no filesystem access, no subprocess. The returned string contains
    the ticket id, the standing rules (:data:`STANDING_RULES`), an
    instruction to read the ticket and implement it, and — when supplied —
    the ticket's full text inlined between fenced markers.

    ``ticket_text`` is the ticket file's full contents. When it is ``None``
    or blank (the file could not be located in the worktree), the prompt
    instead instructs the session to read the ticket from ``ticket_path``
    (or the canonical tickets directory) before implementing.
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
        "Standing rules (binding on every Argos session, regardless of the "
        "ticket text):",
    ]
    for index, rule in enumerate(STANDING_RULES, start=1):
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


def build_prompt_for_ticket(
    ticket_id: str,
    *,
    ticket_dir: Path | str,
) -> str:
    """Locate ``ticket_id`` under ``ticket_dir``, read it, and build the prompt.

    Thin I/O wrapper over :func:`build_prompt`. ``ticket_dir`` is the tickets
    directory inside the worktree (e.g.
    ``<worktree>/argos/specs/v1.0/tickets``). If the ticket file cannot be
    located or read (it is absent from this branch, or the worktree predates
    it), the prompt degrades gracefully to a read-the-file instruction rather
    than failing the spawn — the session still gets the id and the rules.
    """
    try:
        path = independence.find_ticket_path(ticket_id, ticket_dir)
        text = path.read_text(encoding="utf-8")
        return build_prompt(ticket_id, text, ticket_path=path)
    except (independence.IndependenceError, OSError):
        return build_prompt(ticket_id, None, ticket_path=Path(ticket_dir))
