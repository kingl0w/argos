"""``argos independence`` — merge-aware independence detector (ARG1-066).

Usage::

    argos independence ARG1-099 ARG1-100 [ARG1-101 ...] [--json] [--ticket-dir DIR]

Loads each named ticket and reports whether the batch is independent for
parallel dispatch per the criterion in
``argos/cli/orchestrator/independence.py`` (ARG1-066): ``depends_on:`` is the
cheap first-pass exclusion, then a dry-run ``git merge`` of the two
``argos/<id>`` branches in both directions decides the rest. When a pair's
branches are not present (or the command is run outside a git repo) the pair
degrades to ARG1-021's strict ``files_touched:`` disjointness. The CLI surface
(positional ticket ids, ``--json``, exit codes) is unchanged from ARG1-021.

Output contracts (consumed by the ACs and ARG1-022 dispatch):

- Default text mode, exit ``0`` on parse success:

  - For every pair, one line of the shape ``independent: A B`` or
    ``dependent: A B (<reason>)``. Reason is one of ``depends_on``,
    ``merge conflict: <path>[, <path>...]`` (merge path), or
    ``shared file: <path>[, <path>...]`` (static fallback) — AC text can grep
    for each.
  - Plus one ``group N: T1 T2 ...`` line per group from the partition.

- ``--json`` mode, exit ``0`` on parse success: a JSON object on stdout
  with keys ``groups`` (list of lists of ticket ids) and ``pairs`` (list
  of ``{a, b, independent, reason, shared_files}`` objects).

- Exit ``2`` on parse failure (missing ``files_touched:``, missing
  ticket file, malformed ticket id). Stderr names the offending ticket
  id and contains ``missing files_touched`` for the missing-field case
  (per AC#4).

- Exit ``2`` on usage error (no ticket ids supplied, unknown flag).
"""

from __future__ import annotations

import argparse
import json
import sys

from argos.cli.orchestrator.independence import (
    IndependenceError,
    MergeStagingArea,
    MissingFilesTouchedError,
    PairResult,
    Ticket,
    find_repo_root,
    is_independent,
    load_ticket,
    partition,
)
from argos.cli.spec_paths import default_ticket_dir


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argos independence",
        description=(
            "Decide whether the named tickets are independent for parallel "
            "dispatch. Implements ARCHITECTURE.md §Independence detection."
        ),
    )
    parser.add_argument(
        "tickets",
        nargs="+",
        metavar="TICKET_ID",
        help="two or more ticket ids (e.g. ARG1-099)",
    )
    parser.add_argument(
        "--json",
        dest="emit_json",
        action="store_true",
        help="emit a JSON object on stdout instead of text lines",
    )
    parser.add_argument(
        "--ticket-dir",
        default=None,
        help=(
            "directory holding ticket files (default: auto-detected — "
            "argos/specs/v1.0/tickets if present, else argos/specs/tickets)"
        ),
    )
    return parser


def _load_all(
    ticket_ids: list[str], ticket_dir: str
) -> tuple[list[Ticket], int]:
    """Load every ticket; on the first failure, write to stderr and return nonzero."""
    loaded: list[Ticket] = []
    for tid in ticket_ids:
        try:
            loaded.append(load_ticket(tid, ticket_dir))
        except MissingFilesTouchedError as exc:
            sys.stderr.write(f"independence: {exc}\n")
            return loaded, 2
        except IndependenceError as exc:
            sys.stderr.write(f"independence: {exc}\n")
            return loaded, 2
    return loaded, 0


def _pair_results(
    tickets: list[Ticket], staging: MergeStagingArea | None = None
) -> list[PairResult]:
    out: list[PairResult] = []
    for i in range(len(tickets)):
        for j in range(i + 1, len(tickets)):
            out.append(is_independent(tickets[i], tickets[j], staging=staging))
    return out


def _emit_text(
    pairs: list[PairResult], groups: list[list[str]], stream
) -> None:
    for pr in pairs:
        if pr.independent:
            stream.write(f"independent: {pr.a} {pr.b}\n")
        else:
            stream.write(f"dependent: {pr.a} {pr.b} ({pr.reason})\n")
    for idx, grp in enumerate(groups, start=1):
        stream.write(f"group {idx}: {' '.join(grp)}\n")


def _emit_json(
    pairs: list[PairResult], groups: list[list[str]], stream
) -> None:
    payload = {
        "groups": groups,
        "pairs": [
            {
                "a": pr.a,
                "b": pr.b,
                "independent": pr.independent,
                "reason": pr.reason,
                "shared_files": list(pr.shared_files),
            }
            for pr in pairs
        ],
    }
    json.dump(payload, stream, indent=2, sort_keys=True)
    stream.write("\n")


def main(argv: list[str]) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    ticket_dir = args.ticket_dir or default_ticket_dir()
    tickets, rc = _load_all(args.tickets, ticket_dir)
    if rc != 0:
        return rc

    # Merge-aware path: when invoked inside a git repo, build one shared
    # staging worktree and reuse it across every pairwise check and the
    # partition (so a batch creates the worktree at most once — AC#3). The
    # staging area is lazy: if no pair has both `argos/<id>` branches present,
    # no worktree is ever created and every pair degrades to the strict
    # file-set criterion. Outside a repo, staging stays None → pure static.
    repo_root = find_repo_root()
    staging = MergeStagingArea(repo_root) if repo_root is not None else None
    try:
        pairs = _pair_results(tickets, staging)
        groups = partition(tickets, staging=staging)
    finally:
        if staging is not None:
            staging.close()

    if args.emit_json:
        _emit_json(pairs, groups, sys.stdout)
    else:
        _emit_text(pairs, groups, sys.stdout)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
