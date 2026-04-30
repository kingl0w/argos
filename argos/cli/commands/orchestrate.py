"""``argos orchestrate`` — read STATE.md ``## Queue`` and emit the next batch (ARG1-011).

Usage::

    argos orchestrate --dry-run [--batch-size N] [--state-file PATH]

The ``--dry-run`` mode is the only mode wired in this ticket — it parses
the queue section of STATE.md and prints the next ticket ids that would be
dispatched, one per line. No worktrees are created, no sessions are
spawned. Real dispatch is ARG1-022.

Error contracts (substrings consumed by ARG1-011 ACs):

- ``queue empty`` on stdout — ``## Queue`` section parsed cleanly with zero
  ticket-shaped bullets. Exit 0.
- ``STATE.md not found`` on stderr — STATE.md path does not exist. Exit 1.
"""

from __future__ import annotations

import argparse
import sys

from argos.cli.queue import (
    QueueSectionMissingError,
    StateFileNotFoundError,
    parse_queue_file,
)

_DEFAULT_STATE_FILE = "argos/specs/v1.0/STATE.md"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argos orchestrate",
        description=(
            "Read STATE.md ## Queue and emit the next batch of ticket ids "
            "the orchestrator agent would dispatch."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="parse the queue and print ids without dispatching (the only mode wired in v1.0)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="cap the number of ticket ids printed (defaults to all queued)",
    )
    parser.add_argument(
        "--state-file",
        default=_DEFAULT_STATE_FILE,
        help="path to STATE.md (default: %(default)s)",
    )
    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    if not args.dry_run:
        sys.stderr.write(
            "orchestrate: only --dry-run is implemented in v1.0 (real dispatch is ARG1-022)\n"
        )
        return 2

    if args.batch_size is not None and args.batch_size < 1:
        sys.stderr.write("orchestrate: --batch-size must be >= 1\n")
        return 2

    try:
        ticket_ids = parse_queue_file(args.state_file)
    except StateFileNotFoundError as exc:
        sys.stderr.write(f"orchestrate: {exc}\n")
        return 1
    except QueueSectionMissingError as exc:
        sys.stderr.write(f"orchestrate: {exc}\n")
        return 1

    if not ticket_ids:
        sys.stdout.write("queue empty\n")
        return 0

    if args.batch_size is not None:
        ticket_ids = ticket_ids[: args.batch_size]

    for tid in ticket_ids:
        sys.stdout.write(f"{tid}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
