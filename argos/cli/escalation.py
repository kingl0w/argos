"""Escalation file writer + optional webhook POST (ARG1-041).

The writer composes a frontmatter+body markdown file under
``argos/specs/escalations/{ticket-id}-{ISO-timestamp}.md`` per
``argos/specs/v1.0/schemas/escalation.md`` and (when a webhook URL is
configured via ``escalation.webhook_url`` in ``.argos/local.toml``) POSTs a
JSON summary ``{ticket_id, severity, summary, file_path}`` to that URL.

Design:

- Stdlib only (ADR-001). Webhook transport is :mod:`urllib.request`; no
  third-party HTTP client.
- Webhook is **fire-and-forget**: a non-zero HTTP status, a network error,
  or a timeout is logged to stderr but never raised — the command always
  exits 0 once the file is on disk (per ARCHITECTURE.md §Components/
  Escalation Channel "fire-and-forget; no retry, no delivery guarantee").
- Filename collisions (two writers landing in the same wall-clock second
  for the same ticket) are resolved with a 4-hex-char random suffix
  appended to the filename. The frontmatter ``created`` field keeps the
  canonical ISO-8601-with-colons form; the filename uses
  ``YYYY-MM-DDTHH-MM-SSZ`` (colons swapped for ``-`` for filesystem
  portability per the schema doc).
- Auth headers: NONE in v1.0. ARCHITECTURE.md §Technology choices reads
  verbatim "Webhook transport: plain HTTPS POST with JSON body. No auth in
  v1.0 (TODO: signed payloads if anyone asks)." If/when an ADR adds auth,
  this module is the choke point.
"""

from __future__ import annotations

import datetime
import json
import os
import random
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import IO, Optional

from argos.cli.escalation_validator import (
    ALLOWED_RAISED_BY,
    ALLOWED_SEVERITY,
    REQUIRED_BODY_SECTIONS,
)

__all__ = [
    "DEFAULT_ESCALATION_DIR",
    "DEFAULT_WEBHOOK_TIMEOUT",
    "EscalationError",
    "InvalidRaisedByError",
    "InvalidSeverityError",
    "post_webhook",
    "short_summary",
    "write_escalation",
]


DEFAULT_ESCALATION_DIR = Path("argos/specs/escalations")
DEFAULT_WEBHOOK_TIMEOUT = 4.0  # seconds; AC#5 requires < 5s on unreachable

_HEX_ALPHABET = "0123456789abcdef"
_FILENAME_SUFFIX_LENGTH = 4
_MAX_COLLISION_RETRIES = 16


class EscalationError(Exception):
    """Base class for escalation writer errors."""


class InvalidSeverityError(EscalationError):
    """``severity`` is not one of ``blocking`` / ``advisory``."""

    def __init__(self) -> None:
        super().__init__("severity must be blocking or advisory")


class InvalidRaisedByError(EscalationError):
    """``raised_by`` is not one of the five legal authors."""

    def __init__(self, value: str) -> None:
        allowed = ", ".join(sorted(ALLOWED_RAISED_BY))
        self.value = value
        super().__init__(
            f"raised-by must be one of: {allowed} (got {value!r})"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _format_iso(dt: datetime.datetime) -> str:
    """Canonical frontmatter form: ``YYYY-MM-DDTHH:MM:SSZ`` (UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_filename_ts(dt: datetime.datetime) -> str:
    """Filesystem-portable form: colons swapped for ``-``."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H-%M-%SZ")


def _gen_session_id(now: datetime.datetime, rng: random.Random) -> str:
    suffix = "".join(rng.choice(_HEX_ALPHABET) for _ in range(4))
    return f"sess-{_format_iso(now)}-{suffix}"


def short_summary(body: str, *, limit: int = 120) -> str:
    """Return the first non-blank line of ``body``, truncated to ``limit`` chars.

    Used for the webhook payload's ``summary`` field. If ``body`` is empty
    or blank, returns the empty string.
    """
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            if len(stripped) > limit:
                return stripped[: limit - 1] + "…"
            return stripped
    return ""


def _wrap_body(body: str) -> str:
    """Return ``body`` with the four required H2 sections present.

    - If ``body`` already contains all four required headings on their own
      lines, it is passed through verbatim (with a trailing newline added
      if missing).
    - If ``body`` contains none of them, it is wrapped under
      ``## Question`` and the other three sections are appended as
      ``_(not provided)_`` placeholders so the validator accepts the file.
    - If ``body`` contains some but not all, the missing sections are
      appended at the end with placeholder content.
    """
    body_lines = body.splitlines()
    present = {
        section
        for section in REQUIRED_BODY_SECTIONS
        if any(line.strip() == section for line in body_lines)
    }
    if len(present) == len(REQUIRED_BODY_SECTIONS):
        return body if body.endswith("\n") else body + "\n"

    placeholder = "_(not provided)_"

    if not present:
        out = (
            "## Question\n\n"
            f"{body.rstrip()}\n\n"
            "## Context\n\n"
            f"{placeholder}\n\n"
            "## Options considered\n\n"
            f"{placeholder}\n\n"
            "## Why escalated\n\n"
            f"{placeholder}\n"
        )
        return out

    out_lines = [body.rstrip("\n")]
    for section in REQUIRED_BODY_SECTIONS:
        if section not in present:
            out_lines.append("")
            out_lines.append(section)
            out_lines.append("")
            out_lines.append(placeholder)
    out_lines.append("")
    return "\n".join(out_lines)


