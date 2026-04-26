"""``argos config <get|validate>`` — operator-facing config subcommand.

- ``argos config get <dotted.key>`` prints the value to stdout (no
  surrounding quotes; bools as ``true`` / ``false`` to mirror the TOML
  surface) and exits 0. On a miss, exits 1 with
  ``key not found: <dotted.key>`` on stderr.
- ``argos config validate`` exits 0 on a clean config; non-zero with one
  error per stderr line on type mismatches.

The loader is invoked with no explicit paths so the CWD-walk discovery
finds the repo root. Tests use ``tempfile.TemporaryDirectory()`` and
set ``cwd=`` so the discovery picks up fixture files.
"""

from __future__ import annotations

import sys

from argos.cli.config import (
    Config,
    ConfigError,
    ConfigParseError,
    KeyNotFoundError,
    load,
)


def _format_value(value: object) -> str:
    """Render a config value for stdout.

    Bools render as the TOML literals ``true`` / ``false`` so round-trip
    inspection matches what is in the file. Strings render unquoted.
    Ints render as their decimal form.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _print_usage(stream) -> None:
    stream.write(
        "usage: argos config <get|validate> [args...]\n"
        "\n"
        "Subcommands:\n"
        "  get <dotted.key>   print the value of <dotted.key>\n"
        "  validate           type-check the loaded config\n"
    )


def main(argv: list[str]) -> int:
    if not argv:
        _print_usage(sys.stderr)
        return 2

    sub = argv[0]
    rest = argv[1:]

    if sub in ("-h", "--help"):
        _print_usage(sys.stdout)
        return 0

    if sub == "get":
        if len(rest) != 1:
            sys.stderr.write("usage: argos config get <dotted.key>\n")
            return 2
        key = rest[0]
        try:
            cfg = load()
        except ConfigParseError as exc:
            sys.stderr.write(f"config: {exc}\n")
            return 1
        except ConfigError as exc:
            sys.stderr.write(f"config: {exc}\n")
            return 1
        try:
            value = cfg.get(key)
        except KeyNotFoundError as exc:
            sys.stderr.write(f"key not found: {exc.key}\n")
            return 1
        sys.stdout.write(f"{_format_value(value)}\n")
        return 0

    if sub == "validate":
        if rest:
            sys.stderr.write("usage: argos config validate\n")
            return 2
        try:
            cfg = load()
        except ConfigParseError as exc:
            sys.stderr.write(f"config: {exc}\n")
            return 1
        except ConfigError as exc:
            sys.stderr.write(f"config: {exc}\n")
            return 1
        errors = cfg.validate()
        if errors:
            for err in errors:
                sys.stderr.write(f"{err}\n")
            return 1
        return 0

    sys.stderr.write(f"argos config: unknown subcommand: {sub}\n")
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
