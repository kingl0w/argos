"""File-overlap independence detection (ARG1-021).

Implements the v1.0 independence criterion specified by:

- ``argos/specs/v1.0/ARCHITECTURE.md`` §Components/Parallel Session Manager
  / Independence detection (file-scope analysis)
- ``argos/specs/v1.0/agents/orchestrator.md`` §Parallel dispatch behavior
- ``argos/specs/v1.0/tickets/ARG1-021-independence-detection.md`` §Intent

**Criterion (strict, exact wording from the three sources above).** Two
tickets A and B are independent iff:

1. Neither lists the other in ``depends_on:`` ticket frontmatter
   (transitively across the candidate batch).
2. Their declared ``files_touched:`` sets — read from the ``## Plan``
   section the planner appends to each ticket — are pairwise disjoint.

Both conditions must hold. If either is unknown or ambiguous (e.g. a
ticket has no parsed Plan section, or its Plan section omits the
``files_touched:`` field), the parser raises and the orchestrator falls
back to serial dispatch (per ARCHITECTURE.md §Invariants line 274:
"degraded but correct").

**What this module does NOT model.** Per ARG1-021 §Non-goals:

- No directory-prefix overlap heuristics.
- No import-graph analysis.
- No content-aware merge-strategy carve-outs (e.g. shared registration
  files like ``argos/cli/__main__.py`` that auto-merge cleanly under the
  "keep both registrations" pattern). Two parallel tickets touching such
  a file are reported as **dependent** by this module even when, in
  practice, the merge would succeed. Relaxing this is an
  ARCHITECTURE.md change, not an ARG1-021 change. See escalation
  ARG1-021-2026-05-02 for the audit trail.
- No dynamic re-evaluation mid-batch.

Standard library only — :mod:`re`, :mod:`json`, :mod:`pathlib`,
:mod:`dataclasses`, :mod:`typing` (ADR-001 / ADR-002).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

__all__ = [
    "IndependenceError",
    "TicketParseError",
    "TicketNotFoundError",
    "MissingFilesTouchedError",
    "Ticket",
    "PairResult",
    "load_ticket",
    "find_ticket_path",
    "is_independent",
    "partition",
    "DEFAULT_TICKET_DIR",
]


DEFAULT_TICKET_DIR = "argos/specs/v1.0/tickets"


# Frontmatter delimiter — three dashes on their own line per ADR-002 §1.
_FRONTMATTER_DELIM_RE = re.compile(r"^---\s*$")

# A top-level frontmatter key: alphanumeric/underscore/dash, ``:``, then
# either end-of-line (block-sequence value) or whitespace + value.
_FM_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:(?:\s+(?P<inline>.+))?\s*$")

# A block-sequence item: any indentation, then ``- item``.
_FM_BLOCK_ITEM_RE = re.compile(r"^\s+-\s+(?P<item>.+?)\s*$")

# A flow-style sequence: ``[a, b, c]``. Items are comma-separated with
# optional whitespace; quotes around items are tolerated and stripped.
_FLOW_SEQ_RE = re.compile(r"^\[(?P<body>.*)\]\s*$")

# A ``## Plan`` heading — H2 whose text is exactly ``Plan``.
_PLAN_HEADING_RE = re.compile(r"^##\s+Plan\s*$")
# Any H2 heading; used to bound the Plan section.
_NEXT_H2_RE = re.compile(r"^##\s")

# In-Plan ``files_touched:`` opener. Permits leading indentation so the
# field can appear inside a sub-bullet, but the canonical form is at
# column zero.
_FILES_TOUCHED_OPENER_RE = re.compile(r"^(?P<indent>\s*)files_touched\s*:\s*(?P<inline>.*)$")

# Block-sequence item under ``files_touched:`` — must be indented strictly
# deeper than the opener line. Captures the indent length so we can
# detect when the sequence ends.
_PLAN_BLOCK_ITEM_RE = re.compile(r"^(?P<indent>\s+)-\s+(?P<item>.+?)\s*$")

# Ticket id shape — uppercase letters, optional digits, dash, digits.
# Mirrors ``argos.cli.queue.TICKET_ID_RE`` (kept local so the modules do
# not couple).
_TICKET_ID_RE = re.compile(r"^[A-Z]+\d*-\d+$")


class IndependenceError(Exception):
    """Base class for independence-detection errors."""


class TicketParseError(IndependenceError):
    """A ticket file could not be parsed as a ticket.

    Carries ``ticket_id`` so callers can name the offending ticket in
    operator-facing diagnostics.
    """

    def __init__(self, ticket_id: str, reason: str) -> None:
        self.ticket_id = ticket_id
        self.reason = reason
        super().__init__(f"{ticket_id}: {reason}")


class TicketNotFoundError(IndependenceError):
    """No ticket file matches the requested ticket id."""

    def __init__(self, ticket_id: str, ticket_dir: Path) -> None:
        self.ticket_id = ticket_id
        self.ticket_dir = ticket_dir
        super().__init__(
            f"ticket not found: {ticket_id} (looked in {ticket_dir})"
        )


class MissingFilesTouchedError(TicketParseError):
    """A ticket's Plan section is present but lacks ``files_touched:``.

    The error message contains the literal substring
    ``missing files_touched`` so AC text can grep for it without coupling
    to the exact phrasing.
    """

    def __init__(self, ticket_id: str) -> None:
        super().__init__(
            ticket_id, "missing files_touched in ## Plan section"
        )


@dataclass(frozen=True)
class Ticket:
    """A ticket as far as the independence detector is concerned.

    Only the three fields the criterion consumes are loaded:
    ``ticket_id``, ``depends_on``, and ``files_touched``. Other ticket
    content (Intent, ACs, Plan body) is not modeled.
    """

    ticket_id: str
    path: Path
    depends_on: tuple[str, ...]
    files_touched: tuple[str, ...]


@dataclass(frozen=True)
class PairResult:
    """The result of comparing two tickets for independence.

    Returned by :func:`is_independent` so callers can render both the
    boolean answer and the human-readable reason without re-running the
    check. ``reason`` is empty when ``independent`` is ``True``.
    """

    a: str
    b: str
    independent: bool
    reason: str = ""
    shared_files: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Ticket file location + parsing
# ---------------------------------------------------------------------------


def find_ticket_path(ticket_id: str, ticket_dir: str | Path = DEFAULT_TICKET_DIR) -> Path:
    """Return the on-disk path for ``ticket_id`` under ``ticket_dir``.

    Tickets are named ``{ticket_id}-{slug}.md`` (precedent: every ticket
    under ``argos/specs/v1.0/tickets/``); a bare ``{ticket_id}.md`` is
    also accepted for synthetic test fixtures.
    """
    tdir = Path(ticket_dir)
    candidates = sorted(tdir.glob(f"{ticket_id}*.md"))
    candidates = [
        p for p in candidates
        if p.stem == ticket_id or p.stem.startswith(f"{ticket_id}-")
    ]
    if not candidates:
        raise TicketNotFoundError(ticket_id, tdir)
    if len(candidates) > 1:
        raise TicketParseError(
            ticket_id,
            "multiple ticket files match: "
            + ", ".join(p.name for p in candidates),
        )
    return candidates[0]


def _parse_flow_sequence(body: str) -> list[str]:
    """Parse a flow-style sequence body — the contents between ``[`` and ``]``.

    Items are comma-separated. Surrounding whitespace and matched single
    or double quotes around each item are stripped. Empty body returns
    an empty list.
    """
    body = body.strip()
    if not body:
        return []
    items: list[str] = []
    for raw in body.split(","):
        item = raw.strip()
        if (
            len(item) >= 2
            and item[0] == item[-1]
            and item[0] in ("'", '"')
        ):
            item = item[1:-1]
        if item:
            items.append(item)
    return items


def _parse_frontmatter_depends_on(text: str) -> list[str]:
    """Return the ``depends_on`` ticket ids from a ticket file's frontmatter.

    Returns an empty list when the field is absent or the file has no
    frontmatter. Tolerates both block-sequence form (canonical for
    ADR-002) and flow-style form ``[A, B]`` (the literal example used in
    ARG1-021 AC#3). Other YAML constructs are not interpreted.
    """
    lines = text.splitlines()
    if not lines or not _FRONTMATTER_DELIM_RE.match(lines[0]):
        return []

    # Find the closing delimiter.
    end = -1
    for idx in range(1, len(lines)):
        if _FRONTMATTER_DELIM_RE.match(lines[idx]):
            end = idx
            break
    if end == -1:
        return []

    idx = 1
    while idx < end:
        line = lines[idx]
        if not line.strip() or line.lstrip().startswith("#"):
            idx += 1
            continue
        m = _FM_KEY_RE.match(line)
        if not m or m.group(1) != "depends_on":
            idx += 1
            continue
        inline = m.group("inline")
        if inline is not None:
            inline = inline.strip()
            if not inline:
                return []
            flow = _FLOW_SEQ_RE.match(inline)
            if flow:
                return _parse_flow_sequence(flow.group("body"))
            # Inline scalar — single ticket id (rare; tolerated).
            return [inline]
        # Block sequence: collect indented ``- item`` lines until a non
        # block-item line.
        items: list[str] = []
        cursor = idx + 1
        while cursor < end:
            sub = lines[cursor]
            if not sub.strip():
                cursor += 1
                continue
            mi = _FM_BLOCK_ITEM_RE.match(sub)
            if not mi:
                break
            items.append(mi.group("item").strip())
            cursor += 1
        return items

    return []


def _extract_plan_section(text: str) -> str | None:
    """Return the body of the ``## Plan`` section, or ``None`` if absent.

    The Plan section runs from the line after ``## Plan`` up to (but not
    including) the next ``## `` heading or end-of-file.
    """
    lines = text.splitlines()
    start = -1
    for idx, line in enumerate(lines):
        if _PLAN_HEADING_RE.match(line):
            start = idx + 1
            break
    if start == -1:
        return None
    end = len(lines)
    for idx in range(start, len(lines)):
        if _NEXT_H2_RE.match(lines[idx]):
            end = idx
            break
    return "\n".join(lines[start:end])


def _parse_plan_files_touched(plan_body: str) -> list[str] | None:
    """Return the ``files_touched:`` list from a Plan section body.

    Returns ``None`` if the field is absent. An empty list is a valid
    return value (a ticket may declare no files touched, e.g. a spec-only
    ticket).
    """
    lines = plan_body.splitlines()
    for idx, line in enumerate(lines):
        m = _FILES_TOUCHED_OPENER_RE.match(line)
        if not m:
            continue
        opener_indent = len(m.group("indent"))
        inline = m.group("inline").strip()
        if inline:
            flow = _FLOW_SEQ_RE.match(inline)
            if flow:
                return _parse_flow_sequence(flow.group("body"))
            # Single inline scalar — accept as one entry.
            return [inline]
        # Block sequence — collect indented ``- item`` lines until a
        # less-or-equal-indented non-blank line appears.
        items: list[str] = []
        for sub in lines[idx + 1 :]:
            if not sub.strip():
                continue
            mi = _PLAN_BLOCK_ITEM_RE.match(sub)
            if not mi:
                break
            indent = len(mi.group("indent"))
            if indent <= opener_indent:
                break
            items.append(mi.group("item").strip())
        return items
    return None


def load_ticket(
    ticket_id: str,
    ticket_dir: str | Path = DEFAULT_TICKET_DIR,
) -> Ticket:
    """Load a ticket file and extract its independence-relevant fields.

    Raises:
        TicketNotFoundError: no ticket file matches ``ticket_id``.
        MissingFilesTouchedError: ticket exists but its Plan section
            lacks ``files_touched:`` (or the Plan section is absent).
        TicketParseError: structural problem reading the ticket.
    """
    if not _TICKET_ID_RE.match(ticket_id):
        raise TicketParseError(ticket_id, "not a ticket-shaped id")
    path = find_ticket_path(ticket_id, ticket_dir)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TicketParseError(ticket_id, f"read error: {exc}") from exc

    depends_on = _parse_frontmatter_depends_on(text)
    plan_body = _extract_plan_section(text)
    if plan_body is None:
        raise MissingFilesTouchedError(ticket_id)
    files = _parse_plan_files_touched(plan_body)
    if files is None:
        raise MissingFilesTouchedError(ticket_id)

    return Ticket(
        ticket_id=ticket_id,
        path=path,
        depends_on=tuple(depends_on),
        files_touched=tuple(files),
    )


# ---------------------------------------------------------------------------
# Independence criterion
# ---------------------------------------------------------------------------


def is_independent(a: Ticket, b: Ticket) -> PairResult:
    """Decide whether two tickets are independent for parallel dispatch.

    The criterion is exactly the ARCHITECTURE.md §Independence detection
    + orchestrator-agent definition: depends_on is checked first (so the
    reason string is deterministic when both conditions would fail), then
    file-set disjointness.
    """
    if a.ticket_id == b.ticket_id:
        return PairResult(
            a.ticket_id,
            b.ticket_id,
            independent=False,
            reason="same ticket",
        )
    if b.ticket_id in a.depends_on or a.ticket_id in b.depends_on:
        return PairResult(
            a.ticket_id,
            b.ticket_id,
            independent=False,
            reason="depends_on",
        )
    shared = sorted(set(a.files_touched) & set(b.files_touched))
    if shared:
        return PairResult(
            a.ticket_id,
            b.ticket_id,
            independent=False,
            reason="shared file: " + ", ".join(shared),
            shared_files=tuple(shared),
        )
    return PairResult(a.ticket_id, b.ticket_id, independent=True)


def partition(tickets: Iterable[Ticket]) -> list[list[str]]:
    """Greedy partition of tickets into independence groups.

    Each returned group is a list of ticket ids whose pairwise
    :func:`is_independent` checks all return ``independent=True``. The
    partition is locally maximal under the input ordering: the
    first-fit greedy adds each ticket to the earliest group that accepts
    it, and only opens a new group when no existing group does.

    Determinism: input order is preserved; same input always yields the
    same partition. Optimality (minimum number of groups) is not
    guaranteed — graph-coloring is NP-hard in general, and v1.0 favors a
    simple, predictable partition over an optimal one. ARG1-022's
    ``max_parallel`` cap further bounds group size at dispatch time.
    """
    tickets = list(tickets)
    groups: list[list[Ticket]] = []
    for t in tickets:
        placed = False
        for grp in groups:
            if all(is_independent(t, other).independent for other in grp):
                grp.append(t)
                placed = True
                break
        if not placed:
            groups.append([t])
    return [[t.ticket_id for t in grp] for grp in groups]
