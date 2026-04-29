"""``argos frontmatter-parse <path>`` — thin shim over :mod:`argos.cli.frontmatter_parser`.

Mirrors the shape of :mod:`argos.cli.commands.state_parse` so the dispatch
surface in :mod:`argos.cli.__main__` stays uniform across internal
subcommands.
"""

from __future__ import annotations

import sys

from argos.cli.frontmatter_parser import main as _parser_main


def main(argv: list[str]) -> int:
    return _parser_main(argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
