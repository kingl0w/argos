"""``argos attend`` — drain the operator escalation queue (ARG1-005).

Reads every file under ``argos/specs/escalations/``, presents each pending
escalation to the operator one at a time (chronological order by the
frontmatter ``created`` field), captures a free-form decision, appends that
decision to the originating ticket's ``## Decisions`` section, and removes the
escalation file.

Modes::

    argos attend                 # drain: prompt per escalation, record, remove
    argos attend --list          # show pending escalations, no prompting
    argos attend --ticket ARG-NN # restrict to one ticket's escalations

A "pending" escalation is a file whose body has **no** ``## Resolution``
heading. Files that carry a ``## Resolution`` section are already-drained audit
trails (see ``argos/specs/escalations/README.md``) and are skipped — this is
what lets an escalations dir that still holds resolved files read as empty.

Exit codes:
- ``0`` — queue drained / listed cleanly (including the empty-queue case).
- ``1`` — a malformed escalation file was found, or a decision could not be
  recorded (e.g. the originating ticket file is missing). Per the ticket's
  no-partial-save non-goal, unresolved escalations are left in place.

Standard library only (ADR-001).
"""

from __future__ import annotations

import argparse
import datetime
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import IO, List, Optional, Tuple

from argos.cli import escalation_validator

DEFAULT_ESCALATIONS_DIR = Path("argos/specs/escalations")
DEFAULT_TICKETS_DIR = Path("argos/specs/tickets")

_RESOLUTION_HEADING = "## Resolution"
_DECISIONS_HEADING = "## Decisions"


@dataclass
class Escalation:
    """A single pending escalation parsed from disk."""

    path: Path
    ticket_id: str
    session_id: str
    severity: str
    raised_by: str
    created: str
    body: str


# ---------------------------------------------------------------------------
# Repo / path resolution (mirrors commands/escalate.py)
# ---------------------------------------------------------------------------


def _find_repo_root(start: Path) -> Optional[Path]:
    """Walk up from ``start`` looking for an Argos repo-root marker.

    Markers (any one): ``argos/specs/``, ``argos/config.toml``,
    ``argos/config.toml.template``. Returns the first match or ``None``.
    """
    cur = start.resolve()
    while True:
        if (cur / "argos" / "specs").is_dir():
            return cur
        if (cur / "argos" / "config.toml").is_file():
            return cur
        if (cur / "argos" / "config.toml.template").is_file():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def _resolve_dir(explicit: Optional[str], default: Path) -> Path:
    if explicit:
        return Path(explicit)
    root = _find_repo_root(Path.cwd())
    if root is None:
        return Path.cwd() / default
    return root / default


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


