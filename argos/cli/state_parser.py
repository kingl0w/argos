"""Reference parser for the argos v1.0 STATE.md append-mostly block schema.

See ``argos/specs/v1.0/schemas/state-block.md`` for the canonical schema.

Standard library only — no external runtime dependencies (``re``, ``dataclasses``,
``pathlib``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

__all__ = [
    "Block",
    "StateBlockError",
    "UnclosedEntryError",
    "DuplicateIdError",
    "MissingAttributeError",
    "MalformedOpenTagError",
    "parse",
    "parse_file",
]

REQUIRED_ATTRS = ("id", "ticket", "author", "session")

# Open tag like:
#   <!-- argos:entry id=... ticket=... author=... session=... -->
# Whitespace is permitted before/after the directive markers and between attrs.
_OPEN_TAG_RE = re.compile(r"^\s*<!--\s*argos:entry\s+(?P<attrs>.*?)\s*-->\s*$")
_CLOSE_TAG_RE = re.compile(r"^\s*<!--\s*/argos:entry\s*-->\s*$")
# Attribute pairs: key=value where value runs to next whitespace.
_ATTR_RE = re.compile(r"(\w+)=(\S+)")


class StateBlockError(Exception):
    """Base class for state-block schema violations."""


class UnclosedEntryError(StateBlockError):
    """An ``<!-- argos:entry ... -->`` open tag was not followed by a matching close before EOF."""


class DuplicateIdError(StateBlockError):
    """Two blocks in the same file declared the same ``id`` attribute value."""


class MissingAttributeError(StateBlockError):
    """An open tag was missing one of the four required attributes."""


class MalformedOpenTagError(StateBlockError):
    """An open tag's attribute syntax could not be parsed."""


@dataclass
class Block:
    """One parsed argos:entry block."""

    id: str
    ticket: str
    author: str
    session: str
    body: str
    start_line: int  # 1-indexed line of the open tag
    end_line: int    # 1-indexed line of the close tag

    def to_dict(self) -> dict:
        """JSON-serializable dict; preserves field order."""
        return asdict(self)


def _parse_attrs(attrs_text: str, line_no: int) -> dict:
    """Parse ``key=value`` pairs from an open-tag attribute string.

    Raises ``MalformedOpenTagError`` if no recognizable pairs are found in a
    non-empty attribute string.
    """
    pairs = _ATTR_RE.findall(attrs_text)
    if not pairs and attrs_text.strip():
        raise MalformedOpenTagError(
            f"line {line_no}: malformed open tag — could not parse attributes from "
            f"{attrs_text!r}"
        )
    return dict(pairs)


def parse(text: str) -> list[Block]:
    """Scan ``text`` and return the list of ``argos:entry`` blocks in source order.

    Raises:
        UnclosedEntryError: open tag with no matching close.
        DuplicateIdError: two blocks share the same ``id`` value.
        MissingAttributeError: open tag is missing one of the required attributes.
        MalformedOpenTagError: open tag attributes cannot be parsed.
    """
    blocks: list[Block] = []
    seen_ids: set[str] = set()

    in_block = False
    open_line_no = 0
    open_attrs: dict = {}
    body_lines: list[str] = []

    lines: Iterable[str] = text.splitlines()
    for idx, line in enumerate(lines, start=1):
        if not in_block:
            m_open = _OPEN_TAG_RE.match(line)
            if m_open:
                open_line_no = idx
                open_attrs = _parse_attrs(m_open.group("attrs"), idx)
                missing = [a for a in REQUIRED_ATTRS if a not in open_attrs or not open_attrs[a]]
                if missing:
                    raise MissingAttributeError(
                        f"line {idx}: missing required attribute "
                        f"{missing[0]!r} on open tag"
                    )
                in_block = True
                body_lines = []
                continue
            # Stray close tags outside a block are silently ignored per schema.
            continue

        # in_block == True
        if _CLOSE_TAG_RE.match(line):
            block_id = open_attrs["id"]
            if block_id in seen_ids:
                raise DuplicateIdError(
                    f"line {idx}: duplicate id {block_id!r} "
                    f"(block opened at line {open_line_no})"
                )
            seen_ids.add(block_id)
            blocks.append(
                Block(
                    id=block_id,
                    ticket=open_attrs["ticket"],
                    author=open_attrs["author"],
                    session=open_attrs["session"],
                    body="\n".join(body_lines),
                    start_line=open_line_no,
                    end_line=idx,
                )
            )
            in_block = False
            open_attrs = {}
            body_lines = []
            continue

        body_lines.append(line)

    if in_block:
        raise UnclosedEntryError(
            f"line {open_line_no}: unclosed entry — open tag has no matching "
            f"<!-- /argos:entry --> before EOF"
        )

    return blocks


def parse_file(path: str | Path) -> list[Block]:
    """Read ``path`` as UTF-8 text and parse it. Thin wrapper over :func:`parse`."""
    p = Path(path)
    return parse(p.read_text(encoding="utf-8"))
