"""``argos state-parse <path>`` — debug subcommand exposing the reference parser.

On success: emit a JSON list of blocks (each with ``id``, ``ticket``, ``author``,
``session``, ``body``, ``start_line``, ``end_line``) to stdout, exit 0.

On any :class:`argos.cli.state_parser.StateBlockError`: write the exception's
message to stderr, exit 1.
"""

from __future__ import annotations

import json
import sys

from argos.cli.state_parser import StateBlockError, parse_file


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        sys.stderr.write(
            "usage: argos state-parse <path-to-markdown-file>\n"
        )
        return 2

    path = argv[0]
    try:
        blocks = parse_file(path)
    except FileNotFoundError as exc:
        sys.stderr.write(f"state-parse: file not found: {exc.filename}\n")
        return 1
    except StateBlockError as exc:
        sys.stderr.write(f"state-parse: {exc}\n")
        return 1

    payload = [b.to_dict() for b in blocks]
    json.dump(payload, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
