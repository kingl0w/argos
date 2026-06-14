"""``argos sync --close-cycle`` — archive ``## Done this cycle`` blocks.

ARG1-054 / ARCHITECTURE.md §Contracts/STATE.md format. The single operation
that legitimately *removes* blocks from STATE.md: every entry under the
``## Done this cycle`` heading is moved verbatim into a dated archive at
``argos/specs/cycles/{YYYY-MM-DD}.md`` (UTC date of the close), the section
in STATE.md is cleared, and the change is committed in one git commit
labelled ``cycle close YYYY-MM-DD``.

Structural-rewrite discipline:
- The STATE.md rewrite is a deletion, which the ARG1-032 pre-commit hook
  refuses unless ``ARGOS_CYCLE_CLOSE=1`` is set. The bypass is exported only
  for the single ``git commit`` invocation, not for any incidental write.
- File writes use ``tempfile`` + ``os.replace`` so a SIGKILL mid-rewrite
  leaves either the old or new file intact, never a torn write.

Stdlib only — ADR-001 / ADR-002.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from argos.cli.spec_paths import default_state_file
from argos.cli.state_parser import Block, parse as parse_state

__all__ = [
    "CycleCloseResult",
    "close_cycle",
    "main",
]

_DEFAULT_CYCLES_DIR = "argos/specs/cycles"
_DONE_SECTION = "Done this cycle"
_SECTION_HEADING_RE = re.compile(rf"^## {re.escape(_DONE_SECTION)}\s*$")
_NEXT_HEADING_RE = re.compile(r"^## ")


class CycleCloseError(Exception):
    """Base class for cycle-close failures surfaced through the CLI."""


class SectionNotFoundError(CycleCloseError):
    """``## Done this cycle`` heading is absent from STATE.md."""


@dataclass
class CycleCloseResult:
    archived_count: int
    cycle_file: Path
    today_utc: str
    committed: bool
    appended_to_existing: bool


def _utc_today(now: datetime | None) -> str:
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    return now.strftime("%Y-%m-%d")


def _find_done_section_bounds(lines: list[str]) -> tuple[int, int]:
    """Return ``(heading_idx, next_heading_idx)`` for ``## Done this cycle``.

    Both are 0-indexed line positions. ``next_heading_idx`` is the line of
    the following ``## `` heading or ``len(lines)`` if none.

    The regex matches the heading exactly so an existing archive heading
    such as ``## Done this cycle (ARG1-001)`` (which appears in the v1.0
    STATE.md as historical archive content) is not picked up.
    """
    heading_idx = -1
    for idx, line in enumerate(lines):
        if _SECTION_HEADING_RE.match(line):
            heading_idx = idx
            break
    if heading_idx == -1:
        raise SectionNotFoundError(_DONE_SECTION)

    next_idx = len(lines)
    for idx in range(heading_idx + 1, len(lines)):
        if _NEXT_HEADING_RE.match(lines[idx]):
            next_idx = idx
            break
    return heading_idx, next_idx


def _blocks_in_section(
    blocks: list[Block], heading_idx: int, next_heading_idx: int
) -> list[Block]:
    """Filter ``blocks`` to those whose open tag falls inside the section.

    ``heading_idx`` and ``next_heading_idx`` are 0-indexed; ``Block.start_line``
    is 1-indexed. A block's open tag is "inside" the section iff its line is
    strictly between the two heading lines.
    """
    return [
        b for b in blocks
        if heading_idx < (b.start_line - 1) < next_heading_idx
    ]


def _extract_block_text(text: str, block: Block) -> str:
    """Return the verbatim block text (open tag through close tag, inclusive)."""
    lines = text.splitlines(keepends=True)
    # start_line / end_line are 1-indexed inclusive.
    return "".join(lines[block.start_line - 1 : block.end_line])


def _clear_done_section(
    text: str, heading_idx: int, next_heading_idx: int
) -> str:
    """Replace the body of ``## Done this cycle`` with the empty placeholder.

    Body becomes ``\\n_none_\\n\\n`` to mirror the project convention used by
    ``## In progress`` when no entries are present (see argos/specs/v1.0/STATE.md
    fixture under ``_STATE_FIXTURE`` in tests/test_state_append.py).
    """
    lines = text.splitlines(keepends=True)
    placeholder = ["\n", "_none_\n", "\n"]
    new_lines = lines[: heading_idx + 1] + placeholder + lines[next_heading_idx:]
    return "".join(new_lines)


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


def _build_cycle_file_text(
    block_texts: list[str], today_utc: str, *, append_to_existing: bool
) -> str:
    """Compose the bytes to append to (or seed) the cycle archive file.

    First write of the day: a header line and the blocks separated by blank
    lines. Subsequent same-day calls: a blank-line separator followed by the
    new blocks (no second header).
    """
    parts: list[str] = []
    if not append_to_existing:
        parts.append(f"# Argos cycle archive — {today_utc}\n\n")
    else:
        parts.append("\n")
    for idx, btext in enumerate(block_texts):
        if idx > 0:
            parts.append("\n")
        parts.append(btext if btext.endswith("\n") else btext + "\n")
    return "".join(parts)