def _render_file(
    *,
    ticket_id: str,
    session_id: str,
    severity: str,
    raised_by: str,
    created: str,
    body: str,
) -> str:
    fm = (
        "---\n"
        f"ticket_id: {ticket_id}\n"
        f"session_id: {session_id}\n"
        f"severity: {severity}\n"
        f"raised_by: {raised_by}\n"
        f"created: {created}\n"
        "---\n\n"
    )
    return fm + _wrap_body(body)


def _candidate_filename(
    ticket_id: str,
    fs_ts: str,
    suffix: Optional[str],
) -> str:
    base = f"{ticket_id}-{fs_ts}"
    if suffix:
        base = f"{base}-{suffix}"
    return f"{base}.md"


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def write_escalation(
    *,
    ticket_id: str,
    severity: str,
    raised_by: str,
    body: str,
    dest_dir: Path,
    session_id: Optional[str] = None,
    now: Optional[datetime.datetime] = None,
    rng: Optional[random.Random] = None,
) -> Path:
    """Write a single escalation file. Returns the resolved path on success.

    Raises :class:`InvalidSeverityError` / :class:`InvalidRaisedByError` /
    :class:`EscalationError` on bad input. ``dest_dir`` is created (with
    parents) if missing.

    Filename collisions (same ticket + same wall-clock second) are resolved
    with a 4-hex-char random suffix on the *filename only*; the frontmatter
    ``created`` field keeps the canonical timestamp. ``os.O_EXCL`` makes the
    create-or-fail step atomic, so two concurrent writers cannot overwrite
    each other.
    """
    if severity not in ALLOWED_SEVERITY:
        raise InvalidSeverityError()
    if raised_by not in ALLOWED_RAISED_BY:
        raise InvalidRaisedByError(raised_by)
    if not ticket_id:
        raise EscalationError("ticket_id is required")
    if not isinstance(body, str):
        raise EscalationError("body must be a string")

    if now is None:
        now = _utc_now()
    if rng is None:
        rng = random.SystemRandom()
    if session_id is None or session_id == "":
        session_id = _gen_session_id(now, rng)

    created_iso = _format_iso(now)
    fs_ts = _format_filename_ts(now)

    dest_dir.mkdir(parents=True, exist_ok=True)

    file_text = _render_file(
        ticket_id=ticket_id,
        session_id=session_id,
        severity=severity,
        raised_by=raised_by,
        created=created_iso,
        body=body,
    )

    last_error: Optional[OSError] = None
    for attempt in range(_MAX_COLLISION_RETRIES + 1):
        if attempt == 0:
            filename = _candidate_filename(ticket_id, fs_ts, None)
        else:
            suffix = "".join(
                rng.choice(_HEX_ALPHABET) for _ in range(_FILENAME_SUFFIX_LENGTH)
            )
            filename = _candidate_filename(ticket_id, fs_ts, suffix)
        path = dest_dir / filename
        try:
            fd = os.open(
                str(path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o644,
            )
        except FileExistsError as exc:
            last_error = exc
            continue
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(file_text)
                fh.flush()
                os.fsync(fh.fileno())
        except Exception:
            try:
                os.unlink(str(path))
            except OSError:
                pass
            raise
        return path

    raise EscalationError(
        f"could not create unique escalation filename for {ticket_id} "
        f"after {_MAX_COLLISION_RETRIES} retries: {last_error}"
    )


def post_webhook(
    url: str,
    *,
    ticket_id: str,
    severity: str,
    summary: str,
    file_path: str,
    timeout: float = DEFAULT_WEBHOOK_TIMEOUT,
    log_stream: Optional[IO[str]] = None,
) -> bool:
    """POST a JSON summary to ``url``. Returns ``True`` on 2xx, else ``False``.

    Fire-and-forget: every error path (HTTP non-2xx, network unreachable,
    timeout, malformed URL) writes a single ``webhook delivery failed: ...``
    line to ``log_stream`` (default :data:`sys.stderr`) and returns
    ``False``. Never raises.
    """
    stream = log_stream if log_stream is not None else sys.stderr

    payload = json.dumps(
        {
            "ticket_id": ticket_id,
            "severity": severity,
            "summary": summary,
            "file_path": file_path,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            if 200 <= int(status) < 300:
                return True
            stream.write(f"webhook delivery failed: {status}\n")
            return False
    except urllib.error.HTTPError as exc:
        stream.write(f"webhook delivery failed: {exc.code}\n")
        return False
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        # URLError covers DNS failures, refused connections, timeouts that
        # surface as URLError(reason=socket.timeout). ValueError covers
        # urllib's "unknown url type" rejection of malformed URLs.
        stream.write(f"webhook delivery failed: {exc}\n")
        return False
