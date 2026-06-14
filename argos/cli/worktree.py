"""Worktree spawn primitives for ``argos run-session`` (ARG1-020).

The orchestrator (ARG1-022) dispatches a per-ticket session by invoking
``argos run-session --ticket ARG1-NNN --worktree <path> --epic EPIC-NNN``.
That CLI shim is :mod:`argos.cli.commands.run_session`; this module is the
library it delegates to.

Responsibilities:

- Resolve and validate the worktree path. It must live under
  ``<repo_root>/.argos/worktrees/`` (ARCHITECTURE.md §Components/Parallel
  Session Manager pins the layout). Anything outside is rejected.
- Compute the canonical branch name ``argos/{ticket_id}``.
- Detect whether a worktree at the requested path already exists (either
  registered with git or sitting on disk) and refuse to reuse it.
- Run ``git worktree add`` from the repo root.
- Resolve the harness binary used to spawn the per-ticket Claude Code
  session. Resolution order: ``ARGOS_RUN_SESSION_HARNESS_BIN`` env override
  → ``harness.claude_code_binary`` from the loaded config (ARG1-053) →
  ``claude`` on PATH.
- Spawn the session **headlessly** (ARG1-069) with cwd pinned to the
  worktree path: ``claude -p "<prompt>" --dangerously-skip-permissions``.
  The prompt is auto-built from the ticket file (resolved inside the
  worktree) plus the standing argos rules, so the session lands with a
  full instruction instead of an empty interactive shell. Headless mode
  (``-p``) needs no tty, so parallel dispatch works without terminal
  contention.

ADR-001: Python ≥3.9 stdlib only. Subprocess to git is the contract; no
third-party imports.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Sequence

from argos.cli.orchestrator import session_prompt

__all__ = [
    "WorktreeError",
    "InvalidWorktreePathError",
    "WorktreeAlreadyExistsError",
    "GitError",
    "HarnessNotFoundError",
    "BRANCH_PREFIX",
    "WORKTREES_SUBDIR",
    "HARNESS_ENV_VAR",
    "TICKET_SUBDIR_IN_WORKTREE",
    "compute_branch_name",
    "find_repo_root",
    "validate_worktree_path",
    "worktree_path_listed",
    "add_worktree",
    "resolve_harness_binary",
    "spawn_session",
]


BRANCH_PREFIX = "argos"
WORKTREES_SUBDIR = (".argos", "worktrees")
HARNESS_ENV_VAR = "ARGOS_RUN_SESSION_HARNESS_BIN"
# Where the ticket file lives inside a spawned worktree, relative to its
# root. The prompt-builder (ARG1-069) reads from here to inline the ticket.
TICKET_SUBDIR_IN_WORKTREE = "argos/specs/v1.0/tickets"


class WorktreeError(Exception):
    """Base class for run-session helper errors."""


class InvalidWorktreePathError(WorktreeError):
    """The requested worktree path is outside ``.argos/worktrees/``."""


class WorktreeAlreadyExistsError(WorktreeError):
    """A worktree (or a plain directory) already sits at the target path."""


class GitError(WorktreeError):
    """A git subprocess returned non-zero. Carries stderr for diagnosis."""

    def __init__(self, message: str, *, stderr: str = "", returncode: int = 1) -> None:
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode


class HarnessNotFoundError(WorktreeError):
    """The configured Claude Code harness binary cannot be located on PATH."""


def compute_branch_name(ticket_id: str) -> str:
    """Return the canonical branch name for ``ticket_id`` (``argos/<id>``)."""
    if not ticket_id:
        raise ValueError("ticket_id must be non-empty")
    if "/" in ticket_id or any(ch.isspace() for ch in ticket_id):
        raise ValueError(f"invalid ticket id: {ticket_id!r}")
    return f"{BRANCH_PREFIX}/{ticket_id}"


def find_repo_root(start: Optional[Path] = None) -> Path:
    """Return the absolute path of the enclosing git repo root.

    Uses ``git rev-parse --show-toplevel`` against ``start`` (defaults to
    CWD). Raises :class:`GitError` if ``start`` is not inside a repo.
    """
    cwd = Path(start).resolve() if start is not None else Path.cwd()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GitError(
            "not a git repository",
            stderr=result.stderr.strip(),
            returncode=result.returncode,
        )
    return Path(result.stdout.strip()).resolve()


def _worktrees_root(repo_root: Path) -> Path:
    return repo_root.joinpath(*WORKTREES_SUBDIR)


def validate_worktree_path(repo_root: Path, worktree: str | os.PathLike[str]) -> Path:
    """Resolve ``worktree`` and confirm it lives under ``.argos/worktrees/``.

    Relative inputs resolve against CWD. Symlinks and ``..`` segments are
    collapsed via :meth:`pathlib.Path.resolve`. Returns the absolute path.

    Raises :class:`InvalidWorktreePathError` if the resolved path is not a
    strict descendant of ``<repo_root>/.argos/worktrees/``. Bare equality
    with the worktrees root is also rejected — a worktree must have its
    own subdirectory name.
    """
    repo_root = repo_root.resolve()
    raw = Path(worktree)
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    resolved = raw.resolve()
    root = _worktrees_root(repo_root).resolve()
    try:
        rel = resolved.relative_to(root)
    except ValueError as exc:
        raise InvalidWorktreePathError(
            "worktree must live under .argos/worktrees/"
        ) from exc
    if rel == Path("."):
        raise InvalidWorktreePathError(
            "worktree must live under .argos/worktrees/"
        )
    return resolved


def _parse_worktree_list(stdout: str) -> list[Path]:
    """Extract absolute worktree paths from ``git worktree list --porcelain``."""
    paths: list[Path] = []
    for line in stdout.splitlines():
        if line.startswith("worktree "):
            paths.append(Path(line[len("worktree ") :]).resolve())
    return paths


def worktree_path_listed(repo_root: Path, worktree_abs: Path) -> bool:
    """Return True if ``worktree_abs`` is registered with git as a worktree."""
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GitError(
            "git worktree list failed",
            stderr=result.stderr.strip(),
            returncode=result.returncode,
        )
    target = worktree_abs.resolve()
    return target in _parse_worktree_list(result.stdout)


def add_worktree(repo_root: Path, worktree_abs: Path, branch: str) -> None:
    """Run ``git worktree add -b <branch> <path>`` from ``repo_root``.

    On failure, classifies "already exists" stderr substrings as
    :class:`WorktreeAlreadyExistsError`; everything else as
    :class:`GitError`.
    """
    worktree_abs.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(worktree_abs)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return
    err = result.stderr.strip()
    if "already exists" in err.lower():
        raise WorktreeAlreadyExistsError(err)
    raise GitError(
        "git worktree add failed",
        stderr=err,
        returncode=result.returncode,
    )


def resolve_harness_binary(
    *,
    env: Optional[dict[str, str]] = None,
    configured: Optional[str] = None,
) -> str:
    """Pick the Claude Code harness binary path.

    Order of precedence:

    1. ``ARGOS_RUN_SESSION_HARNESS_BIN`` from ``env`` (defaults to
       :data:`os.environ`). An explicit override always wins; useful for
       testing and one-off runs.
    2. ``configured`` — typically ``harness.claude_code_binary`` from the
       loaded config (ARG1-053). Pass ``None`` to skip.
    3. ``claude`` resolved via :func:`shutil.which`.

    Returns the resolved path string. Raises
    :class:`HarnessNotFoundError` if no candidate is locatable.
    """
    if env is None:
        env = os.environ  # type: ignore[assignment]
    override = env.get(HARNESS_ENV_VAR)
    candidates: list[str] = []
    if override:
        candidates.append(override)
    if configured:
        candidates.append(configured)
    candidates.append("claude")
    for cand in candidates:
        if not cand:
            continue
        if os.path.isabs(cand):
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
            continue
        resolved = shutil.which(cand)
        if resolved is not None:
            return resolved
    raise HarnessNotFoundError(
        f"could not locate Claude Code harness binary "
        f"(set {HARNESS_ENV_VAR} or harness.claude_code_binary)"
    )


def spawn_session(
    binary: str,
    worktree_abs: Path,
    *,
    ticket: str,
    epic: str,
    extra_args: Optional[Sequence[str]] = None,
    env: Optional[dict[str, str]] = None,
    permission_arg: str = session_prompt.DEFAULT_PERMISSION_ARG,
    ticket_dir: Optional[Path] = None,
) -> int:
    """Run ``binary`` headlessly in ``worktree_abs``; return its exit code.

    The harness is invoked as::

        binary -p "<prompt>" --dangerously-skip-permissions

    (ARG1-069). The prompt is auto-built by
    :mod:`argos.cli.orchestrator.session_prompt` from the ticket file —
    resolved under ``<worktree_abs>/argos/specs/v1.0/tickets`` (overridable
    via ``ticket_dir``) — plus the standing argos rules, so the spawned
    session lands with a full instruction. If the ticket file is absent from
    the worktree, the prompt degrades to a read-the-file instruction rather
    than failing the spawn.

    Headless ``-p`` needs no tty, so parallel dispatch works without terminal
    contention. Stdio is inherited from the calling process, so the harness's
    output flows to the orchestrator (where the dispatch loop logs it).

    ``permission_arg`` is the trailing permission flag (default
    :data:`session_prompt.DEFAULT_PERMISSION_ARG`); pass a different value to
    select another permission mode. ``extra_args`` are appended after the
    harness flags for one-off needs (no caller currently uses them).

    Three context env vars are exported to the child so downstream tooling
    (the session's planner, future hooks) can read them without re-parsing
    argv:

    - ``ARGOS_TICKET``
    - ``ARGOS_EPIC``
    - ``ARGOS_WORKTREE``
    """
    child_env = dict(os.environ if env is None else env)
    child_env["ARGOS_TICKET"] = ticket
    child_env["ARGOS_EPIC"] = epic
    child_env["ARGOS_WORKTREE"] = str(worktree_abs)

    if ticket_dir is None:
        ticket_dir = worktree_abs / TICKET_SUBDIR_IN_WORKTREE
    prompt = session_prompt.build_prompt_for_ticket(ticket, ticket_dir=ticket_dir)

    cmd = [binary, "-p", prompt, permission_arg]
    if extra_args:
        cmd.extend(extra_args)
    completed = subprocess.run(
        cmd,
        cwd=str(worktree_abs),
        env=child_env,
        check=False,
    )
    return completed.returncode
