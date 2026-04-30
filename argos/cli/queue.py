"""STATE.md ``## Queue`` section parser (ARG1-011).

Reads the ``## Queue`` section of an argos STATE.md file and extracts ticket
ids in source order. Used by the ``argos orchestrate`` entry point
(:mod:`argos.cli.commands.orchestrate`) to surface the next batch of
tickets the orchestrator agent will dispatch.

The Queue section is a plain markdown list. Each ticket entry sits on its
own line as a bullet item that begins with the ticket id, e.g.::

    ## Queue

    - ARG1-022 — independence detection (P0)
    - ARG1-013 — auto-fix retry loop (P1)

Lines that are not bullet items, or bullet items whose first token is not a
ticket-id-shaped string, are ignored. This makes placeholder text such as
``_(populated as tickets are queued for dispatch; orchestrator reads this
section)_`` a no-op rather than a parse error.

Standard library only — :mod:`re` and :mod:`pathlib` are the only imports
(ADR-001 / ADR-002).
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = [
    "QueueError",
    "StateFileNotFoundError",
    "QueueSectionMissingError",
    "TICKET_ID_RE",
    "parse_queue",
    "parse_queue_file",
]


# Ticket ids look like ``ARG-001`` or ``ARG1-022`` — uppercase letters + an
# optional digit run, then a dash, then digits. Anchored to the start of a
# bullet body so we do not pick up ticket ids embedded in trailing prose.
TICKET_ID_RE = re.compile(r"^[A-Z]+\d*-\d+$")

# Match a markdown list bullet at the start of a line (allowing leading
# indentation). Captures the bullet body (everything after the dash + space).
_BULLET_RE = re.compile(r"^\s*-\s+(?P<body>.*\S)\s*$")

# A queue heading is a level-2 markdown heading whose text is exactly
# ``Queue``. Trailing whitespace tolerated; leading whitespace not.
_QUEUE_HEADING_RE = re.compile(r"^## Queue\s*$")

# Any level-2 heading. Used to bound the section.
_NEXT_HEADING_RE = re.compile(r"^## ")


class QueueError(Exception):
    """Base class for queue-parser errors."""


class StateFileNotFoundError(QueueError):
    """The STATE.md file does not exist on disk.

    Carries the substring ``STATE.md not found`` in ``str(self)`` so AC text
    can grep for it without coupling to the exact path.
    """


class QueueSectionMissingError(QueueError):
    """The STATE.md file exists but contains no ``## Queue`` heading.

    Distinct from "queue empty" — the latter is a successful parse that
    returns an empty list. This error indicates a malformed STATE.md.
    """


def _extract_ticket_id(bullet_body: str) -> str | None:
    """Return the ticket id at the start of ``bullet_body``, or ``None``.

    The first whitespace-delimited token is tested against
    :data:`TICKET_ID_RE`. Returns the id verbatim on a match; ``None``
    otherwise (so non-ticket bullets are silently skipped).
    """
    head = bullet_body.split(None, 1)[0] if bullet_body else ""
    if TICKET_ID_RE.match(head):
        return head
    return None


def parse_queue(text: str) -> list[str]:
    """Return the ticket ids listed in ``## Queue`` in source order.

    An empty list is a valid successful return value when the section
    exists but contains no ticket-shaped bullets.

    Raises:
        QueueSectionMissingError: ``## Queue`` heading absent.
    """
    lines = text.splitlines()

    queue_idx = -1
    for idx, line in enumerate(lines):
        if _QUEUE_HEADING_RE.match(line):
            queue_idx = idx
            break

    if queue_idx == -1:
        raise QueueSectionMissingError("STATE.md has no '## Queue' section")

    ticket_ids: list[str] = []
    for idx in range(queue_idx + 1, len(lines)):
        line = lines[idx]
        if _NEXT_HEADING_RE.match(line):
            break
        m = _BULLET_RE.match(line)
        if not m:
            continue
        ticket_id = _extract_ticket_id(m.group("body"))
        if ticket_id is not None:
            ticket_ids.append(ticket_id)

    return ticket_ids


def parse_queue_file(path: str | Path) -> list[str]:
    """Read ``path`` as UTF-8 and parse its ``## Queue`` section.

    Raises:
        StateFileNotFoundError: ``path`` does not exist.
        QueueSectionMissingError: file exists but has no ``## Queue`` heading.
    """
    p = Path(path)
    if not p.exists():
        raise StateFileNotFoundError(f"STATE.md not found: {p}")
    return parse_queue(p.read_text(encoding="utf-8"))
