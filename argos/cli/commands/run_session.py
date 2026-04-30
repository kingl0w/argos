"""``argos run-session`` — per-ticket worktree spawn helper (ARG1-020).

Usage::

    argos run-session --ticket ARG1-099 \\
        --worktree .argos/worktrees/ARG1-099-test --epic EPIC-001 \\
        [--dry-run] [--debug-print-cwd]

Behavior:

- Validates ``--worktree`` lives under ``<repo_root>/.argos/worktrees/``
  (per ARCHITECTURE.md §Components/Parallel Session Manager).
- Refuses to overwrite or reuse an existing worktree at that path.
- Creates the worktree branched as ``argos/<ticket-id>``.
- Spawns the configured Claude Code harness with cwd pinned to the
  worktree path. Returns the spawned process's exit code.

Diagnostic flags:

- ``--dry-run`` resolves the branch + absolute worktree path and prints
  them to stdout without touching git or spawning anything. Exit 0.
- ``--debug-print-cwd`` validates inputs, creates the worktree, then
  prints the absolute worktree path it would have spawned the session in
  and exits 0 without invoking the harness binary. Used to verify the
  CWD-isolation invariant from outside an actual session.

Error contracts (stderr substrings consumed by ACs):

- ``worktree must live under .argos/worktrees/`` — invalid path
- ``worktree already exists`` — duplicate dispatch
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from argos.cli.worktree import (
    GitError,
    HarnessNotFoundError,
    InvalidWorktreePathError,
    WorktreeAlreadyExistsError,
    add_worktree,
    compute_branch_name,
    find_repo_root,
    resolve_harness_binary,
    spawn_session,
    validate_worktree_path,
    worktree_path_listed,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argos run-session",
        description="Spawn a per-ticket Claude Code session in a fresh worktree.",
    )
    parser.add_argument("--ticket", required=True, help="ticket id (e.g. ARG1-099)")
    parser.add_argument(
        "--worktree",
        required=True,
        help="path under .argos/worktrees/ to host the session",
    )
    parser.add_argument("--epic", required=True, help="epic id (e.g. EPIC-001)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the resolved branch and worktree path; do not create or spawn",
    )
    parser.add_argument(
        "--debug-print-cwd",
        action="store_true",
        help=(
            "create the worktree but do not spawn; print the absolute worktree "
            "path the session would have used (verifies CWD pinning)"
        ),
    )
    return parser


def _load_configured_binary() -> str | None:
    """Best-effort load of ``harness.claude_code_binary`` from ARG1-053 config.

    Returns ``None`` if the config loader is unavailable or the key is
    not set. Errors are swallowed deliberately — the env-var override and
    the ``claude``-on-PATH fallback are the test/prod paths and must keep
    working when no config is initialized yet.
    """
    try:
        from argos.cli.config import KeyNotFoundError, load
    except Exception:
        return None
    try:
        cfg = load()
    except Exception:
        return None
    try:
        return cfg.get("harness.claude_code_binary")
    except KeyNotFoundError:
        return None
    except Exception:
        return None


def main(argv: list[str]) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    branch = compute_branch_name(args.ticket)

    try:
        repo_root = find_repo_root()
    except GitError as exc:
        sys.stderr.write(f"run-session: {exc}\n")
        if exc.stderr:
            sys.stderr.write(f"run-session: git: {exc.stderr}\n")
        return 1

    try:
        worktree_abs = validate_worktree_path(repo_root, args.worktree)
    except InvalidWorktreePathError as exc:
        sys.stderr.write(f"run-session: {exc}\n")
        return 2

    if args.dry_run:
        sys.stdout.write(f"branch: {branch}\n")
        sys.stdout.write(f"worktree: {worktree_abs}\n")
        return 0

    try:
        already_listed = worktree_path_listed(repo_root, worktree_abs)
    except GitError as exc:
        sys.stderr.write(f"run-session: {exc}\n")
        if exc.stderr:
            sys.stderr.write(f"run-session: git: {exc.stderr}\n")
        return 1

    if already_listed or worktree_abs.exists():
        sys.stderr.write(
            f"run-session: worktree already exists: {worktree_abs}\n"
        )
        return 1

    try:
        add_worktree(repo_root, worktree_abs, branch)
    except WorktreeAlreadyExistsError as exc:
        sys.stderr.write(
            f"run-session: worktree already exists: {worktree_abs}\n"
        )
        if str(exc):
            sys.stderr.write(f"run-session: git: {exc}\n")
        return 1
    except GitError as exc:
        sys.stderr.write(f"run-session: {exc}\n")
        if exc.stderr:
            sys.stderr.write(f"run-session: git: {exc.stderr}\n")
        return 1

    if args.debug_print_cwd:
        sys.stdout.write(f"{worktree_abs}\n")
        return 0

    try:
        binary = resolve_harness_binary(configured=_load_configured_binary())
    except HarnessNotFoundError as exc:
        sys.stderr.write(f"run-session: {exc}\n")
        return 1

    return spawn_session(
        binary,
        worktree_abs,
        ticket=args.ticket,
        epic=args.epic,
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
