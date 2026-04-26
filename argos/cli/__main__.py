"""Minimal CLI dispatch for ``python3 -m argos.cli``.

Scaffolding stand-in until ARG1-001's full CLI lands. Knows exactly one
subcommand: ``state-parse``. All other input prints a short usage line and
exits non-zero.
"""

from __future__ import annotations

import sys


def _usage() -> None:
    sys.stderr.write("usage: python3 -m argos.cli state-parse <path>\n")


def main(argv: list[str]) -> int:
    if not argv:
        _usage()
        return 2
    sub, rest = argv[0], argv[1:]
    if sub == "state-parse":
        from argos.cli.commands.state_parse import main as state_parse_main
        return state_parse_main(rest)
    _usage()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
