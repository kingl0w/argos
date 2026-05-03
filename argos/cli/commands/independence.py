"""``argos independence`` — file-overlap independence detector (ARG1-021).

Usage::

    argos independence ARG1-099 ARG1-100 [ARG1-101 ...] [--json] [--ticket-dir DIR]

Loads each named ticket, parses its frontmatter ``depends_on:`` and its
``## Plan`` section's ``files_touched:`` field, and reports whether the
batch is independent for parallel dispatch per the criterion pinned in
``argos/cli/orchestrator/independence.py`` (which itself implements
ARCHITECTURE.md §Independence detection verbatim).

Output contracts (consumed by ARG1-021 ACs and ARG1-022 dispatch):

- Default text mode, exit ``0`` on parse success:

  - For every pair, one line of the shape ``independent: A B`` or
    ``dependent: A B (<reason>)``. Reason is either ``depends_on`` or
    ``shared file: <path>[, <path>...]`` so AC text can grep for both.
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
    DEFAULT_TICKET_DIR,
    IndependenceError,
    MissingFilesTouchedError,
    PairResult,
    Ticket,
    is_independent,
    load_ticket,
    partition,
)


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
        default=DEFAULT_TICKET_DIR,
        help="directory holding ticket files (default: %(default)s)",
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


def _pair_results(tickets: list[Ticket]) -> list[PairResult]:
    out: list[PairResult] = []
    for i in range(len(tickets)):
        for j in range(i + 1, len(tickets)):
            out.append(is_independent(tickets[i], tickets[j]))
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

    tickets, rc = _load_all(args.tickets, args.ticket_dir)
    if rc != 0:
        return rc

    pairs = _pair_results(tickets)
    groups = partition(tickets)

    if args.emit_json:
        _emit_json(pairs, groups, sys.stdout)
    else:
        _emit_text(pairs, groups, sys.stdout)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
