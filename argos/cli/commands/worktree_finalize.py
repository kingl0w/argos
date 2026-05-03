"""``argos worktree-finalize`` — merge-on-pass / preserve-on-fail (ARG1-023).

Usage::

    argos worktree-finalize --ticket ARG1-099 --result pass [--json]
    argos worktree-finalize --ticket ARG1-099 --result fail
    argos worktree-finalize --ticket ARG1-099 --result pass-with-minors \\
        [--base main] [--escalation-dir <dir>] [--json]

Behavior is dispatched by ``--result``:

- ``pass`` / ``pass-with-minors`` → attempt fast-forward merge of
  ``argos/<ticket>`` into ``--base`` (default ``main``); on
  non-fast-forwardable history, attempt a three-way merge; on conflict,
  abort and write a ``severity: blocking`` escalation file.
- ``fail`` → no-op; preserve worktree and branch for ARG1-013's
  auto-fix retry or operator inspection.

Exit codes:

- ``0``  success — merge completed (pass/pass-with-minors) OR fail
                   preserved cleanly.
- ``1``  conflict (escalation written) or other operational failure
         (dirty base, missing branch, git plumbing error).
- ``2``  argument errors.

``--json`` prints a single-line JSON object to stdout with at least the
four AC#6 keys (``merged``, ``merge_strategy``, ``conflicts``,
``worktree_preserved``) plus diagnostic context.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from argos.cli.escalation import EscalationError
from argos.cli.orchestrator.merge import (
    DEFAULT_BASE_BRANCH,
    DirtyWorkingTreeError,
    FinalizeError,
    InvalidResultError,
    MissingBranchError,
    VALID_RESULTS,
    finalize,
    find_main_repo_root,
)
from argos.cli.worktree import GitError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argos worktree-finalize",
        description=(
            "Merge a passed ticket's worktree branch into base, or preserve "
            "the worktree for retry on fail. On three-way merge conflict, "
            "abort and write a blocking escalation."
        ),
    )
    parser.add_argument(
        "--ticket",
        required=True,
        help="ticket id (e.g. ARG1-099)",
    )
    parser.add_argument(
        "--result",
        required=True,
        help=(
            "verifier decision: " + " | ".join(VALID_RESULTS)
        ),
    )
    parser.add_argument(
        "--base",
        default=DEFAULT_BASE_BRANCH,
        help=f"base branch to merge into (default: {DEFAULT_BASE_BRANCH})",
    )
    parser.add_argument(
        "--escalation-dir",
        dest="escalation_dir",
        default=None,
        help=(
            "directory to write escalation files into "
            "(default: <repo-root>/argos/specs/escalations)"
        ),
    )
    parser.add_argument(
        "--repo-root",
        dest="repo_root",
        default=None,
        help=(
            "main worktree path (default: resolved via "
            "`git worktree list --porcelain`)"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a single-line JSON object to stdout",
    )
    return parser


def _emit_human(result, stream) -> None:
    """Plain-text summary for non-``--json`` runs."""
    if result.result == "fail":
        stream.write(
            f"worktree-finalize: {result.ticket_id}: result=fail; "
            f"worktree and branch preserved\n"
        )
        return
    if result.conflicts:
        stream.write(
            f"worktree-finalize: {result.ticket_id}: merge conflict; "
            f"merge aborted; escalation written to "
            f"{result.escalation_path}\n"
        )
        return
    if result.merged:
        stream.write(
            f"worktree-finalize: {result.ticket_id}: merged "
            f"({result.merge_strategy}) into {result.base_branch}\n"
        )
        return
    # Defensive: no other code path produces a non-conflict, non-merged,
    # non-fail outcome. Surface as diagnostic rather than crashing.
    stream.write(
        f"worktree-finalize: {result.ticket_id}: unexpected outcome "
        f"(merged={result.merged}, conflicts={result.conflicts})\n"
    )


def main(argv: list[str]) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    if args.result not in VALID_RESULTS:
        sys.stderr.write(
            f"worktree-finalize: --result must be one of "
            f"{', '.join(VALID_RESULTS)} (got {args.result!r})\n"
        )
        return 2

    repo_root = (
        Path(args.repo_root).resolve() if args.repo_root else None
    )
    if repo_root is None:
        try:
            repo_root = find_main_repo_root()
        except GitError as exc:
            sys.stderr.write(f"worktree-finalize: {exc}\n")
            if exc.stderr:
                sys.stderr.write(
                    f"worktree-finalize: git: {exc.stderr}\n"
                )
            return 1

    escalation_dir = (
        Path(args.escalation_dir) if args.escalation_dir else None
    )

    try:
        result = finalize(
            ticket_id=args.ticket,
            result=args.result,
            repo_root=repo_root,
            base_branch=args.base,
            escalation_dir=escalation_dir,
        )
    except InvalidResultError as exc:
        sys.stderr.write(f"worktree-finalize: {exc}\n")
        return 2
    except MissingBranchError as exc:
        sys.stderr.write(f"worktree-finalize: {exc}\n")
        return 1
    except DirtyWorkingTreeError as exc:
        sys.stderr.write(f"worktree-finalize: {exc}\n")
        return 1
    except GitError as exc:
        sys.stderr.write(f"worktree-finalize: {exc}\n")
        if exc.stderr:
            sys.stderr.write(f"worktree-finalize: git: {exc.stderr}\n")
        return 1
    except EscalationError as exc:
        sys.stderr.write(
            f"worktree-finalize: could not write escalation: {exc}\n"
        )
        return 1
    except FinalizeError as exc:
        sys.stderr.write(f"worktree-finalize: {exc}\n")
        return 1

    if args.json:
        sys.stdout.write(json.dumps(result.to_json_payload()) + "\n")
    else:
        _emit_human(result, sys.stdout)

    if result.conflicts:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