def _created_sort_key(value: str) -> Tuple[int, object]:
    """Chronological sort key for a frontmatter ``created`` string.

    Normalises a trailing ``Z`` to ``+00:00`` so ``datetime.fromisoformat``
    parses it on Python 3.9/3.10 (which, unlike 3.11+, reject ``Z``). Naive
    timestamps are assumed UTC. Unparseable values sort last, by raw string,
    without ever being compared against the parsed-datetime group.
    """
    norm = value.strip()
    if norm.endswith("Z"):
        norm = norm[:-1] + "+00:00"
    try:
        dt = datetime.datetime.fromisoformat(norm)
    except ValueError:
        return (1, value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return (0, dt.timestamp())


def _is_drained(body: str) -> bool:
    """True if ``body`` carries a ``## Resolution`` heading on its own line."""
    return any(line.strip() == _RESOLUTION_HEADING for line in body.splitlines())


def scan(
    escalations_dir: Path,
    ticket_filter: Optional[str] = None,
) -> Tuple[List[Escalation], List[str]]:
    """Scan ``escalations_dir`` for pending escalations.

    Returns ``(pending, malformed)`` where ``pending`` is the chronologically
    ordered list of :class:`Escalation` objects (filtered by ``ticket_filter``
    when given) and ``malformed`` is a list of ``"<path>: <reason>"`` strings
    for files that are not drained but fail to parse/validate.

    Drained files (those with a ``## Resolution`` section) are skipped silently
    — they are resolved audit trails, not pending work.
    """
    if not escalations_dir.is_dir():
        return [], []

    pending: List[Escalation] = []
    malformed: List[str] = []

    for path in sorted(escalations_dir.glob("*.md")):
        # The directory ships a README.md sentinel (see the escalations
        # README itself) — it documents the channel, it is not an escalation.
        if path.name.lower() == "readme.md":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            malformed.append(f"{path}: cannot read file: {exc}")
            continue

        try:
            fm, body = escalation_validator.parse_frontmatter(text)
        except ValueError as exc:
            malformed.append(f"{path}: cannot parse frontmatter: {exc}")
            continue

        if _is_drained(body):
            continue

        errors = escalation_validator.validate(path)
        if errors:
            malformed.append(f"{path}: {'; '.join(errors)}")
            continue

        ticket_id = fm["ticket_id"]
        if ticket_filter is not None and ticket_id != ticket_filter:
            continue

        pending.append(
            Escalation(
                path=path,
                ticket_id=ticket_id,
                session_id=fm["session_id"],
                severity=fm["severity"],
                raised_by=fm["raised_by"],
                created=fm["created"],
                body=body,
            )
        )

    pending.sort(key=lambda e: _created_sort_key(e.created))
    return pending, malformed


# ---------------------------------------------------------------------------
# Decision recording
# ---------------------------------------------------------------------------


class TicketNotFoundError(Exception):
    """The originating ticket file for an escalation could not be located."""


def _find_ticket_file(tickets_dir: Path, ticket_id: str) -> Path:
    matches = sorted(tickets_dir.glob(f"{ticket_id}-*.md"))
    exact = tickets_dir / f"{ticket_id}.md"
    if exact.is_file():
        matches.insert(0, exact)
    if not matches:
        raise TicketNotFoundError(
            f"no ticket file for {ticket_id} under {tickets_dir}"
        )
    return matches[0]


def _format_decision_entry(
    esc: Escalation, decision: str, now: datetime.datetime
) -> str:
    ts = now.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    decision_line = decision.strip()
    return (
        f"- **[{ts}]** {decision_line}\n"
        f"  - Escalation: `{esc.path.name}` "
        f"(severity {esc.severity}, raised_by {esc.raised_by}, "
        f"session {esc.session_id})"
    )


def _append_to_decisions_section(text: str, entry: str) -> str:
    """Return ``text`` with ``entry`` added to its ``## Decisions`` section.

    Creates the section at the end of the file if it does not exist. Within an
    existing section, the entry is inserted after the last non-blank line of
    that section (before the next ``## `` heading, or at EOF).
    """
    entry_block = entry.rstrip("\n")
    lines = text.splitlines()

    heading_idx: Optional[int] = None
    for i, line in enumerate(lines):
        if line.strip() == _DECISIONS_HEADING:
            heading_idx = i
            break

    if heading_idx is None:
        base = text.rstrip("\n")
        return f"{base}\n\n{_DECISIONS_HEADING}\n\n{entry_block}\n"

    end = len(lines)
    for j in range(heading_idx + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break

    insert_at = end
    while insert_at - 1 > heading_idx and lines[insert_at - 1].strip() == "":
        insert_at -= 1

    new_lines = lines[:insert_at] + ["", entry_block] + lines[insert_at:]
    result = "\n".join(new_lines)
    if not result.endswith("\n"):
        result += "\n"
    return result


def record_decision(
    tickets_dir: Path,
    esc: Escalation,
    decision: str,
    now: Optional[datetime.datetime] = None,
) -> Path:
    """Append ``decision`` to the originating ticket's ``## Decisions`` section.

    Returns the ticket path written. Raises :class:`TicketNotFoundError` when
    the ticket file is missing (the caller leaves the escalation in place).
    """
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    ticket_path = _find_ticket_file(tickets_dir, esc.ticket_id)
    text = ticket_path.read_text(encoding="utf-8")
    entry = _format_decision_entry(esc, decision, now)
    ticket_path.write_text(_append_to_decisions_section(text, entry), encoding="utf-8")
    return ticket_path


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------


def _empty_message(ticket_filter: Optional[str]) -> str:
    if ticket_filter is not None:
        return f"no pending escalations for {ticket_filter}\n"
    return "no pending escalations\n"


def _list_line(esc: Escalation) -> str:
    return f"{esc.ticket_id}  {esc.created}  {esc.severity}  {esc.path.name}\n"


def _present(esc: Escalation, out: IO[str]) -> None:
    out.write("\n")
    out.write("=" * 72 + "\n")
    out.write(
        f"{esc.ticket_id}  ({esc.severity}, raised_by {esc.raised_by}, "
        f"created {esc.created})\n"
    )
    out.write(f"file: {esc.path.name}\n")
    out.write("-" * 72 + "\n")
    out.write(esc.body.strip() + "\n")
    out.write("-" * 72 + "\n")
    out.write("decision> ")
    out.flush()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argos attend",
        description=(
            "Drain the escalation queue under argos/specs/escalations/: "
            "present each pending escalation, record the operator's decision "
            "in the ticket's Decisions section, and remove the file."
        ),
    )
    parser.add_argument(
        "--list",
        dest="list_only",
        action="store_true",
        help="show pending escalations without prompting for decisions",
    )
    parser.add_argument(
        "--ticket",
        default=None,
        help="restrict to escalations whose ticket_id matches (e.g. ARG1-099)",
    )
    parser.add_argument(
        "--dir",
        dest="escalations_dir",
        default=None,
        help="escalations directory (default: <repo>/argos/specs/escalations/)",
    )
    parser.add_argument(
        "--tickets-dir",
        dest="tickets_dir",
        default=None,
        help="tickets directory (default: <repo>/argos/specs/tickets/)",
    )
    return parser


def main(argv: List[str]) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    escalations_dir = _resolve_dir(args.escalations_dir, DEFAULT_ESCALATIONS_DIR)
    pending, malformed = scan(escalations_dir, args.ticket)

    if malformed:
        for line in malformed:
            sys.stderr.write(f"attend: malformed escalation: {line}\n")
        return 1

    if not pending:
        sys.stdout.write(_empty_message(args.ticket))
        return 0

    if args.list_only:
        for esc in pending:
            sys.stdout.write(_list_line(esc))
        return 0

    return _drain(pending, args.tickets_dir)


def _drain(pending: List[Escalation], tickets_dir_arg: Optional[str]) -> int:
    tickets_dir = _resolve_dir(tickets_dir_arg, DEFAULT_TICKETS_DIR)
    drained = 0
    had_error = False

    for esc in pending:
        _present(esc, sys.stdout)
        line = sys.stdin.readline()
        if line == "":
            # EOF: operator stopped early. Per the no-partial-save non-goal,
            # this and every remaining escalation stay in place.
            sys.stdout.write("\n")
            sys.stderr.write(
                "attend: input closed; remaining escalations left in place\n"
            )
            break

        decision = line.strip()
        if not decision:
            sys.stdout.write(f"skipped {esc.path.name} (no decision)\n")
            continue

        try:
            ticket_path = record_decision(tickets_dir, esc, decision)
        except TicketNotFoundError as exc:
            had_error = True
            sys.stderr.write(f"attend: {exc}; leaving {esc.path.name} in place\n")
            continue
        except OSError as exc:
            had_error = True
            sys.stderr.write(
                f"attend: cannot record decision for {esc.path.name}: {exc}; "
                "leaving it in place\n"
            )
            continue

        try:
            esc.path.unlink()
        except OSError as exc:
            had_error = True
            sys.stderr.write(
                f"attend: recorded decision in {ticket_path} but could not "
                f"remove {esc.path.name}: {exc}\n"
            )
            continue

        drained += 1
        sys.stdout.write(f"recorded decision for {esc.ticket_id} in {ticket_path}\n")

    sys.stdout.write(f"drained {drained} escalation(s)\n")
    return 1 if had_error else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
