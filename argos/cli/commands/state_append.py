"""``argos state-append`` — append a verifier-authored block to STATE.md.

Usage::

    argos state-append --section "Done this cycle" --ticket ARG1-099 \\
        --author verifier --session sess-test --body-file /tmp/body.md \\
        [--state-file argos/specs/v1.0/STATE.md] [--dry-run]

On success: silent (or, with ``--dry-run``, the composed block on stdout). On
failure: stderr message and non-zero exit. The substring ``section not
found`` is the AC#5 contract for the missing-section error path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from argos.cli.state_append import SectionNotFoundError, append_block

_DEFAULT_STATE_FILE = "argos/specs/v1.0/STATE.md"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argos state-append",
        description="Append a verifier-authored block to STATE.md.",
    )
    parser.add_argument("--section", required=True, help="STATE.md section heading (without leading '## ')")
    parser.add_argument("--ticket", required=True, help="ticket id (e.g. ARG1-099)")
    parser.add_argument("--author", required=True, help="agent role (verifier|planner|coder|watchdog|orchestrator)")
    parser.add_argument("--session", required=True, help="opaque session identifier")
    parser.add_argument("--body-file", required=True, help="path to a markdown file containing the block body, or '-' for stdin")
    parser.add_argument("--state-file", default=_DEFAULT_STATE_FILE, help="path to STATE.md (default: %(default)s)")
    parser.add_argument("--dry-run", action="store_true", help="print the block to stdout without modifying any file")
    return parser


def _read_body(body_file: str) -> str:
    if body_file == "-":
        return sys.stdin.read()
    return Path(body_file).read_text(encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    try:
        body = _read_body(args.body_file)
    except FileNotFoundError:
        sys.stderr.write(f"state-append: body file not found: {args.body_file}\n")
        return 1
    except OSError as exc:
        sys.stderr.write(f"state-append: cannot read body file {args.body_file}: {exc}\n")
        return 1

    try:
        block = append_block(
            args.state_file,
            section=args.section,
            ticket=args.ticket,
            author=args.author,
            session=args.session,
            body=body,
            dry_run=args.dry_run,
        )
    except SectionNotFoundError as exc:
        sys.stderr.write(f"state-append: section not found: {str(exc)!r}\n")
        return 1
    except FileNotFoundError as exc:
        sys.stderr.write(f"state-append: state file not found: {exc}\n")
        return 1
    except OSError as exc:
        sys.stderr.write(f"state-append: {exc}\n")
        return 1

    if args.dry_run:
        sys.stdout.write(block)
        if not block.endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
