"""``argos sync --clean-queue`` — remove shipped tickets from ``## Queue``.

ARG1-068 / ARCHITECTURE.md §Contracts/STATE.md format. Operator-driven
companion to ARG1-054's cycle close: where ``--close-cycle`` archives the
``## Done this cycle`` section, ``--clean-queue`` prunes the orthogonal
``## Queue`` section of entries for tickets that have already shipped.

A ticket is "shipped" iff its id appears in either the live STATE.md's
``## Done this cycle`` section OR any ``argos/specs/cycles/*.md`` archive
produced by cycle close. Queue bullets whose leading ticket id matches a
shipped id are removed; every other queue line (unshipped bullets, the
placeholder, blank lines) is preserved verbatim.

Structural-rewrite discipline (mirrors cycle_close.py exactly):
- Removing a ``- ARG1-NNN ...`` bullet is a *deletion*, which the ARG1-032
  pre-commit hook refuses unless ``ARGOS_CYCLE_CLOSE=1`` is set. The bypass
  is exported only for the single ``git commit`` invocation, never for any
  incidental write (``git add`` does not trigger the hook).
- The STATE.md rewrite uses ``tempfile`` + ``os.replace`` so a SIGKILL
  mid-rewrite leaves either the old or new file intact, never a torn write
  (ARG1-051 pattern).

The orchestrator never writes ``## Queue`` (it would violate the ARG1-032
verifier-only-author contract); this primitive is the legitimate operator
channel for that edit. See ARG1-068 §Context.

Stdlib only — ADR-001 / ADR-002.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from argos.cli.queue import TICKET_ID_RE
from argos.cli.state_parser import Block, StateBlockError, parse as parse_state

__all__ = [
    "CleanQueueError",
    "QueueSectionMissingError",
    "CleanQueueResult",
    "clean_queue",
    "main",
]

_DEFAULT_STATE_FILE = "argos/specs/v1.0/STATE.md"
_DEFAULT_CYCLES_DIR = "argos/specs/cycles"
_DONE_SECTION = "Done this cycle"

# Exact-match section headings. ``## Done this cycle`` must match the *live*
# section only — historical inline archives such as
# ``## Done this cycle (ARG1-001)`` carry a suffix and are intentionally not
# picked up (mirrors cycle_close._SECTION_HEADING_RE).
_DONE_HEADING_RE = re.compile(rf"^## {re.escape(_DONE_SECTION)}\s*$")
_QUEUE_HEADING_RE = re.compile(r"^## Queue\s*$")
_NEXT_HEADING_RE = re.compile(r"^## ")

# A markdown list bullet (allowing leading indentation), capturing the body
# after the dash + space. Mirrors argos.cli.queue._BULLET_RE.
_BULLET_RE = re.compile(r"^\s*-\s+(?P<body>.*\S)\s*$")


class CleanQueueError(Exception):
    """Base class for clean-queue failures surfaced through the CLI."""


class QueueSectionMissingError(CleanQueueError):
    """``## Queue`` heading is absent from STATE.md."""


@dataclass
class CleanQueueResult:
    removed_ids: list = field(default_factory=list)
    committed: bool = False


def _find_section_bounds(
    lines: list, heading_re: "re.Pattern"
) -> "tuple[int, int] | None":
    """Return ``(heading_idx, next_heading_idx)`` for ``heading_re``.

    Both are 0-indexed. ``next_heading_idx`` is the line of the following
    ``## `` heading or ``len(lines)`` if none. Returns ``None`` if the
    heading is absent.
    """
    heading_idx = -1
    for idx, line in enumerate(lines):
        if heading_re.match(line):
            heading_idx = idx
            break
    if heading_idx == -1:
        return None

    next_idx = len(lines)
    for idx in range(heading_idx + 1, len(lines)):
        if _NEXT_HEADING_RE.match(lines[idx]):
            next_idx = idx
            break
    return heading_idx, next_idx


def _ticket_id_in_bullet(bullet_body: str) -> "str | None":
    """Return the ticket id leading ``bullet_body`` if it is id-shaped."""
    head = bullet_body.split(None, 1)[0] if bullet_body else ""
    if TICKET_ID_RE.match(head):
        return head
    return None


def _done_section_ticket_ids(text: str, lines: list) -> set:
    """Ticket ids recorded in the live ``## Done this cycle`` section.

    Bounded to the exact ``## Done this cycle`` heading; blocks inside the
    section contribute their ``ticket=`` attribute. Returns an empty set if
    the section is absent or holds no blocks.
    """
    bounds = _find_section_bounds(lines, _DONE_HEADING_RE)
    if bounds is None:
        return set()
    heading_idx, next_heading_idx = bounds
    blocks = parse_state(text)
    return {
        b.ticket
        for b in blocks
        if heading_idx < (b.start_line - 1) < next_heading_idx
    }


def _archive_ticket_ids(cycles_dir: Path) -> set:
    """Ticket ids recorded in any ``argos/specs/cycles/*.md`` archive.

    Each archive's ``argos:entry`` blocks contribute their ``ticket=``
    attribute. A missing directory yields an empty set. A malformed archive
    is surfaced as a ``CleanQueueError`` rather than silently dropping ids.
    """
    if not cycles_dir.is_dir():
        return set()
    ids: set = set()
    for path in sorted(cycles_dir.glob("*.md")):
        try:
            blocks = parse_state(path.read_text(encoding="utf-8"))
        except StateBlockError as exc:
            raise CleanQueueError(f"malformed cycle archive {path}: {exc}") from exc
        ids.update(b.ticket for b in blocks)
    return ids


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via tempfile + os.replace (atomic on POSIX)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".tmp.", dir=str(path.parent)
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp:
            tmp.write(text)
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


