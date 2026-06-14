"""``argos status`` — the v1.0 integrity oracle (ARG1-003).

Exits 0 iff the spec tree is internally consistent: STATE.md parses
against the v1.0 block schema and every block's ticket exists; the two
config files parse and type-validate; ``argos/specs/escalations/`` holds
no malformed file and no undrained *blocking* escalation; and every
``## Done this cycle`` ticket appears in the recent git log on the current
branch. Otherwise it exits non-zero with a one-screen diagnosis on
stderr.

The check logic lives in :mod:`argos.cli.integrity`; this module only
resolves the repo root, picks the output format, and maps the report to a
process exit code. Diagnose only — no auto-fix, no network. Standard
library only (ADR-001); runs under Python >= 3.9.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from argos.cli import integrity

__all__ = ["main"]


def _resolve_repo_root(arg: str | None) -> Path:
    """Repo root: explicit ``--repo-root`` → git toplevel → CWD."""
    if arg is not None:
        return Path(arg).resolve()
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return Path(proc.stdout.strip()).resolve()
    except (FileNotFoundError, OSError):
        pass
    return Path.cwd().resolve()


def _emit_text(report: integrity.IntegrityReport, *, out, err) -> None:
    if report.ok:
        out.write("argos status: ok — STATE.md, config, escalations, and "
                  "git are mutually consistent.\n")
        return
    err.write("argos status: integrity check failed\n")
    for check in report.checks:
        if check.passed:
            continue
        err.write(f"  [{check.name}] FAIL\n")
        for msg in check.messages:
            err.write(f"    - {msg}\n")
    passed = [c.name for c in report.checks if c.passed]
    if passed:
        err.write(f"  ok: {', '.join(passed)}\n")


def _emit_json(report: integrity.IntegrityReport, *, out) -> None:
    out.write(json.dumps(report.to_json_obj(), indent=2, sort_keys=False))
    out.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="argos status",
        description=(
            "Integrity oracle: exit 0 iff STATE.md, tickets, config, "
            "escalations, and git are mutually consistent."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a JSON object on stdout instead of human text",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="repo root to inspect (default: git toplevel, else CWD)",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    repo_root = _resolve_repo_root(args.repo_root)
    report = integrity.run_checks(repo_root)

    if args.json:
        _emit_json(report, out=sys.stdout)
    else:
        _emit_text(report, out=sys.stdout, err=sys.stderr)

    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
