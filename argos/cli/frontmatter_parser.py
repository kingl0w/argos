"""Reference parser for the argos v1.0 YAML frontmatter subset.

The grammar is pinned by ``argos/specs/v1.0/decisions/ADR-002-ac-harness-portability.md``
§3. This module implements that grammar exactly — no more, no less. Inputs
outside the subset raise :class:`FrontmatterParseError` with a one-line reason
prefixed by ``line N:`` per ADR-002 §4.

Standard library only — no external runtime dependencies (per ADR-001
§Decision item 2 and ADR-002 §1).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "FrontmatterParseError",
    "parse",
    "parse_file",
    "extract_frontmatter",
    "main",
]


class FrontmatterParseError(Exception):
    """Raised when input violates the ADR-002 §3 subset.

    The exception ``str()`` form is the one-line reason that the CLI emits to
    stderr after the ``frontmatter-parse: `` prefix; it always starts with
    ``line N: `` when ``line_no`` was provided.
    """

    def __init__(self, reason: str, *, line_no: int | None = None) -> None:
        self.reason = reason
        self.line_no = line_no
        if line_no is not None:
            super().__init__(f"line {line_no}: {reason}")
        else:
            super().__init__(reason)


_FRONTMATTER_DELIM = "---"

# Top-level key: must start at column 0; key chars are word/dash; followed by
# ``:`` then end-of-line or whitespace.
_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:(\s|$)")
# Block-sequence item: any indentation, then ``- `` or ``-`` at end-of-line.
_SEQ_ITEM_RE = re.compile(r"^(\s+)-(\s+(.*)|\s*$)")
# Nested-mapping line under an empty-value key: indentation + ``key:``.
_NESTED_MAP_RE = re.compile(r"^(\s+)([A-Za-z_][A-Za-z0-9_-]*)\s*:")
# Bare integer (with optional sign).
_INT_RE = re.compile(r"^-?\d+$")


def extract_frontmatter(text: str) -> tuple[str, int]:
    """Locate the YAML frontmatter region in ``text``.

    If ``text`` begins with a ``---`` delimiter on its first line, the
    frontmatter is the content between that delimiter and the next ``---``
    line. Otherwise, the entire input is treated as frontmatter.

    Returns ``(frontmatter_text, line_offset)`` where ``line_offset`` is the
    1-indexed line number, in the *original* ``text``, of the first
    frontmatter content line. The offset lets parser errors cite line numbers
    that match the user's source file.

    Raises :class:`FrontmatterParseError` if a ``---`` opens but never closes.
    """
    lines = text.splitlines()
    if not lines:
        return "", 1
    if lines[0].strip() == _FRONTMATTER_DELIM:
        for i in range(1, len(lines)):
            if lines[i].strip() == _FRONTMATTER_DELIM:
                return "\n".join(lines[1:i]), 2
        raise FrontmatterParseError(
            "opening '---' delimiter has no matching closing '---'", line_no=1
        )
    return text, 1


def parse(text: str) -> dict[str, Any]:
    """Parse YAML-subset frontmatter ``text`` to a dict.

    Accepts either a bare frontmatter body or a ``---``-delimited frontmatter
    region followed by markdown body (the body is ignored).

    Raises :class:`FrontmatterParseError` on any input outside the ADR-002 §3
    subset.
    """
    fm_text, line_offset = extract_frontmatter(text)
    return _parse_body(fm_text, line_offset)


def parse_file(path: str | Path) -> dict[str, Any]:
    """Read ``path`` as UTF-8 and parse its frontmatter.

    Raises :class:`FrontmatterParseError` with reason ``input not valid UTF-8``
    when the file cannot be decoded as UTF-8 (the error's ``line_no`` is 1
    because the failure is byte-level, before any line structure is known).
    """
    p = Path(path)
    raw = p.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FrontmatterParseError("input not valid UTF-8", line_no=1) from exc
    return parse(text)


def _parse_body(text: str, line_offset: int) -> dict[str, Any]:
    lines = text.splitlines()
    result: dict[str, Any] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        line_no = i + line_offset

        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        if line[:1] in (" ", "\t"):
            raise FrontmatterParseError(
                f"unexpected indentation at top level (saw {line!r})",
                line_no=line_no,
            )

        m = _KEY_RE.match(line)
        if not m:
            raise FrontmatterParseError(
                f"expected 'key: value' or 'key:' (saw {line!r})",
                line_no=line_no,
            )
        key = m.group(1)
        rest = line[m.end() :]
        rest = _strip_inline_comment(rest).strip()

        if not rest:
            seq, consumed = _try_parse_block_sequence(lines, i + 1, line_offset)
            if seq is not None:
                result[key] = seq
                i = i + 1 + consumed
                continue
            nested_line = _peek_nested_mapping_line(lines, i + 1)
            if nested_line is not None:
                raise FrontmatterParseError(
                    "nested mapping at depth 2 not supported",
                    line_no=nested_line + line_offset,
                )
            result[key] = None
            i += 1
            continue

        result[key] = _parse_scalar(rest, line_no)
        i += 1

    return result


def _strip_inline_comment(value: str) -> str:
    """Strip a `` # ...`` trailing comment from a bare-scalar value.

    A ``#`` only starts a comment when preceded by whitespace; otherwise it is
    part of the value (per YAML 1.2). This is applied only to bare scalars; the
    quoted-scalar parser handles its own trailing-content rules.
    """
    out = []
    in_squote = False
    in_dquote = False
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "'" and not in_dquote:
            in_squote = not in_squote
        elif ch == '"' and not in_squote:
            if not (i > 0 and value[i - 1] == "\\"):
                in_dquote = not in_dquote
        elif ch == "#" and not in_squote and not in_dquote:
            if i == 0 or value[i - 1].isspace():
                break
        out.append(ch)
        i += 1
    return "".join(out)


def _try_parse_block_sequence(
    lines: list[str], start: int, line_offset: int
) -> tuple[list[Any] | None, int]:
    """Attempt to parse a block sequence starting at ``lines[start]``.

    Returns ``(items, consumed)`` if a sequence is found, where ``consumed`` is
    the number of input lines the sequence occupies. Returns ``(None, 0)`` if
    the next non-blank line is not a sequence item.

    The first sequence item determines the indentation level; subsequent items
    must share it. Items are flat scalars only — nested sequences (an item
    whose value spawns its own ``-`` lines) raise.
    """
    j = start
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j >= len(lines):
        return None, 0
    m_first = _SEQ_ITEM_RE.match(lines[j])
    if not m_first:
        return None, 0

    indent = m_first.group(1)
    items: list[Any] = []
    k = start
    while k < len(lines):
        line = lines[k]
        if not line.strip():
            k += 1
            continue
        m = _SEQ_ITEM_RE.match(line)
        if not m:
            break
        if m.group(1) != indent:
            break
        item_line_no = k + line_offset
        raw = m.group(3) if m.group(3) is not None else ""
        raw = _strip_inline_comment(raw).strip()
        if not raw:
            raise FrontmatterParseError(
                "empty sequence item not supported",
                line_no=item_line_no,
            )
        items.append(_parse_scalar(raw, item_line_no))
        k += 1
    consumed = k - start
    return items, consumed


def _peek_nested_mapping_line(lines: list[str], start: int) -> int | None:
    """Return the 0-indexed line of an indented ``key:`` after a bare key.

    When a top-level key has an empty value, the next non-blank line is either
    a block-sequence item (``  - ...``) or an indented ``key:`` (which is a
    nested mapping at depth 2 — rejected). This helper returns the index of
    the offending line, or ``None`` if no nested mapping is present.
    """
    j = start
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j >= len(lines):
        return None
    if _NESTED_MAP_RE.match(lines[j]):
        return j
    return None


def _parse_scalar(raw: str, line_no: int) -> Any:
    """Parse a single scalar value from ``raw`` (already trimmed of leading
    whitespace and trailing inline comment).

    Rejects every YAML feature outside the ADR-002 §3 subset.
    """
    if not raw:
        raise FrontmatterParseError(
            "empty scalar value not supported", line_no=line_no
        )

    first = raw[0]

    if first == "[":
        raise FrontmatterParseError(
            "flow-style sequence not supported", line_no=line_no
        )
    if first == "{":
        raise FrontmatterParseError(
            "flow-style mapping not supported", line_no=line_no
        )
    if first == "|":
        raise FrontmatterParseError(
            "multiline scalar indicator '|' not supported", line_no=line_no
        )
    if first == ">":
        raise FrontmatterParseError(
            "multiline scalar indicator '>' not supported", line_no=line_no
        )
    if first == "&":
        token = raw.split(None, 1)[0]
        raise FrontmatterParseError(
            f"anchor {token!r} not supported", line_no=line_no
        )
    if first == "*":
        token = raw.split(None, 1)[0]
        raise FrontmatterParseError(
            f"alias {token!r} not supported", line_no=line_no
        )
    if first == "!":
        token = raw.split(None, 1)[0]
        raise FrontmatterParseError(
            f"tag {token!r} not supported", line_no=line_no
        )

    if first == '"':
        return _parse_double_quoted(raw, line_no)
    if first == "'":
        return _parse_single_quoted(raw, line_no)

    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw == "null" or raw == "~":
        return None
    if _INT_RE.match(raw):
        return int(raw)
    return raw


def _parse_double_quoted(raw: str, line_no: int) -> str:
    """Parse a double-quoted scalar with limited escape support.

    Per ADR-002 §3: ``\"``, ``\\``, ``\\n``, ``\\t`` are recognized inside
    double-quoted strings; other backslash sequences are rejected.
    """
    out: list[str] = []
    i = 1
    while i < len(raw):
        ch = raw[i]
        if ch == "\\":
            if i + 1 >= len(raw):
                raise FrontmatterParseError(
                    "unterminated escape sequence in double-quoted string",
                    line_no=line_no,
                )
            nxt = raw[i + 1]
            if nxt == '"':
                out.append('"')
            elif nxt == "\\":
                out.append("\\")
            elif nxt == "n":
                out.append("\n")
            elif nxt == "t":
                out.append("\t")
            else:
                raise FrontmatterParseError(
                    f"unsupported escape sequence '\\{nxt}' in double-quoted string",
                    line_no=line_no,
                )
            i += 2
            continue
        if ch == '"':
            tail = raw[i + 1 :].lstrip()
            if tail and not tail.startswith("#"):
                raise FrontmatterParseError(
                    f"unexpected content after closing quote: {tail!r}",
                    line_no=line_no,
                )
            return "".join(out)
        out.append(ch)
        i += 1
    raise FrontmatterParseError(
        "unterminated double-quoted string", line_no=line_no
    )


def _parse_single_quoted(raw: str, line_no: int) -> str:
    """Parse a single-quoted scalar.

    YAML 1.2 single-quoted strings have only one escape: ``''`` produces a
    literal ``'``. No backslash escapes.
    """
    out: list[str] = []
    i = 1
    while i < len(raw):
        ch = raw[i]
        if ch == "'":
            if i + 1 < len(raw) and raw[i + 1] == "'":
                out.append("'")
                i += 2
                continue
            tail = raw[i + 1 :].lstrip()
            if tail and not tail.startswith("#"):
                raise FrontmatterParseError(
                    f"unexpected content after closing quote: {tail!r}",
                    line_no=line_no,
                )
            return "".join(out)
        out.append(ch)
        i += 1
    raise FrontmatterParseError(
        "unterminated single-quoted string", line_no=line_no
    )


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argos frontmatter-parse",
        description=(
            "Parse the YAML-subset frontmatter of <path> and emit JSON to "
            "stdout. The grammar is pinned by ADR-002 §3."
        ),
    )
    parser.add_argument("path", help="path to a markdown or YAML file")
    return parser


def main(argv: list[str]) -> int:
    parser = _build_argparser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    try:
        data = parse_file(args.path)
    except FileNotFoundError:
        sys.stderr.write(
            f"frontmatter-parse: file not found: {args.path}\n"
        )
        return 1
    except IsADirectoryError:
        sys.stderr.write(
            f"frontmatter-parse: not a file: {args.path}\n"
        )
        return 1
    except FrontmatterParseError as exc:
        sys.stderr.write(f"frontmatter-parse: {exc}\n")
        return 2

    json.dump(data, sys.stdout, indent=2, sort_keys=False, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