def _git(args: list, *, cwd: Path, env: "dict | None" = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _git_check(args: list, *, cwd: Path, env: "dict | None" = None) -> subprocess.CompletedProcess:
    res = _git(args, cwd=cwd, env=env)
    if res.returncode != 0:
        raise CleanQueueError(
            f"git {' '.join(args)} failed (rc={res.returncode}): "
            f"stdout={res.stdout!r} stderr={res.stderr!r}"
        )
    return res


def clean_queue(
    *,
    state_file: Path,
    cycles_dir: Path,
    repo_root: Path,
    dry_run: bool = False,
) -> "CleanQueueResult | None":
    """Remove shipped tickets from ``## Queue``; return result or ``None``.

    Returns ``None`` when no queue bullet matches a shipped ticket id (empty
    queue, no shipped entries, or an already-cleaned queue — the idempotent
    no-op). Otherwise performs the rewrite and (unless ``dry_run``) creates
    one git commit on the current branch.
    """
    state_path = Path(state_file)
    cycles_path = Path(cycles_dir)
    repo_path = Path(repo_root)

    if not state_path.exists():
        raise CleanQueueError(f"state file not found: {state_path}")

    text = state_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    queue_bounds = _find_section_bounds(lines, _QUEUE_HEADING_RE)
    if queue_bounds is None:
        raise QueueSectionMissingError("STATE.md has no '## Queue' section")
    queue_start, queue_end = queue_bounds

    shipped_ids = _done_section_ticket_ids(text, lines) | _archive_ticket_ids(cycles_path)

    # Identify queue bullet lines whose leading ticket id has shipped.
    removed_ids: list = []
    drop_idxs: set = set()
    for idx in range(queue_start + 1, queue_end):
        m = _BULLET_RE.match(lines[idx])
        if not m:
            continue
        ticket_id = _ticket_id_in_bullet(m.group("body"))
        if ticket_id is not None and ticket_id in shipped_ids:
            drop_idxs.add(idx)
            removed_ids.append(ticket_id)

    if not drop_idxs:
        return None

    # Rebuild from the keepends view so line endings are preserved exactly.
    # splitlines() and splitlines(keepends=True) index identically.
    kept = text.splitlines(keepends=True)
    new_state_text = "".join(
        line for i, line in enumerate(kept) if i not in drop_idxs
    )

    result = CleanQueueResult(removed_ids=removed_ids, committed=False)

    if dry_run:
        return result

    _atomic_write(state_path, new_state_text)

    # Pre-commit hook (ARG1-032) blocks STATE.md deletions unless
    # ARGOS_CYCLE_CLOSE=1 is set. Export the bypass for the single commit
    # invocation only — ``git add`` does not trigger the hook.
    state_rel = os.path.relpath(state_path, repo_path)
    _git_check(["add", "--", state_rel], cwd=repo_path)

    commit_env = os.environ.copy()
    commit_env["ARGOS_CYCLE_CLOSE"] = "1"
    _git_check(
        ["commit", "-m", f"clean queue: remove {len(removed_ids)} shipped ticket(s)"],
        cwd=repo_path,
        env=commit_env,
    )

    result.committed = True
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argos sync --clean-queue",
        description=(
            "Remove tickets that have already shipped (recorded in "
            "'## Done this cycle' or argos/specs/cycles/*.md) from the "
            "'## Queue' section of STATE.md and commit the result (ARG1-068)."
        ),
    )
    parser.add_argument(
        "--state-file",
        default=_DEFAULT_STATE_FILE,
        help="path to STATE.md (default: %(default)s)",
    )
    parser.add_argument(
        "--cycles-dir",
        default=_DEFAULT_CYCLES_DIR,
        help="directory of dated cycle archives (default: %(default)s)",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="git repo root (default: derived via 'git rev-parse --show-toplevel')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would be removed without modifying STATE.md or committing",
    )
    return parser


def _resolve_repo_root(arg: "str | None") -> Path:
    if arg is not None:
        return Path(arg).resolve()
    res = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise CleanQueueError(
            f"could not determine repo root (git rev-parse --show-toplevel "
            f"exited {res.returncode}): {res.stderr.strip()}"
        )
    return Path(res.stdout.strip()).resolve()


def main(argv: list) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    try:
        repo_root = _resolve_repo_root(args.repo_root)
    except CleanQueueError as exc:
        sys.stderr.write(f"sync --clean-queue: {exc}\n")
        return 1

    state_path = Path(args.state_file)
    if not state_path.is_absolute():
        state_path = (repo_root / state_path).resolve()
    cycles_path = Path(args.cycles_dir)
    if not cycles_path.is_absolute():
        cycles_path = (repo_root / cycles_path).resolve()

    try:
        result = clean_queue(
            state_file=state_path,
            cycles_dir=cycles_path,
            repo_root=repo_root,
            dry_run=args.dry_run,
        )
    except QueueSectionMissingError as exc:
        sys.stderr.write(f"sync --clean-queue: section not found: {exc}\n")
        return 1
    except CleanQueueError as exc:
        sys.stderr.write(f"sync --clean-queue: {exc}\n")
        return 1

    if result is None:
        sys.stdout.write("nothing to clean\n")
        return 0

    joined = ", ".join(result.removed_ids)
    if args.dry_run:
        sys.stdout.write(
            f"would remove {len(result.removed_ids)} shipped ticket(s) "
            f"from '## Queue' in {state_path}: {joined}\n"
        )
        return 0

    sys.stdout.write(
        f"removed {len(result.removed_ids)} shipped ticket(s) from "
        f"'## Queue': {joined}; committed\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
