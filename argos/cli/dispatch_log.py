"""Orchestrator dispatch log writer (ARG1-012).

Per `argos/specs/v1.0/ARCHITECTURE.md` §Components/Orchestrator, the
orchestrator records each dispatch decision to
``argos/specs/dispatch/{epic-id}/{ticket-id}.md``. Each file is created once
(initial dispatch) and appended to thereafter (verifier results, parked-on-
escalation transitions, retry events). Files are markdown with a
ADR-002-conformant frontmatter prefix and an ``## Events`` body of
self-contained timestamped blocks.

Design:

- Stdlib only (ADR-001 §Decision item 2).
- Initial create uses ``os.O_CREAT | os.O_EXCL | os.O_WRONLY`` so two
  concurrent dispatchers cannot overwrite each other (precedent: ARG1-041
  escalation writer). The orchestrator is a singleton per Argos invocation,
  so concurrent same-ticket writes are not the practical case — but the
  invariant still holds against operator-driven re-runs.
- Append uses ``fcntl.flock`` on a sidecar lock plus ``tempfile`` +
  ``os.replace`` (precedent: ARG1-051 ``state_append``). The frontmatter
  region is a strict byte-prefix of the file and is never re-rendered, so
  ``stat -c %s`` strictly increases on every append and the canonical
  frontmatter is preserved bit-for-bit (AC#3).
- ``dry_run=True`` short-circuits every disk operation. ``argos orchestrate
  --dry-run`` (ARG1-011) routes through this path so AC#4 — "writes nothing
  to ``argos/specs/dispatch/`` under ``--dry-run``" — is enforced at the
  writer rather than at every caller.
"""

from __future__ import annotations

import fcntl
import os
import random
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

__all__ = [
    "DispatchLogError",
    "DispatchLogExistsError",
    "DispatchLogMissingError",
    "InvalidIdError",
    "EVENT_DISPATCHED",
    "EVENT_VERIFIER_RESULT",
    "EVENT_PARKED",
    "EVENT_RETRY",
    "EVENT_MERGED",
    "build_initial_file",
    "build_event_block",
    "dispatch_log_path",
    "write_dispatch_log",
    "append_event",
]


# Canonical event-type slugs. Producers may emit other ``[a-z0-9-]+`` slugs
# (the writer accepts any matching the slug shape); these constants exist so
# call sites don't repeat the literal strings.
EVENT_DISPATCHED = "dispatched"
EVENT_VERIFIER_RESULT = "verifier-result"
EVENT_PARKED = "parked"
EVENT_RETRY = "retry"
EVENT_MERGED = "merged"


_ID_SLUG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_EVENT_TYPE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._:T\-]+$")
_HEX_ALPHABET = "0123456789abcdef"
_DISAMBIG_SUFFIX_LENGTH = 6
_DISAMBIG_MAX_ATTEMPTS = 5

_EVENTS_HEADING = "## Events"
_EVENT_OPEN_FMT = (
    "<!-- argos:dispatch-event id={id} type={type} ticket={ticket} at={at} -->"
)
_EVENT_CLOSE = "<!-- /argos:dispatch-event -->"


class DispatchLogError(Exception):
    """Base class for dispatch-log writer errors."""


class DispatchLogExistsError(DispatchLogError):
    """Initial write tried to clobber an existing log file."""


class DispatchLogMissingError(DispatchLogError):
    """``append_event`` invoked on a path with no existing log file."""


