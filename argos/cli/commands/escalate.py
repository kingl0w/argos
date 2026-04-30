"""``argos escalate`` — write an escalation file and (optionally) POST a webhook.

Usage::

    argos escalate --ticket ARG1-099 --severity blocking \\
        --raised-by orchestrator --body 'Question text' \\
        [--body-file -|<path>] [--session-id <id>] \\
        [--dest-dir <dir>] [--no-webhook]

Exit codes:
- ``0`` on success (file written; webhook attempted iff configured).
- ``1`` on writer-level failures (filesystem, body validation).
- ``2`` on argument errors (severity / raised-by / missing flags). The AC#6
  contract is that an invalid ``--severity`` produces stderr containing the
  literal ``severity must be blocking or advisory``.

Webhook URL is read from ``escalation.webhook_url`` via
:mod:`argos.cli.config`. An unset, empty, or unloadable URL is treated as
"no webhook"; a logged note goes to stderr only on a *load* error
(missing-key is silent — that is the documented "no webhook" path).

Webhook delivery is fire-and-forget per ARCHITECTURE.md §Components/
Escalation Channel: HTTP errors and connection failures are logged to
stderr but the command still exits 0.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from argos.cli.config import (
    Config,
    ConfigError,
    KeyNotFoundError,
    load as load_config,
)
from argos.cli.escalation import (
    DEFAULT_ESCALATION_DIR,
    EscalationError,
    InvalidRaisedByError,
    InvalidSeverityError,
    post_webhook,
    short_summary,
    write_escalation,
)
from argos.cli.escalation_validator import ALLOWED_RAISED_BY, ALLOWED_SEVERITY


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argos escalate",
        description=(
            "Write an escalation file under argos/specs/escalations/ and, "
            "if escalation.webhook_url is configured, POST a JSON summary "
            "to that URL."
        ),
        # AC#6 requires our own severity error to win over argparse's
        # required-argument error, so flags are formally optional and the
        # validation order is enforced in main().
        add_help=True,
    )
    parser.add_argument("--ticket", default=None, help="ticket id (e.g. ARG1-099)")
    parser.add_argument(
        "--severity",
        default=None,
        help="blocking | advisory",
    )
    parser.add_argument(
        "--raised-by",
        dest="raised_by",
        default="orchestrator",
        help=(
            "one of: orchestrator | planner | coder | watchdog | verifier "
            "(default: orchestrator)"
        ),
    )
    parser.add_argument(
        "--body",
        default=None,
        help="inline body text (use --body-file for files / stdin)",
    )
    parser.add_argument(
        "--body-file",
        dest="body_file",
        default=None,
        help="path to a body file, or '-' for stdin",
    )
    parser.add_argument(
        "--session-id",
        dest="session_id",
        default=None,
        help="opaque session identifier; auto-generated if omitted",
    )
    parser.add_argument(
        "--dest-dir",
        dest="dest_dir",
        default=None,
        help=(
            "directory to write the escalation file into "
            "(default: <repo-root>/argos/specs/escalations/)"
        ),
    )
    parser.add_argument(
        "--no-webhook",
        action="store_true",
        help="skip the webhook POST regardless of config",
    )
    return parser


def _find_repo_root(start: Path) -> Optional[Path]:
    """Walk up from ``start`` looking for an Argos repo root marker.

    Markers (any one): ``argos/specs/``, ``argos/config.toml``,
    ``argos/config.toml.template``. Returns the first match or ``None``.
    """
    cur = start.resolve()
    while True:
        if (cur / "argos" / "specs").is_dir():
            return cur
        if (cur / "argos" / "config.toml").is_file():
            return cur
        if (cur / "argos" / "config.toml.template").is_file():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def _resolve_dest_dir(explicit: Optional[str]) -> Path:
    if explicit:
        return Path(explicit)
    root = _find_repo_root(Path.cwd())
    if root is None:
        return Path.cwd() / DEFAULT_ESCALATION_DIR
    return root / DEFAULT_ESCALATION_DIR


def _read_body(args: argparse.Namespace) -> Optional[str]:
    if args.body_file is not None:
        if args.body_file == "-":
            return sys.stdin.read()
        try:
            return Path(args.body_file).read_text(encoding="utf-8")
        except FileNotFoundError:
            sys.stderr.write(f"escalate: body file not found: {args.body_file}\n")
            return None
        except OSError as exc:
            sys.stderr.write(
                f"escalate: cannot read body file {args.body_file}: {exc}\n"
            )
            return None
    if args.body is not None:
        return args.body
    return None


def _load_webhook_url() -> Optional[str]:
    """Return the configured webhook URL, or ``None`` on miss/error.

    A missing-key or unset/empty value returns ``None`` silently — that is
    the documented "no webhook" path. A genuine config-load failure
    (parse error, unreadable file) writes one stderr line and also
    returns ``None`` so the writer can continue.
    """
    try:
        cfg: Config = load_config(warn_stream=sys.stderr)
    except (ConfigError, OSError) as exc:
        sys.stderr.write(f"escalate: could not load config: {exc}\n")
        return None
    try:
        value = cfg.get("escalation.webhook_url")
    except KeyNotFoundError:
        return None
    if not isinstance(value, str):
        sys.stderr.write(
            "escalate: escalation.webhook_url is not a string; ignoring\n"
        )
        return None
    if value == "":
        return None
    return value


def main(argv: list[str]) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    # Severity validation MUST come first per AC#6 (the canonical error
    # message wins over a "required argument missing" one).
    if args.severity is None:
        sys.stderr.write("severity must be blocking or advisory\n")
        return 2
    if args.severity not in ALLOWED_SEVERITY:
        sys.stderr.write("severity must be blocking or advisory\n")
        return 2

    if args.raised_by not in ALLOWED_RAISED_BY:
        allowed = ", ".join(sorted(ALLOWED_RAISED_BY))
        sys.stderr.write(
            f"raised-by must be one of: {allowed}\n"
        )
        return 2

    if not args.ticket:
        sys.stderr.write("escalate: --ticket is required\n")
        return 2

    body = _read_body(args)
    if body is None:
        if args.body is None and args.body_file is None:
            sys.stderr.write("escalate: --body or --body-file is required\n")
            return 2
        # _read_body already wrote a stderr line for the file-not-found /
        # OSError paths.
        return 1

    dest_dir = _resolve_dest_dir(args.dest_dir)

    try:
        path = write_escalation(
            ticket_id=args.ticket,
            severity=args.severity,
            raised_by=args.raised_by,
            body=body,
            dest_dir=dest_dir,
            session_id=args.session_id,
        )
    except InvalidSeverityError:
        sys.stderr.write("severity must be blocking or advisory\n")
        return 2
    except InvalidRaisedByError as exc:
        sys.stderr.write(f"escalate: {exc}\n")
        return 2
    except EscalationError as exc:
        sys.stderr.write(f"escalate: {exc}\n")
        return 1
    except OSError as exc:
        sys.stderr.write(f"escalate: cannot write escalation file: {exc}\n")
        return 1

    if not args.no_webhook:
        webhook_url = _load_webhook_url()
        if webhook_url:
            post_webhook(
                webhook_url,
                ticket_id=args.ticket,
                severity=args.severity,
                summary=short_summary(body),
                file_path=str(path),
            )

    sys.stdout.write(f"{path}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
