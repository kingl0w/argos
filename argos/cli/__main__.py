"""Unified CLI dispatch for ``argos`` / ``python3 -m argos.cli``.

Top-level flags ``--version`` and ``--help`` are handled here. All other input
is routed by subcommand name. Subcommands fall into two groups:

- **Implemented internal subcommands** delegate to existing reference modules:
  ``state-parse`` → :mod:`argos.cli.commands.state_parse`,
  ``state-append`` → :mod:`argos.cli.commands.state_append`,
  ``verifier-parse`` → :mod:`argos.cli.verifier_parser`,
  ``verifier-writeback`` → :mod:`argos.cli.verifier_writeback`,
  ``escalation-validate`` → :mod:`argos.cli.escalation_validator`,
  ``frontmatter-parse`` → :mod:`argos.cli.commands.frontmatter_parse`,
  ``lint-imports`` → :mod:`argos.cli.lint_imports`.
- **Public-surface stubs** for ARG1-002 / ARG1-003 / ARG1-004 / ARG1-005:
  ``init`` / ``sync`` / ``status`` / ``attend`` print a "not yet implemented"
  message and exit non-zero. They exist so ``argos --help`` lists them.

Error contracts:
- No args → ``usage:`` line on stderr, exit 2.
- Unknown subcommand → ``argos: unknown subcommand: <name>`` on stderr, exit 2.
"""

from __future__ import annotations

import sys

from argos.cli import __version__

PROG = "argos"

# Public CLI surface for v1.0 (PRD §Distribution). Order is the order shown
# in --help.
PUBLIC_SUBCOMMANDS = (
    "init",
    "sync",
    "status",
    "attend",
    "escalate",
    "config",
    "orchestrate",
    "independence",
)

# Internal subcommands implemented in earlier tickets; routed by the
# dispatcher but kept out of the prominent --help summary.
INTERNAL_SUBCOMMANDS = (
    "state-parse",
    "state-append",
    "verifier-parse",
    "verifier-writeback",
    "escalation-validate",
    "frontmatter-parse",
    "run-session",
    "worktree-finalize",
    "lint-imports",
)

# Mapping of ARG1-0NN follow-up tickets that implement each public stub.
_STUB_TICKETS = {
    "init": "ARG1-002",
    "sync": "ARG1-004",
    "status": "ARG1-003",
    "attend": "ARG1-005",
}


def _print_usage(stream) -> None:
    stream.write(
        "usage: argos [--version] [--help] <subcommand> [args...]\n"
        "\n"
        "Public subcommands:\n"
        "  init      scaffold argos/specs/, install hooks (ARG1-002)\n"
        "  sync      reconcile tickets, STATE.md, and git (ARG1-004)\n"
        "  status    exit 0 iff specs are internally consistent (ARG1-003)\n"
        "  attend    drain the escalation queue (ARG1-005)\n"
        "  escalate  write an escalation file (and optionally POST a webhook)\n"
        "  config    get/validate config keys (project + local TOML)\n"
        "  orchestrate  read STATE.md ## Queue and emit the next dispatch batch (ARG1-011)\n"
        "  independence decide whether named tickets are independent for parallel dispatch (ARG1-021)\n"
        "\n"
        "Internal subcommands:\n"
        "  state-parse           parse STATE.md append-mostly blocks\n"
        "  state-append          append a block to a STATE.md section\n"
        "  verifier-parse        parse a verifier-output structured block\n"
        "  verifier-writeback    format a verifier block and append to STATE.md\n"
        "  escalation-validate   validate an escalation file against the schema\n"
        "  frontmatter-parse     parse YAML-subset frontmatter (ADR-002) to JSON\n"
        "  run-session           spawn a per-ticket session in a worktree (orchestrator)\n"
        "  worktree-finalize     merge a passed worktree's branch back to base (or preserve on fail)\n"
        "  lint-imports          verify .py imports against the ADR-001 stdlib allowlist\n"
        "\n"
        "Run 'argos --version' to print the version.\n"
    )


def _print_version(stream) -> None:
    stream.write(f"{PROG} {__version__}\n")


def _stub(name: str) -> int:
    ticket = _STUB_TICKETS[name]
    sys.stderr.write(
        f"argos {name}: not yet implemented (see {ticket})\n"
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    """Dispatch ``argv``. Returns the process exit code."""
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        _print_usage(sys.stderr)
        return 2

    head = argv[0]

    if head in ("-h", "--help"):
        _print_usage(sys.stdout)
        return 0
    if head in ("-V", "--version"):
        _print_version(sys.stdout)
        return 0

    rest = argv[1:]

    if head == "config":
        from argos.cli.commands.config import main as config_main
        return config_main(rest)

    if head == "escalate":
        from argos.cli.commands.escalate import main as escalate_main
        return escalate_main(rest)

    if head == "orchestrate":
        from argos.cli.commands.orchestrate import main as orchestrate_main
        return orchestrate_main(rest)

    if head == "independence":
        from argos.cli.commands.independence import main as independence_main
        return independence_main(rest)

    if head in PUBLIC_SUBCOMMANDS:
        return _stub(head)

    if head == "state-parse":
        from argos.cli.commands.state_parse import main as state_parse_main
        return state_parse_main(rest)

    if head == "state-append":
        from argos.cli.commands.state_append import main as state_append_main
        return state_append_main(rest)

    if head == "verifier-parse":
        from argos.cli.verifier_parser import main as verifier_parse_main
        # verifier_parser.main expects argv starting with prog name; pass a
        # synthetic argv0 to preserve its existing contract.
        return verifier_parse_main(["argos", *rest])

    if head == "verifier-writeback":
        from argos.cli.verifier_writeback import main as verifier_writeback_main
        return verifier_writeback_main(rest)

    if head == "escalation-validate":
        from argos.cli.escalation_validator import main as escalation_main
        return escalation_main(rest)

    if head == "frontmatter-parse":
        from argos.cli.commands.frontmatter_parse import main as frontmatter_parse_main
        return frontmatter_parse_main(rest)

    if head == "run-session":
        from argos.cli.commands.run_session import main as run_session_main
        return run_session_main(rest)

    if head == "worktree-finalize":
        from argos.cli.commands.worktree_finalize import main as worktree_finalize_main
        return worktree_finalize_main(rest)

    if head == "lint-imports":
        from argos.cli.lint_imports import main as lint_imports_main
        return lint_imports_main(rest)

    sys.stderr.write(f"argos: unknown subcommand: {head}\n")
    return 2


def main_entry() -> int:
    """Console-script entry point declared in ``pyproject.toml``.

    Wraps :func:`main` so ``pip install``ed users get the same behavior as
    ``python3 -m argos.cli``.
    """
    return main(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