class InvalidIdError(DispatchLogError, ValueError):
    """ticket-id, epic-id, or event-type failed slug-shape validation."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_slug(value: str, *, kind: str) -> None:
    if not isinstance(value, str) or not _ID_SLUG_RE.match(value):
        raise InvalidIdError(
            f"{kind} must match ^[A-Za-z][A-Za-z0-9_-]*$ (got {value!r})"
        )


def _validate_event_type(value: str) -> None:
    if not isinstance(value, str) or not _EVENT_TYPE_RE.match(value):
        raise InvalidIdError(
            f"event_type must match ^[a-z][a-z0-9-]*$ (got {value!r})"
        )


def _validate_session_id(value: str) -> None:
    if not isinstance(value, str) or not _SESSION_ID_RE.match(value) or not value:
        raise InvalidIdError(
            f"session_id must be a non-empty token of [A-Za-z0-9._:T-] "
            f"(got {value!r})"
        )


def dispatch_log_path(dispatch_root: Path | str, epic_id: str, ticket_id: str) -> Path:
    """Return the canonical dispatch-log path for ``(epic_id, ticket_id)``.

    Raises :class:`InvalidIdError` if either id has a shape that would let it
    escape the dispatch root (e.g. ``..``, ``foo/bar``).
    """
    _validate_slug(epic_id, kind="epic_id")
    _validate_slug(ticket_id, kind="ticket_id")
    return Path(dispatch_root) / epic_id / f"{ticket_id}.md"


def build_event_block(
    *,
    block_id: str,
    event_type: str,
    ticket_id: str,
    at: str,
    body: str,
) -> str:
    """Compose a single ``<!-- argos:dispatch-event ... -->`` block.

    Body is preserved verbatim modulo a trailing-newline trim so the close
    tag sits on its own line directly below the body.
    """
    open_tag = _EVENT_OPEN_FMT.format(
        id=block_id, type=event_type, ticket=ticket_id, at=at
    )
    body_text = body.rstrip("\n") if body else ""
    if body_text:
        return f"{open_tag}\n{body_text}\n{_EVENT_CLOSE}\n"
    return f"{open_tag}\n{_EVENT_CLOSE}\n"


def build_initial_file(
    *,
    ticket_id: str,
    epic_id: str,
    batch_id: str,
    worktree_path: str,
    session_id: str,
    dispatched_at: str,
    initial_block_id: str,
    initial_body: str = "",
) -> str:
    """Compose the full initial-file text (frontmatter + ``## Events`` + one block).

    The frontmatter conforms to ADR-002 §3: flat scalar ``key: value`` pairs.
    Bare scalars are used because none of the values contain leading
    flow-style or anchor characters; YAML 1.2 core type detection treats
    ``2026-04-30T10:00:00Z`` as a string (no integer match, no enum hit).
    """
    fm_lines = [
        "---",
        f"ticket_id: {ticket_id}",
        f"epic_id: {epic_id}",
        f"batch_id: {batch_id}",
        f"dispatched_at: {dispatched_at}",
        f"worktree_path: {worktree_path}",
        f"session_id: {session_id}",
        "---",
        "",
        _EVENTS_HEADING,
        "",
    ]
    initial_block = build_event_block(
        block_id=initial_block_id,
        event_type=EVENT_DISPATCHED,
        ticket_id=ticket_id,
        at=dispatched_at,
        body=initial_body
        or f"- worktree: `{worktree_path}`\n- batch: `{batch_id}`\n- session: `{session_id}`",
    )
    return "\n".join(fm_lines) + initial_block


def _gen_block_id(
    ticket_id: str,
    event_type: str,
    *,
    now: datetime,
    existing_ids: set[str],
    rng: random.Random,
) -> str:
    primary = f"{_format_iso(now)}-{ticket_id}-{event_type}"
    if primary not in existing_ids:
        return primary
    for _ in range(_DISAMBIG_MAX_ATTEMPTS):
        suffix = "".join(
            rng.choice(_HEX_ALPHABET) for _ in range(_DISAMBIG_SUFFIX_LENGTH)
        )
        candidate = f"{primary}-{suffix}"
        if candidate not in existing_ids:
            return candidate
    raise DispatchLogError(
        f"could not allocate unique event id for {ticket_id}/{event_type} "
        f"after {_DISAMBIG_MAX_ATTEMPTS} attempts"
    )


_BLOCK_ID_RE = re.compile(
    r"<!--\s*argos:dispatch-event\s+id=([^\s]+)\s"
)


def _scan_existing_ids(text: str) -> set[str]:
    return set(_BLOCK_ID_RE.findall(text))


def write_dispatch_log(
    *,
    ticket_id: str,
    epic_id: str,
    batch_id: str,
    worktree_path: str,
    session_id: str,
    dispatch_root: Path | str,
    dispatched_at: Optional[datetime] = None,
    initial_body: str = "",
    dry_run: bool = False,
    rng: Optional[random.Random] = None,
) -> Path:
    """Create the initial dispatch-log file for ``ticket_id`` under ``epic_id``.

    Writes ``{dispatch_root}/{epic_id}/{ticket_id}.md`` exactly once. The
    file is created via ``O_CREAT | O_EXCL | O_WRONLY``; a second call for
    the same path raises :class:`DispatchLogExistsError`. Returns the
    resolved path (whether or not it was written, when ``dry_run=True``).

    Raises:
        InvalidIdError: ``ticket_id`` / ``epic_id`` / ``session_id`` failed
            slug validation.
        DispatchLogExistsError: a file already exists at the target path.
    """
    _validate_slug(ticket_id, kind="ticket_id")
    _validate_slug(epic_id, kind="epic_id")
    _validate_session_id(session_id)
    if not batch_id:
        raise InvalidIdError("batch_id must be a non-empty string")
    if not worktree_path:
        raise InvalidIdError("worktree_path must be a non-empty string")

    if dispatched_at is None:
        dispatched_at = _utc_now()
    if rng is None:
        rng = random.SystemRandom()

    iso = _format_iso(dispatched_at)
    target = Path(dispatch_root) / epic_id / f"{ticket_id}.md"

    if dry_run:
        return target

    initial_block_id = f"{iso}-{ticket_id}-{EVENT_DISPATCHED}"
    file_text = build_initial_file(
        ticket_id=ticket_id,
        epic_id=epic_id,
        batch_id=batch_id,
        worktree_path=worktree_path,
        session_id=session_id,
        dispatched_at=iso,
        initial_block_id=initial_block_id,
        initial_body=initial_body,
    )

    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        fd = os.open(
            str(target),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o644,
        )
    except FileExistsError as exc:
        raise DispatchLogExistsError(
            f"dispatch log already exists: {target}"
        ) from exc

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(file_text)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        try:
            os.unlink(str(target))
        except OSError:
            pass
        raise

    return target


def append_event(
    *,
    dispatch_file: Path | str,
    event_type: str,
    body: str = "",
    at: Optional[datetime] = None,
    dry_run: bool = False,
    rng: Optional[random.Random] = None,
) -> str:
    """Append one event block to an existing dispatch-log file.

    Atomic: a sidecar ``{file}.lock`` serializes concurrent appenders;
    rendering goes via ``tempfile`` + ``os.replace``. The frontmatter region
    (everything up to and including the closing ``---``) is never touched,
    so byte-equality of the canonical frontmatter is preserved across any
    number of appends (AC#3).

    Returns the composed block string. ``dry_run=True`` returns the block
    string without touching disk.

    Raises:
        DispatchLogMissingError: ``dispatch_file`` does not exist.
        InvalidIdError: ``event_type`` failed slug-shape validation, or the
            existing log's frontmatter lacks a ``ticket_id``.
    """
    _validate_event_type(event_type)
    path = Path(dispatch_file)

    if at is None:
        at = _utc_now()
    if rng is None:
        rng = random.SystemRandom()
    iso = _format_iso(at)

    if dry_run:
        # We can't read existing ids without the file; in dry-run, a fresh id
        # without disambiguation suffix is enough for the caller to inspect
        # the would-be block.
        ticket_for_id = _peek_ticket_id_or_path_stem(path)
        block_id = f"{iso}-{ticket_for_id}-{event_type}"
        return build_event_block(
            block_id=block_id,
            event_type=event_type,
            ticket_id=ticket_for_id,
            at=iso,
            body=body,
        )

    if not path.exists():
        raise DispatchLogMissingError(f"dispatch log not found: {path}")

    lock_path = path.with_name(path.name + ".lock")
    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        current_text = path.read_text(encoding="utf-8")
        ticket_id = _read_ticket_id(current_text)
        existing_ids = _scan_existing_ids(current_text)

        block_id = _gen_block_id(
            ticket_id,
            event_type,
            now=at,
            existing_ids=existing_ids,
            rng=rng,
        )
        block = build_event_block(
            block_id=block_id,
            event_type=event_type,
            ticket_id=ticket_id,
            at=iso,
            body=body,
        )
        new_text = _splice_event(current_text, block)

        tmp_fd, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".tmp.",
            dir=str(path.parent),
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp:
                tmp.write(new_text)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_name, str(path))
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


_TICKET_ID_FM_RE = re.compile(r"(?m)^ticket_id:\s*(\S+)\s*$")


def _read_ticket_id(text: str) -> str:
    m = _TICKET_ID_FM_RE.search(text)
    if m is None:
        raise InvalidIdError(
            "dispatch log frontmatter has no ticket_id field"
        )
    return m.group(1)


def _peek_ticket_id_or_path_stem(path: Path) -> str:
    if path.exists():
        try:
            return _read_ticket_id(path.read_text(encoding="utf-8"))
        except (OSError, InvalidIdError):
            pass
    return path.stem


def _splice_event(text: str, block: str) -> str:
    """Insert ``block`` at the end of the file, separated by a blank line.

    The dispatch-log format treats every event block as a peer at the
    document level after ``## Events``; we simply append. This keeps the
    frontmatter region untouched (it lives at byte offset 0) and avoids
    re-rendering any prior block — both load-bearing for AC#3.
    """
    if not text.endswith("\n"):
        text = text + "\n"
    if not text.endswith("\n\n"):
        text = text + "\n"
    return text + block