def _git(args: list[str], *, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _git_check(args: list[str], *, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    res = _git(args, cwd=cwd, env=env)
    if res.returncode != 0:
        raise CycleCloseError(
            f"git {' '.join(args)} failed (rc={res.returncode}): "
            f"stdout={res.stdout!r} stderr={res.stderr!r}"
        )
    return res


def close_cycle(
    *,
    state_file: Path,
    cycles_dir: Path,
    repo_root: Path,
    dry_run: bool = False,
    now: datetime | None = None,
) -> CycleCloseResult | None:
    """Archive ``## Done this cycle`` blocks; return result or None if no-op.

    Returns ``None`` when the section is empty (idempotent same-day re-run).
    Otherwise performs the rewrite and (unless ``dry_run``) creates one git
    commit on the current branch.
    """
    state_path = Path(state_file)
    cycles_path = Path(cycles_dir)
    repo_path = Path(repo_root)

    if not state_path.exists():
        raise CycleCloseError(f"state file not found: {state_path}")

    text = state_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    heading_idx, next_heading_idx = _find_done_section_bounds(lines)

    blocks = parse_state(text)
    cycle_blocks = _blocks_in_section(blocks, heading_idx, next_heading_idx)

    if not cycle_blocks:
        return None

    today = _utc_today(now)
    cycle_file = cycles_path / f"{today}.md"
    append_to_existing = cycle_file.exists()

    block_texts = [_extract_block_text(text, b) for b in cycle_blocks]
    archive_payload = _build_cycle_file_text(
        block_texts, today, append_to_existing=append_to_existing
    )
    new_state_text = _clear_done_section(text, heading_idx, next_heading_idx)

    result = CycleCloseResult(
        archived_count=len(cycle_blocks),
        cycle_file=cycle_file,
        today_utc=today,
        committed=False,
        appended_to_existing=append_to_existing,
    )

    if dry_run:
        return result

    if append_to_existing:
        existing = cycle_file.read_text(encoding="utf-8")
        if existing and not existing.endswith("\n"):
            existing += "\n"
        _atomic_write(cycle_file, existing + archive_payload)
    else:
        _atomic_write(cycle_file, archive_payload)

    _atomic_write(state_path, new_state_text)

    # Pre-commit hook (ARG1-032) blocks STATE.md deletions unless
    # ARGOS_CYCLE_CLOSE=1 is set. Export the bypass for the single commit
    # invocation only — ``git add`` does not trigger the hook.
    state_rel = os.path.relpath(state_path, repo_path)
    cycle_rel = os.path.relpath(cycle_file, repo_path)
    _git_check(["add", "--", state_rel, cycle_rel], cwd=repo_path)

    commit_env = os.environ.copy()
    commit_env["ARGOS_CYCLE_CLOSE"] = "1"
    _git_check(
        ["commit", "-m", f"cycle close {today}"],
        cwd=repo_path,
        env=commit_env,
    )

    result.committed = True
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argos sync --close-cycle",
        description=(
            "Archive '## Done this cycle' blocks from STATE.md into "
            "argos/specs/cycles/YYYY-MM-DD.md and commit the cleared "
            "STATE.md (ARG1-054)."
        ),
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help=(
            "path to STATE.md (default: auto-detected — argos/specs/v1.0/STATE.md "
            "if present, else argos/specs/STATE.md)"
        ),
    )
    parser.add_argument(
        "--cycles-dir",
        default=_DEFAULT_CYCLES_DIR,
        help="directory for dated archive files (default: %(default)s)",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="git repo root (default: derived via 'git rev-parse --show-toplevel')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="describe the rewrite and commit without performing them",
    )
    return parser


def _resolve_repo_root(arg: str | None) -> Path:
    if arg is not None:
        return Path(arg).resolve()
    res = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise CycleCloseError(
            f"could not determine repo root (git rev-parse --show-toplevel "
            f"exited {res.returncode}): {res.stderr.strip()}"
        )
    return Path(res.stdout.strip()).resolve()


def main(argv: list[str]) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    try:
        repo_root = _resolve_repo_root(args.repo_root)
    except CycleCloseError as exc:
        sys.stderr.write(f"sync --close-cycle: {exc}\n")
        return 1

    state_path = Path(args.state_file or default_state_file(repo_root))
    if not state_path.is_absolute():
        state_path = (repo_root / state_path).resolve()
    cycles_path = Path(args.cycles_dir)
    if not cycles_path.is_absolute():
        cycles_path = (repo_root / cycles_path).resolve()

    try:
        result = close_cycle(
            state_file=state_path,
            cycles_dir=cycles_path,
            repo_root=repo_root,
            dry_run=args.dry_run,
        )
    except SectionNotFoundError as exc:
        sys.stderr.write(f"sync --close-cycle: section not found: {exc}\n")
        return 1
    except CycleCloseError as exc:
        sys.stderr.write(f"sync --close-cycle: {exc}\n")
        return 1

    if result is None:
        sys.stdout.write("nothing to close\n")
        return 0

    if args.dry_run:
        sys.stdout.write(
            f"would archive {result.archived_count} block(s) to "
            f"{result.cycle_file} (cycle {result.today_utc})"
            + (" [append]" if result.appended_to_existing else " [new]")
            + " and clear '## Done this cycle' in "
            f"{state_path}; would commit 'cycle close {result.today_utc}'\n"
        )
        return 0

    sys.stdout.write(
        f"archived {result.archived_count} block(s) to "
        f"{result.cycle_file}; committed 'cycle close {result.today_utc}'\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
