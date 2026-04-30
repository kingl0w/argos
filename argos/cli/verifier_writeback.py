"""Format a verifier structured-output block into a STATE.md body.

Per ARG1-031: the verifier emits a structured block matching
``argos/specs/v1.0/schemas/verifier-output.md``; this module translates that
parsed block into the body string consumed by ``argos state-append`` and
appends it via :mod:`argos.cli.state_append`.

The mapping from the structured ``decision`` to the STATE.md phase label is::

    pass               -> verified
    pass-with-minors   -> verified-with-minors
    fail               -> verification-failed

A ``Decision:`` line in the body always carries the literal decision value
(``pass`` / ``pass-with-minors`` / ``fail``) so downstream consumers can grep
either the phase label (heading) or the literal decision value.

Stdlib only — re, datetime, pathlib, json, argparse, sys.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from argos.cli.state_append import (
    InvalidSuffixError,
    SectionNotFoundError,
    append_block,
)
from argos.cli.verifier_parser import (
    SchemaError,
    extract_block,
    parse_block,
    validate,
)

__all__ = [
    "DECISION_PHASE",
    "DEFAULT_SECTION",
    "format_body",
    "main",
]

DECISION_PHASE = {
    "pass": "verified",
    "pass-with-minors": "verified-with-minors",
    "fail": "verification-failed",
}

DEFAULT_SECTION = "Done this cycle"

_VALID_DECISIONS = set(DECISION_PHASE.keys())


def _format_timestamp(dt: datetime | None) -> str:
    if dt is None:
        dt = datetime.now(timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _count_findings(findings: list) -> tuple[int, int, int]:
    c = m = n = 0
    for f in findings:
        sev = f.get("severity")
        if sev == "critical":
            c += 1
        elif sev == "major":
            m += 1
        elif sev == "minor":
            n += 1
    return c, m, n


def _format_finding_ref(finding: dict) -> str:
    file_ref = finding.get("file")
    desc = finding.get("description", "")
    if file_ref:
        return f"`{file_ref}` — {desc}"
    return desc


def format_body(
    *,
    parsed: dict,
    ticket: str,
    session: str,
    worktree: str | None = None,
    test_stdout: str | None = None,
    timestamp: datetime | None = None,
) -> str:
    """Build a STATE.md block body from a parsed verifier-output dict.

    The body always contains:
      - a leading bullet ``[ts] TICKET — <phase>`` where phase is one of
        ``verified`` / ``verified-with-minors`` / ``verification-failed``
      - ``Findings: N critical, N major, N minor`` line
      - a ``Decision: <literal>`` line carrying ``pass`` / ``pass-with-minors``
        / ``fail``

    For ``decision: pass-with-minors`` each minor finding is listed verbatim
    with its ``file:line`` reference (omitted for whole-suite findings).

    For ``decision: fail`` ``test_stdout`` is rendered verbatim under a
    ``Test stdout:`` fenced sub-block so AC#3's ``grep -Fc`` of a known
    fragment matches.
    """
    decision = parsed["decision"]
    if decision not in _VALID_DECISIONS:
        raise ValueError(f"unknown decision: {decision!r}")

    findings = parsed.get("findings", [])
    crit, maj, mnr = _count_findings(findings)
    phase = DECISION_PHASE[decision]
    ts = _format_timestamp(timestamp)

    head_extras = [f"session {session}"]
    if worktree:
        head_extras.append(f"worktree `{worktree}`")
    head_paren = ", ".join(head_extras)

    lines: list[str] = []
    lines.append(f"- **[{ts}] {ticket} — {phase}** ({head_paren})")
    lines.append(
        f"  - Findings: {crit} critical, {maj} major, {mnr} minor"
    )

    if decision == "pass-with-minors":
        lines.append("  - Minor findings:")
        for f in findings:
            if f.get("severity") != "minor":
                continue
            lines.append(f"    - {_format_finding_ref(f)}")

    if decision == "fail":
        if findings:
            lines.append("  - Critical/major findings:")
            for f in findings:
                if f.get("severity") in ("critical", "major"):
                    lines.append(f"    - {_format_finding_ref(f)}")
        if test_stdout:
            lines.append("  - Test stdout:")
            lines.append("")
            lines.append("    ```")
            for raw in test_stdout.rstrip("\n").splitlines():
                lines.append(f"    {raw}")
            lines.append("    ```")

    lines.append(f"  - Decision: {decision}")
    return "\n".join(lines) + "\n"


def _read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argos verifier-writeback",
        description=(
            "Translate a verifier structured-output block into a STATE.md "
            "block body and append via argos state-append."
        ),
    )
    parser.add_argument(
        "--input",
        required=True,
        help="path to a file containing a <!-- argos:verifier-output --> block, or '-' for stdin",
    )
    parser.add_argument("--ticket", required=True, help="ticket id (e.g. ARG1-099)")
    parser.add_argument("--session", required=True, help="opaque session identifier")
    parser.add_argument(
        "--worktree",
        default=None,
        help="optional worktree path/label rendered into the body header",
    )
    parser.add_argument(
        "--stdout-file",
        default=None,
        help="optional path to a file containing test stdout to embed verbatim on decision=fail",
    )
    parser.add_argument(
        "--state-file",
        default="argos/specs/v1.0/STATE.md",
        help="path to STATE.md (default: %(default)s)",
    )
    parser.add_argument(
        "--section",
        default=DEFAULT_SECTION,
        help="STATE.md section heading without leading '## ' (default: %(default)s)",
    )
    parser.add_argument(
        "--suffix",
        default="verify",
        help="state-append --suffix slug; must match ^[a-z0-9-]+$ (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the composed block to stdout without modifying STATE.md",
    )
    parser.add_argument(
        "--emit-body",
        action="store_true",
        help="print only the body (without the argos:entry wrapper) and exit; does not call state-append",
    )
    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    try:
        text = _read_text(args.input)
    except FileNotFoundError:
        sys.stderr.write(f"verifier-writeback: input not found: {args.input}\n")
        return 1
    except OSError as exc:
        sys.stderr.write(f"verifier-writeback: cannot read input: {exc}\n")
        return 1

    try:
        block = extract_block(text)
        parsed = parse_block(block)
        validate(parsed)
    except SchemaError as exc:
        sys.stderr.write(f"verifier-writeback: schema error: {exc}\n")
        return 2

    test_stdout: str | None = None
    if args.stdout_file:
        try:
            test_stdout = Path(args.stdout_file).read_text(encoding="utf-8")
        except FileNotFoundError:
            sys.stderr.write(
                f"verifier-writeback: stdout file not found: {args.stdout_file}\n"
            )
            return 1
        except OSError as exc:
            sys.stderr.write(
                f"verifier-writeback: cannot read stdout file: {exc}\n"
            )
            return 1

    body = format_body(
        parsed=parsed,
        ticket=args.ticket,
        session=args.session,
        worktree=args.worktree,
        test_stdout=test_stdout,
    )

    if args.emit_body:
        sys.stdout.write(body)
        if not body.endswith("\n"):
            sys.stdout.write("\n")
        return 0

    try:
        composed = append_block(
            args.state_file,
            section=args.section,
            ticket=args.ticket,
            author="verifier",
            session=args.session,
            body=body,
            dry_run=args.dry_run,
            suffix=args.suffix,
        )
    except InvalidSuffixError as exc:
        sys.stderr.write(f"verifier-writeback: {exc}\n")
        return 2
    except SectionNotFoundError as exc:
        sys.stderr.write(f"verifier-writeback: section not found: {str(exc)!r}\n")
        return 1
    except FileNotFoundError as exc:
        sys.stderr.write(f"verifier-writeback: state file not found: {exc}\n")
        return 1
    except OSError as exc:
        sys.stderr.write(f"verifier-writeback: {exc}\n")
        return 1

    if args.dry_run:
        sys.stdout.write(composed)
        if not composed.endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
