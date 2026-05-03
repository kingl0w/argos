"""``argos orchestrate`` — read STATE.md ``## Queue`` and dispatch.

ARG1-011 wired ``--dry-run`` as the only mode and rejected real
dispatch with the explicit message that real dispatch is ARG1-022's
scope. ARG1-022 (this ticket) flips that:

- ``--dry-run`` keeps the ARG1-011 contract for the queue-only case
  (no ticket files resolvable, e.g. the existing test fixtures), and
  upgrades to a markdown table when every queued ticket loads with a
  ``files_touched:`` Plan section (AC#6).
- Without ``--dry-run`` and with a non-empty queue, real dispatch runs:
  the queue is parsed, ``orchestrator.max_parallel`` is read from
  config (default 3 per the v1.0 schema), and
  :func:`argos.cli.orchestrator.dispatch.dispatch_batch` runs the
  per-ticket sessions. Exit code is 0 iff every dispatched session
  returned 0; non-zero otherwise.

Error contracts (substrings consumed by ACs):

- ``queue empty`` on stdout — ``## Queue`` section parsed cleanly
  with zero ticket-shaped bullets. Exit 0.
- ``STATE.md not found`` on stderr — STATE.md path does not exist.
  Exit 1.
- ``independence detection failed; falling back to serial`` on
  stdout (AC#4) — independence detector raised on real dispatch.
- ``orchestrate: --epic is required for real dispatch`` on stderr
  — non-dry-run invocation without ``--epic``. Exit 2.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

from argos.cli.orchestrator import dispatch as dispatch_module
from argos.cli.orchestrator import independence
from argos.cli.queue import (
    QueueSectionMissingError,
    StateFileNotFoundError,
    parse_queue_file,
)

_DEFAULT_STATE_FILE = "argos/specs/v1.0/STATE.md"
_DEFAULT_TICKET_DIR = independence.DEFAULT_TICKET_DIR


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argos orchestrate",
        description=(
            "Dispatch the next batch of queued tickets in parallel "
            "where independence allows; or print the would-be batch in "
            "--dry-run mode."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "parse the queue and emit either a markdown dispatch table "
            "(when every ticket loads with files_touched:) or a plain "
            "ticket-id list (fallback). No worktrees created, no sessions "
            "spawned."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="cap the number of ticket ids consumed (defaults to all queued)",
    )
    parser.add_argument(
        "--state-file",
        default=_DEFAULT_STATE_FILE,
        help="path to STATE.md (default: %(default)s)",
    )
    parser.add_argument(
        "--ticket-dir",
        default=_DEFAULT_TICKET_DIR,
        help=(
            "directory holding ticket files for independence detection "
            "(default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--epic",
        default=None,
        help=(
            "epic id stamped on dispatch log entries; required for real "
            "dispatch, ignored under --dry-run"
        ),
    )
    parser.add_argument(
        "--max-parallel",
        type=int,
        default=None,
        help=(
            "override orchestrator.max_parallel from config "
            "(default: read from config, falls back to 3)"
        ),
    )
    return parser


def _resolve_max_parallel(override: int | None) -> int:
    """Return the effective ``max_parallel`` value for this dispatch.

    Resolution: explicit ``--max-parallel`` flag → ``orchestrator.max_parallel``
    from the config loader → :data:`dispatch_module.DEFAULT_MAX_PARALLEL`.
    Errors from the config loader are swallowed so a missing config
    file does not block real dispatch (mirrors run-session's
    ``_load_configured_binary`` discipline).
    """
    if override is not None:
        return override
    try:
        from argos.cli.config import KeyNotFoundError, load
    except Exception:
        return dispatch_module.DEFAULT_MAX_PARALLEL
    try:
        cfg = load()
    except Exception:
        return dispatch_module.DEFAULT_MAX_PARALLEL
    try:
        value = cfg.get("orchestrator.max_parallel")
    except KeyNotFoundError:
        return dispatch_module.DEFAULT_MAX_PARALLEL
    except Exception:
        return dispatch_module.DEFAULT_MAX_PARALLEL
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return dispatch_module.DEFAULT_MAX_PARALLEL
    return value


def _compose_batch_id(now: datetime, rng: random.Random) -> str:
    """Compose a fresh ``batch_id`` for a real-dispatch invocation.

    Shape: ``batch-YYYYMMDDTHHMMSSZ-{4hex}``. Deterministic given
    ``now`` and ``rng`` so tests can pin both for stability. The hex
    suffix avoids same-second collisions between operator-driven
    re-runs.
    """
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = "".join(rng.choice("0123456789abcdef") for _ in range(4))
    return f"batch-{stamp}-{suffix}"


def _do_dry_run(
    ticket_ids: list[str],
    ticket_dir: str,
) -> int:
    """Emit either the AC#6 table or the ARG1-011 id list.

    The table is emitted when :func:`dispatch_module.plan_dispatch`
    succeeds without ``serial_fallback`` (every ticket has a Plan
    section). Otherwise the ARG1-011 id list is emitted for
    backwards compatibility — operators using a STATE.md whose
    queued tickets are not yet present on disk (the bootstrap case)
    still get useful output.
    """
    plan = dispatch_module.plan_dispatch(ticket_ids, ticket_dir=ticket_dir)
    if plan.serial_fallback:
        for tid in ticket_ids:
            sys.stdout.write(f"{tid}\n")
        return 0
    sys.stdout.write(dispatch_module.render_dry_run_table(plan))
    return 0


def main(argv: list[str]) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

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

    if args.dry_run:
        return _do_dry_run(ticket_ids, args.ticket_dir)

    if not args.epic:
        sys.stderr.write(
            "orchestrate: --epic is required for real dispatch "
            "(use --dry-run to preview without dispatching)\n"
        )
        return 2

    max_parallel = _resolve_max_parallel(args.max_parallel)
    batch_id = _compose_batch_id(datetime.now(timezone.utc), random.SystemRandom())

    repo_root = dispatch_module.default_repo_root()
    dispatch_root = Path(repo_root) / "argos" / "specs" / "dispatch"

    result = dispatch_module.dispatch_batch(
        ticket_ids,
        epic_id=args.epic,
        batch_id=batch_id,
        max_parallel=max_parallel,
        repo_root=repo_root,
        dispatch_root=dispatch_root,
        ticket_dir=args.ticket_dir,
        info_stream=sys.stdout,
    )

    failed = [o for o in result.outcomes if o.returncode != 0]
    if failed:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
