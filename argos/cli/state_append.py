"""Append-only writer for argos v1.0 STATE.md blocks.

The single chokepoint for STATE.md mutations: every writer (verifier on ticket
close, cycle-close helper, future tooling) goes through :func:`append_block`
rather than editing the file directly. The helper:

- Generates a unique block ``id`` (``{UTC-ISO-timestamp}-{ticket}``, with a
  6-hex-char random suffix on same-second collisions).
- Wraps the body in canonical ``<!-- argos:entry ... -->`` /
  ``<!-- /argos:entry -->`` HTML comments per
  ``argos/specs/v1.0/schemas/state-block.md``.
- Locates the named ``## <section>`` heading and inserts the block at the end
  of that section (just before the next ``## `` heading or EOF).
- Serializes concurrent calls via ``fcntl.flock`` on a sidecar ``{file}.lock``
  and commits the new content via ``tempfile`` + ``os.replace`` (atomic rename
  on POSIX).

Standard library only — no external runtime dependencies.
"""

from __future__ import annotations

import fcntl
import os
import random
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from argos.cli.state_parser import parse as parse_state

__all__ = [
    "SectionNotFoundError",
    "build_block",
    "generate_id",
    "append_block",
]

_ID_SUFFIX_ALPHABET = "0123456789abcdef"
_ID_SUFFIX_LENGTH = 6
_ID_GENERATION_MAX_ATTEMPTS = 5


class SectionNotFoundError(Exception):
    """Raised when the requested ``## <section>`` heading is absent."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_timestamp(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_id(
    ticket: str,
    *,
    now: datetime | None = None,
    existing_ids: set[str] | None = None,
    rng: random.Random | None = None,
) -> str:
    """Compose a globally-unique block ``id`` for ``ticket``.

    Format: ``{UTC-ISO-timestamp}-{ticket}``. If that primary ID is already in
    ``existing_ids``, retries with a 6-hex-char random suffix
    (``{primary}-{abcdef}``) until uniqueness, up to 5 attempts.
    """
    if now is None:
        now = _utc_now()
    if existing_ids is None:
        existing_ids = set()
    if rng is None:
        rng = random.Random()

    primary = f"{_format_timestamp(now)}-{ticket}"
    if primary not in existing_ids:
        return primary

    for _ in range(_ID_GENERATION_MAX_ATTEMPTS):
        suffix = "".join(rng.choice(_ID_SUFFIX_ALPHABET) for _ in range(_ID_SUFFIX_LENGTH))
        candidate = f"{primary}-{suffix}"
        if candidate not in existing_ids:
            return candidate

    raise RuntimeError(
        f"could not generate unique id for ticket {ticket!r} after "
        f"{_ID_GENERATION_MAX_ATTEMPTS} attempts"
    )


def build_block(
    *,
    block_id: str,
    ticket: str,
    author: str,
    session: str,
    body: str,
) -> str:
    """Compose the full block string (open tag + body + close tag).

    Body is preserved verbatim modulo a single trailing-newline trim so the
    close tag sits on its own line directly below the last body line.
    """
    open_tag = (
        f"<!-- argos:entry id={block_id} ticket={ticket} "
        f"author={author} session={session} -->"
    )
    close_tag = "<!-- /argos:entry -->"
    body_text = body.rstrip("\n")
    if body_text:
        return f"{open_tag}\n{body_text}\n{close_tag}\n"
    return f"{open_tag}\n{close_tag}\n"


_SECTION_HEADING_RE_TEMPLATE = r"^## {name}\s*$"
_NEXT_HEADING_RE = re.compile(r"^## ")


def _find_section_bounds(lines: list[str], section: str) -> tuple[int, int]:
    """Return (heading_line_index, insert_line_index) for ``## section``.

    ``insert_line_index`` is where a new line should be spliced in (just
    before the next ``## `` heading, or at end of file). Both are 0-indexed
    line positions in ``lines``.

    Raises :class:`SectionNotFoundError` if the heading is absent.
    """
    heading_re = re.compile(_SECTION_HEADING_RE_TEMPLATE.format(name=re.escape(section)))
    heading_idx = -1
    for idx, line in enumerate(lines):
        if heading_re.match(line):
            heading_idx = idx
            break

    if heading_idx == -1:
        raise SectionNotFoundError(section)

    insert_idx = len(lines)
    for idx in range(heading_idx + 1, len(lines)):
        if _NEXT_HEADING_RE.match(lines[idx]):
            insert_idx = idx
            break
    return heading_idx, insert_idx


def _splice_block(text: str, section: str, block: str) -> str:
    """Return ``text`` with ``block`` spliced at the end of ``## section``.

    Adds a leading blank line for separation and a trailing blank line before
    the next section (or EOF).
    """
    # splitlines(keepends=True) preserves trailing newlines so we can rejoin
    # losslessly.
    lines = text.splitlines(keepends=True)
    _, insert_idx = _find_section_bounds([line.rstrip("\n") for line in lines], section)

    insertion = "\n" + block + "\n"

    new_lines = lines[:insert_idx] + [insertion] + lines[insert_idx:]
    result = "".join(new_lines)
    # Preserve trailing newline behavior: if the original file ended with a
    # newline, ours should too; same if it did not.
    if not text.endswith("\n") and result.endswith("\n"):
        result = result.rstrip("\n")
    return result


def _existing_ids(text: str) -> set[str]:
    return {block.id for block in parse_state(text)}


def append_block(
    state_file: Path | str,
    *,
    section: str,
    ticket: str,
    author: str,
    session: str,
    body: str,
    dry_run: bool = False,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> str:
    """Atomically append a new block to ``state_file`` under ``## section``.

    Returns the composed block string (whether or not it was written).

    Raises:
        SectionNotFoundError: ``## section`` heading is absent.
        FileNotFoundError: ``state_file`` does not exist (non-dry-run).
    """
    state_path = Path(state_file)

    if dry_run:
        if state_path.exists():
            existing_text = state_path.read_text(encoding="utf-8")
            existing = _existing_ids(existing_text)
            # Validate section presence so dry-run mirrors real-run errors.
            _find_section_bounds(existing_text.splitlines(), section)
        else:
            existing = set()
        block_id = generate_id(ticket, now=now, existing_ids=existing, rng=rng)
        return build_block(
            block_id=block_id,
            ticket=ticket,
            author=author,
            session=session,
            body=body,
        )

    if not state_path.exists():
        raise FileNotFoundError(str(state_path))

    lock_path = state_path.with_name(state_path.name + ".lock")
    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        current_text = state_path.read_text(encoding="utf-8")
        existing = _existing_ids(current_text)
        block_id = generate_id(ticket, now=now, existing_ids=existing, rng=rng)
        block = build_block(
            block_id=block_id,
            ticket=ticket,
            author=author,
            session=session,
            body=body,
        )
        new_text = _splice_block(current_text, section, block)

        tmp_fd, tmp_name = tempfile.mkstemp(
            prefix=state_path.name + ".tmp.",
            dir=str(state_path.parent),
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp:
                tmp.write(new_text)
                tmp.flush()
                os.fsync(tmp.fileno())

            delay = os.environ.get("ARGOS_TEST_DELAY_BEFORE_RENAME")
            if delay:
                time.sleep(float(delay))

            os.replace(tmp_name, str(state_path))
            tmp_name = None
        finally:
            if tmp_name is not None and os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass

        return block
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)
