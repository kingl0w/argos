"""``argos sync`` — reconcile tickets, Issues, STATE.md, and worktrees (ARG1-004).

Three reconciliations, run in order and reported as a one-line-per-phase
status table on stdout:

1. **issues** — re-render existing GitHub Issue bodies from ticket markdown
   (the only network-touching phase; skipped by ``--no-issues``).
2. **state-git** — verify every ``## Done this cycle`` ticket traces to a
   commit on ``git log --first-parent <main>``. A done-but-unmerged ticket is
   a ``MISMATCH``: sync names it on stderr and exits non-zero, never
   auto-correcting STATE.md.
3. **worktrees** — prune worktrees under ``.argos/worktrees/`` whose branch is
   merged into main and deleted from ``origin``.

The status vocabulary is ``OK`` / ``WOULD-FIX`` / ``MISMATCH`` under
``--dry-run`` (which always exits 0) and ``OK`` / ``FIXED`` / ``MISMATCH`` on
a real run (which exits non-zero iff state-git reports a ``MISMATCH``).

Two delegating flags short-circuit the full sync:

- ``--close-cycle`` → :mod:`argos.cli.commands.cycle_close` (ARG1-054).
- ``--clean-queue`` → :mod:`argos.cli.commands.clean_queue` (ARG1-068).

Both strip their own flag and forward the remaining args verbatim, returning
the delegate's exit code unchanged (AC#4).

ADR-001 / ADR-002: Python ≥3.9, standard library only.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from argos.cli import reconcile
from argos.cli.reconcile import PhaseResult, ReconcileError
from argos.cli.spec_paths import default_spec_paths

__all__ = ["main", "run_sync"]


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
        raise ReconcileError(
            f"could not determine repo root (git rev-parse --show-toplevel "
            f"exited {res.returncode}): {res.stderr.strip()}"
        )
    return Path(res.stdout.strip()).resolve()


def _resolve(repo_root: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (repo_root / p).resolve()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argos sync",
        description=(
            "Reconcile ticket files with GitHub Issues, STATE.md's "
            "'## Done this cycle' with git history, and prune stale worktrees "
            "under .argos/worktrees/ (ARG1-004)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report each phase without applying any change; always exits 0",
    )
    parser.add_argument(
        "--no-issues",
        action="store_true",
        help="skip the GitHub Issue phase entirely (works offline)",
    )
    parser.add_argument(
        "--main-ref",
        default=reconcile.DEFAULT_MAIN_REF,
        help="main branch ref for the state-git and worktree phases "
        "(default: %(default)s)",
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
        "--tickets-dir",
        default=None,
        help=(
            "directory of ticket markdown files (default: auto-detected alongside "
            "STATE.md — argos/specs/v1.0/tickets or argos/specs/tickets)"
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="git repo root (default: derived via 'git rev-parse --show-toplevel')",
    )
    return parser


def _render_table(results: "list[PhaseResult]", *, dry_run: bool) -> str:
    """Render the status table — one aligned line per phase."""
    name_w = max((len(r.name) for r in results), default=0)
    status_w = max((len(r.status) for r in results), default=0)
    lines = []
    header = "argos sync (dry-run)" if dry_run else "argos sync"
    lines.append(f"{header}:")
    for r in results:
        lines.append(
            f"  {r.name.ljust(name_w)}  {r.status.ljust(status_w)}  {r.summary}"
        )
    return "\n".join(lines) + "\n"


def run_sync(
    *,
    repo_root: Path,
    state_file: Path,
    tickets_dir: Path,
    main_ref: str,
    dry_run: bool,
    no_issues: bool,
    issue_backend=None,
    out=sys.stdout,
    err=sys.stderr,
) -> int:
    """Run the three reconciliation phases and return the process exit code.

    Phases are computed independently; the issues and worktree phases apply
    their fixes (unless ``dry_run``) while state-git is always read-only. The
    full status table prints to ``out`` regardless of outcome; on a state-git
    ``MISMATCH`` the per-ticket detail lines print to ``err`` and the function
    returns 1 (AC#3). ``--dry-run`` always returns 0 (AC#1).
    """
    results: "list[PhaseResult]" = []

    # Phase 1: issues (network) — applied on a real run.
    results.append(
        reconcile.reconcile_issues(
            tickets_dir=tickets_dir,
            repo_root=repo_root,
            dry_run=dry_run,
            backend=issue_backend,
            skip=no_issues,
        )
    )

    # Phase 2: state-git — read-only check.
    state_git = reconcile.reconcile_state_git(
        state_file=state_file,
        repo_root=repo_root,
        main_ref=main_ref,
    )
    results.append(state_git)

    # Phase 3: worktree pruning — applied on a real run.
    results.append(
        reconcile.reconcile_worktrees(
            repo_root=repo_root,
            main_ref=main_ref,
            dry_run=dry_run,
        )
    )

    out.write(_render_table(results, dry_run=dry_run))

    if state_git.is_mismatch and not dry_run:
        for line in state_git.details:
            err.write(f"sync: state-git MISMATCH: {line}\n")
        return 1

    return 0


def main(argv: list) -> int:
    # Delegating flags short-circuit the full sync (AC#4). They are detected
    # before argparse so their own parsers own the remaining argv.
    if "--close-cycle" in argv:
        from argos.cli.commands.cycle_close import main as cycle_close_main

        return cycle_close_main([a for a in argv if a != "--close-cycle"])
    if "--clean-queue" in argv:
        from argos.cli.commands.clean_queue import main as clean_queue_main

        return clean_queue_main([a for a in argv if a != "--clean-queue"])

    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    try:
        repo_root = _resolve_repo_root(args.repo_root)
    except ReconcileError as exc:
        sys.stderr.write(f"sync: {exc}\n")
        return 1

    # Resolve STATE.md and tickets dir from a single probe of the spec tree
    # (ARG1-075) so v1.0 and flat-scaffolded repos both work; explicit flags win.
    state_default, tickets_default = default_spec_paths(repo_root)
    state_file = _resolve(repo_root, args.state_file or state_default)
    tickets_dir = _resolve(repo_root, args.tickets_dir or tickets_default)

    try:
        return run_sync(
            repo_root=repo_root,
            state_file=state_file,
            tickets_dir=tickets_dir,
            main_ref=args.main_ref,
            dry_run=args.dry_run,
            no_issues=args.no_issues,
        )
    except ReconcileError as exc:
        sys.stderr.write(f"sync: {exc}\n")
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
