"""``argos queue`` — add or remove a ticket bullet in STATE.md's ``## Queue``.

Usage::

    argos queue add ARG1-099       # add a "- ARG1-099" bullet (idempotent)
    argos queue remove ARG1-099    # remove it (no-op if absent)
    argos queue add ARG1-099 --state-file path/to/STATE.md

The STATE.md path is auto-detected via the shared resolver (ARG1-075), so the
command works on both argos's own ``argos/specs/v1.0/`` tree and a flat
``init``-scaffolded ``argos/specs/`` repo with no flags.

EDIT-ONLY: this command writes the working-tree STATE.md and does NOT stage or
commit — exactly like ``argos state-append``. The operator commits. Because the
written change is a plain ``## Queue`` bullet, the ARG1-078 pre-commit hook
accepts it without the ``ARGOS_CYCLE_CLOSE`` bypass.

The bullet format (``- <TICKET-ID>``) round-trips through
:func:`argos.cli.queue.parse_queue`. Standard library only — ADR-001 / ADR-002.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from argos.cli.queue import TICKET_ID_RE
from argos.cli.spec_paths import default_state_file

__all__ = ["main"]

# A queue heading is the level-2 heading whose text is exactly ``Queue``; the
# section runs until the next level-2 heading. Mirrors argos.cli.queue.
_QUEUE_HEADING_RE = re.compile(r"^## Queue\s*$")
_NEXT_HEADING_RE = re.compile(r"^## ")
_BULLET_RE = re.compile(r"^\s*-\s+(?P<body>.*\S)\s*$")


class QueueEditError(Exception):
    """A STATE.md the queue editor cannot operate on (missing file/section)."""


def _bullet_ticket_id(line: str) -> str | None:
    """Return the ticket id of a queue bullet line, or ``None`` if not one."""
    m = _BULLET_RE.match(line)
    if not m:
        return None
    head = m.group("body").split(None, 1)[0]
    return head if TICKET_ID_RE.match(head) else None


def _queue_bounds(lines: list[str]) -> tuple[int, int]:
    """Return ``(start, end)`` line indices of the ``## Queue`` body.

    ``start`` is the first line after the heading; ``end`` is the index of the
    next level-2 heading (or ``len(lines)``). Raises :class:`QueueEditError`
    when there is no ``## Queue`` heading.
    """
    queue_idx = next(
        (i for i, ln in enumerate(lines) if _QUEUE_HEADING_RE.match(ln)), -1
    )
    if queue_idx == -1:
        raise QueueEditError("STATE.md has no '## Queue' section")
    end = len(lines)
    for i in range(queue_idx + 1, len(lines)):
        if _NEXT_HEADING_RE.match(lines[i]):
            end = i
            break
    return queue_idx + 1, end


def _add(lines: list[str], ticket_id: str) -> tuple[bool, str]:
    """Add a ``- <ticket_id>`` bullet to ## Queue. Idempotent.

    Returns ``(changed, message)``.
    """
    start, end = _queue_bounds(lines)
    for i in range(start, end):
        if _bullet_ticket_id(lines[i]) == ticket_id:
            return False, f"{ticket_id} already in queue (no change)"

    bullet_idxs = [i for i in range(start, end) if _BULLET_RE.match(lines[i])]
    if bullet_idxs:
        insert_at = bullet_idxs[-1] + 1
    else:
        # Empty section: insert after the heading, keeping the blank line that
        # conventionally follows a heading.
        insert_at = start
        if insert_at < end and lines[insert_at].strip() == "":
            insert_at += 1
    lines.insert(insert_at, f"- {ticket_id}")
    return True, f"queued {ticket_id}"


def _remove(lines: list[str], ticket_id: str) -> tuple[bool, str]:
    """Remove every ``- <ticket_id>`` bullet from ## Queue.

    Returns ``(changed, message)``. A non-present id is a clear no-op.
    """
    start, end = _queue_bounds(lines)
    keep = [
        lines[i]
        for i in range(start, end)
        if _bullet_ticket_id(lines[i]) != ticket_id
    ]
    if len(keep) == len(range(start, end)):
        return False, f"{ticket_id} not in queue (no change)"
    lines[start:end] = keep
    return True, f"removed {ticket_id} from queue"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argos queue",
        description=(
            "Add or remove a ticket bullet in STATE.md's '## Queue' section. "
            "Edits the working tree only (the operator commits)."
        ),
    )
    sub = parser.add_subparsers(dest="action", required=True, metavar="add|remove")
    for verb, helptext in (
        ("add", "add a '- <TICKET-ID>' bullet to ## Queue (idempotent)"),
        ("remove", "remove a '- <TICKET-ID>' bullet from ## Queue (no-op if absent)"),
    ):
        p = sub.add_parser(verb, help=helptext)
        p.add_argument("ticket_id", help="ticket id, e.g. ARG1-099")
        p.add_argument(
            "--state-file",
            default=None,
            help=(
                "path to STATE.md (default: auto-detected — "
                "argos/specs/v1.0/STATE.md if present, else argos/specs/STATE.md)"
            ),
        )
    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    if not TICKET_ID_RE.match(args.ticket_id):
        sys.stderr.write(
            f"queue: not a ticket id: {args.ticket_id!r} "
            "(expected e.g. ARG1-099)\n"
        )
        return 2

    state_file = Path(args.state_file or default_state_file())
    if not state_file.exists():
        sys.stderr.write(f"queue: STATE.md not found: {state_file}\n")
        return 1

    text = state_file.read_text(encoding="utf-8")
    lines = text.splitlines()

    try:
        if args.action == "add":
            changed, message = _add(lines, args.ticket_id)
        else:
            changed, message = _remove(lines, args.ticket_id)
    except QueueEditError as exc:
        sys.stderr.write(f"queue: {exc}\n")
        return 1

    if changed:
        state_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.write(message + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
