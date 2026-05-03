"""Parallel dispatch loop for ARG1-022.

The orchestrator's main dispatch surface. Consumes a batch of ticket
ids, partitions them into independence groups via
:mod:`argos.cli.orchestrator.independence` (ARG1-021), spawns
per-ticket ``argos run-session`` subprocesses (ARG1-020) under a
``threading.Semaphore``-bounded slot pool of size ``max_parallel``,
and writes a dispatch log (ARG1-012) for each ticket on dispatch and
on completion.

Architectural pins (locked in the ticket's ``## Plan`` section, mirrored
here so the call sites have the canonical reference):

1. **Concurrency model — subprocess-managed.** Each per-ticket session
   runs as its own ``argos run-session`` subprocess. A ``threading.Thread``
   blocks on that subprocess; ``threading.Semaphore`` caps concurrency
   at ``max_parallel``. ``concurrent.futures`` would be cleaner but is
   not in the ARG1-064 lint-imports allowlist.
2. **Partial-batch failure — peers continue.** A non-zero exit from one
   session does not affect siblings. Each outcome is recorded
   independently. Auto-fix retry is ARG1-013's territory; this module
   does no retry, no signal-kill.
3. **Group barrier.** All sessions in group N must finish before any in
   group N+1 starts. No cross-group pipelining (per Non-goals).
4. **Strict criterion.** ``independence.partition`` is consumed verbatim;
   no carve-outs for shared registration files (ARG1-066's scope).

ADR-001 stdlib-only. Imports limited to the lint-imports allowlist.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Sequence

import argos
from argos.cli import dispatch_log
from argos.cli.orchestrator import independence

__all__ = [
    "DispatchEntry",
    "DispatchPlan",
    "SessionOutcome",
    "BatchResult",
    "SessionRequest",
    "SessionRunner",
    "DEFAULT_MAX_PARALLEL",
    "SERIAL_FALLBACK_MESSAGE",
    "plan_dispatch",
    "render_dry_run_table",
    "dispatch_batch",
    "default_session_runner",
    "default_repo_root",
    "default_short_sha",
]


# Default per the v1.0 config schema (`argos/specs/v1.0/schemas/config.md`
# §File 1) when no config loader is reachable.
DEFAULT_MAX_PARALLEL = 3

# Fallback diagnostic emitted on AC#4. Operators / tests grep for the
# substring "falling back to serial".
SERIAL_FALLBACK_MESSAGE = "independence detection failed; falling back to serial"


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DispatchEntry:
    """One row of the dispatch plan, one per ticket in the batch.

    ``group`` and ``dispatch_order`` are 1-indexed for human-readable
    rendering (the AC#6 markdown table). ``parallel_with`` is the list
    of other tickets that share this entry's group.
    """

    ticket_id: str
    group: int
    dispatch_order: int
    parallel_with: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DispatchPlan:
    """The full plan for a batch, in input order.

    ``serial_fallback`` is True iff :func:`plan_dispatch` could not load
    every ticket (any :class:`independence.IndependenceError`) and
    degraded to one-ticket-per-group serial dispatch.
    """

    entries: tuple[DispatchEntry, ...]
    serial_fallback: bool


@dataclass(frozen=True)
class SessionOutcome:
    """The result of one dispatched session."""

    ticket_id: str
    worktree_path: Path
    branch: str
    returncode: int
    started_at: datetime
    finished_at: datetime


@dataclass(frozen=True)
class BatchResult:
    """The outcome of one ``dispatch_batch`` call."""

    plan: DispatchPlan
    outcomes: tuple[SessionOutcome, ...]


@dataclass(frozen=True)
class SessionRequest:
    """The arguments handed to a :data:`SessionRunner`.

    Kept frozen so test seams cannot mutate runtime state. Production
    callers receive the same shape so swapping the runner has no
    accidental coupling.
    """

    ticket_id: str
    epic_id: str
    batch_id: str
    worktree_path: Path
    branch: str
    repo_root: Path
    session_id: str


# A SessionRunner takes a SessionRequest and returns the subprocess exit
# code. Implementations are responsible for actually spawning the
# per-ticket session (or, in tests, simulating one).
SessionRunner = Callable[[SessionRequest], int]


# ---------------------------------------------------------------------------
# Plan construction
# ---------------------------------------------------------------------------


def plan_dispatch(
    ticket_ids: Sequence[str],
    *,
    ticket_dir: str | Path = independence.DEFAULT_TICKET_DIR,
) -> DispatchPlan:
    """Run ARG1-021's independence detector and return a dispatch plan.

    On any :class:`independence.IndependenceError` (missing ticket file,
    missing ``files_touched:``, malformed ticket id), each ticket is
    placed in its own group and ``serial_fallback=True``. Callers are
    responsible for surfacing the fallback diagnostic to the operator;
    the plan itself only records the boolean.
    """
    try:
        loaded = [independence.load_ticket(t, ticket_dir) for t in ticket_ids]
        groups = independence.partition(loaded)
        return _build_plan(ticket_ids, groups, serial=False)
    except independence.IndependenceError:
        groups = [[t] for t in ticket_ids]
        return _build_plan(ticket_ids, groups, serial=True)


def _build_plan(
    ticket_ids: Sequence[str],
    groups: Sequence[Sequence[str]],
    *,
    serial: bool,
) -> DispatchPlan:
    """Compose a :class:`DispatchPlan` from a partition.

    Entry order in the returned plan is the input order of
    ``ticket_ids``; ``group`` and ``dispatch_order`` are derived from
    each ticket's position within its group.
    """
    entries_by_id: dict[str, DispatchEntry] = {}
    for gi, grp in enumerate(groups, start=1):
        for di, tid in enumerate(grp, start=1):
            others = tuple(t for t in grp if t != tid)
            entries_by_id[tid] = DispatchEntry(
                ticket_id=tid,
                group=gi,
                dispatch_order=di,
                parallel_with=others,
            )
    ordered: list[DispatchEntry] = []
    for tid in ticket_ids:
        if tid in entries_by_id:
            ordered.append(entries_by_id[tid])
    return DispatchPlan(entries=tuple(ordered), serial_fallback=serial)


# ---------------------------------------------------------------------------
# Dry-run table rendering (AC#6)
# ---------------------------------------------------------------------------


_TABLE_HEADER = "| ticket_id | group | dispatch_order | parallel_with |"
_TABLE_SEP = "|-----------|-------|----------------|---------------|"


def render_dry_run_table(plan: DispatchPlan) -> str:
    """Render ``plan`` as the canonical AC#6 markdown table.

    Columns, in order: ``ticket_id`` | ``group`` | ``dispatch_order`` |
    ``parallel_with``. Entries with no parallel siblings render as
    ``-`` so the column never collapses.
    """
    lines = [_TABLE_HEADER, _TABLE_SEP]
    for entry in plan.entries:
        if entry.parallel_with:
            pw = ", ".join(entry.parallel_with)
        else:
            pw = "-"
        lines.append(
            f"| {entry.ticket_id} | {entry.group} | "
            f"{entry.dispatch_order} | {pw} |"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Session runner — production default
# ---------------------------------------------------------------------------


def default_repo_root() -> Path:
    """Resolve the current git repo root, or ``Path.cwd()`` on failure.

    Uses ``git rev-parse --show-toplevel``. The orchestrate command
    invokes this once at start-up; tests bypass it by passing
    ``repo_root=`` explicitly.
    """
    res = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode == 0:
        return Path(res.stdout.strip()).resolve()
    return Path.cwd().resolve()


def default_short_sha(repo_root: Path) -> str:
    """Return the 7-char SHA of HEAD in ``repo_root``, or ``"head"``.

    Used to compose the worktree path
    ``.argos/worktrees/{ticket-id}-{short-sha}/`` per
    ARCHITECTURE.md §Components/Parallel Session Manager. The fallback
    string ``"head"`` is for repos with no commits yet (a freshly
    ``git init``'d test fixture); it is not reachable in production
    where the ticket's own merge added a commit.
    """
    res = subprocess.run(
        ["git", "rev-parse", "--short=7", "HEAD"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.strip()
    return "head"


def default_session_runner(req: SessionRequest) -> int:
    """Spawn ``argos run-session`` as a subprocess and return its exit code.

    The runner blocks until the child exits — the orchestrator's
    semaphore is what bounds concurrency, not this function. Stdio is
    inherited so an interactive session keeps its tty (the production
    use case); tests inject a non-interactive runner instead.

    Invoked as ``python3 -m argos.cli run-session --ticket ... --worktree
    ... --epic ...``. CWD is set to ``req.repo_root`` so
    ``git worktree add`` operates on the right repo. ``PYTHONPATH`` is
    augmented with the directory containing the running ``argos``
    package so the spawned interpreter can import ``argos.cli`` even
    when ``cwd`` is a temporary repo unrelated to the install (the
    test path) or when argos is run out of an in-repo checkout.
    """
    cmd = [
        sys.executable,
        "-m",
        "argos.cli",
        "run-session",
        "--ticket",
        req.ticket_id,
        "--worktree",
        str(req.worktree_path),
        "--epic",
        req.epic_id,
    ]
    env = dict(os.environ)
    pkg_parent = str(Path(argos.__file__).resolve().parents[1])
    existing = env.get("PYTHONPATH", "")
    parts = existing.split(os.pathsep) if existing else []
    if pkg_parent not in parts:
        env["PYTHONPATH"] = (
            pkg_parent + (os.pathsep + existing if existing else "")
        )
    completed = subprocess.run(
        cmd,
        cwd=str(req.repo_root),
        env=env,
        check=False,
    )
    return completed.returncode


# ---------------------------------------------------------------------------
# dispatch_batch — the public entry point
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _compose_session_id(batch_id: str, ticket_id: str) -> str:
    """Compose the ``session_id`` recorded in the dispatch log.

    Slug-shaped per ``argos.cli.dispatch_log._SESSION_ID_RE``: must
    match ``^[A-Za-z0-9._:T-]+$`` and be non-empty.
    """
    return f"{batch_id}-{ticket_id}"


def _compose_worktree_path(
    repo_root: Path,
    ticket_id: str,
    short_sha: str,
) -> Path:
    """Return ``<repo_root>/.argos/worktrees/<ticket-id>-<short-sha>/``."""
    return repo_root / ".argos" / "worktrees" / f"{ticket_id}-{short_sha}"


def _run_one_session(
    entry: DispatchEntry,
    *,
    epic_id: str,
    batch_id: str,
    repo_root: Path,
    dispatch_root: Path,
    short_sha: str,
    session_runner: SessionRunner,
) -> SessionOutcome:
    """Dispatch one ticket's session and write its dispatch log.

    Initial event ``dispatched`` is written before the runner is
    invoked; ``verifier-result`` is written after it returns. Both
    writes go to ``argos/specs/dispatch/{epic_id}/{ticket_id}.md`` via
    ARG1-012's writer.

    Per ticket Q3 confirmation: this function never touches STATE.md,
    so the ARG1-032 pre-commit hook is irrelevant on this code path.
    """
    ticket_id = entry.ticket_id
    branch = f"argos/{ticket_id}"
    worktree_path = _compose_worktree_path(repo_root, ticket_id, short_sha)
    session_id = _compose_session_id(batch_id, ticket_id)

    started_at = _utc_now()
    log_path = dispatch_log.write_dispatch_log(
        ticket_id=ticket_id,
        epic_id=epic_id,
        batch_id=batch_id,
        worktree_path=str(worktree_path),
        session_id=session_id,
        dispatch_root=dispatch_root,
        dispatched_at=started_at,
    )

    request = SessionRequest(
        ticket_id=ticket_id,
        epic_id=epic_id,
        batch_id=batch_id,
        worktree_path=worktree_path,
        branch=branch,
        repo_root=repo_root,
        session_id=session_id,
    )
    try:
        rc = session_runner(request)
    except Exception as exc:
        rc = 1
        finished_at = _utc_now()
        dispatch_log.append_event(
            dispatch_file=log_path,
            event_type=dispatch_log.EVENT_VERIFIER_RESULT,
            body=(
                f"- returncode: {rc}\n"
                f"- runner_exception: {type(exc).__name__}: {exc}"
            ),
            at=finished_at,
        )
        return SessionOutcome(
            ticket_id=ticket_id,
            worktree_path=worktree_path,
            branch=branch,
            returncode=rc,
            started_at=started_at,
            finished_at=finished_at,
        )

    finished_at = _utc_now()
    dispatch_log.append_event(
        dispatch_file=log_path,
        event_type=dispatch_log.EVENT_VERIFIER_RESULT,
        body=(
            f"- returncode: {rc}\n"
            f"- duration_s: {(finished_at - started_at).total_seconds():.3f}"
        ),
        at=finished_at,
    )
    return SessionOutcome(
        ticket_id=ticket_id,
        worktree_path=worktree_path,
        branch=branch,
        returncode=rc,
        started_at=started_at,
        finished_at=finished_at,
    )


def _dispatch_group(
    entries: Sequence[DispatchEntry],
    *,
    epic_id: str,
    batch_id: str,
    max_parallel: int,
    repo_root: Path,
    dispatch_root: Path,
    short_sha: str,
    session_runner: SessionRunner,
) -> list[SessionOutcome]:
    """Dispatch one independence group under a semaphore-bounded slot pool.

    Threads are launched eagerly — one per entry — but each blocks on
    the shared semaphore until a slot frees up. ``join`` after all
    threads are launched provides the group barrier required by
    architectural choice 4.
    """
    if max_parallel < 1:
        raise ValueError(f"max_parallel must be >= 1 (got {max_parallel})")

    sem = threading.Semaphore(max_parallel)
    outcomes_lock = threading.Lock()
    outcomes: list[SessionOutcome] = []

    def worker(entry: DispatchEntry) -> None:
        with sem:
            outcome = _run_one_session(
                entry,
                epic_id=epic_id,
                batch_id=batch_id,
                repo_root=repo_root,
                dispatch_root=dispatch_root,
                short_sha=short_sha,
                session_runner=session_runner,
            )
        with outcomes_lock:
            outcomes.append(outcome)

    threads: list[threading.Thread] = []
    for entry in entries:
        t = threading.Thread(
            target=worker,
            args=(entry,),
            name=f"dispatch-{entry.ticket_id}",
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    return outcomes


def dispatch_batch(
    ticket_ids: Sequence[str],
    *,
    epic_id: str,
    batch_id: str,
    max_parallel: int = DEFAULT_MAX_PARALLEL,
    repo_root: Optional[Path] = None,
    dispatch_root: Optional[Path] = None,
    ticket_dir: str | Path = independence.DEFAULT_TICKET_DIR,
    short_sha: Optional[str] = None,
    info_stream=None,
    session_runner: Optional[SessionRunner] = None,
) -> BatchResult:
    """Dispatch a batch of tickets and return per-session outcomes.

    Architectural choices 1–5 (see module docstring) are pinned here:

    - Builds the plan via :func:`plan_dispatch` (consumes ARG1-021
      verbatim; no carve-outs).
    - On ``serial_fallback``, writes
      ``"independence detection failed; falling back to serial"`` to
      ``info_stream`` (AC#4).
    - Iterates groups in plan order; within each group, dispatches up
      to ``max_parallel`` concurrent sessions; barriers between groups.
    - One outcome per ticket, in completion order (race-determined).

    ``session_runner`` is the test seam — defaults to spawning ``argos
    run-session`` as a subprocess.
    """
    if max_parallel < 1:
        raise ValueError(f"max_parallel must be >= 1 (got {max_parallel})")
    if not epic_id:
        raise ValueError("epic_id must be a non-empty string")
    if not batch_id:
        raise ValueError("batch_id must be a non-empty string")

    if repo_root is None:
        repo_root = default_repo_root()
    repo_root = Path(repo_root).resolve()
    if dispatch_root is None:
        dispatch_root = repo_root / "argos" / "specs" / "dispatch"
    dispatch_root = Path(dispatch_root)
    if short_sha is None:
        short_sha = default_short_sha(repo_root)
    if info_stream is None:
        info_stream = sys.stdout
    if session_runner is None:
        session_runner = default_session_runner

    plan = plan_dispatch(ticket_ids, ticket_dir=ticket_dir)
    if plan.serial_fallback:
        info_stream.write(SERIAL_FALLBACK_MESSAGE + "\n")
        info_stream.flush()

    groups: dict[int, list[DispatchEntry]] = {}
    for entry in plan.entries:
        groups.setdefault(entry.group, []).append(entry)

    all_outcomes: list[SessionOutcome] = []
    for group_idx in sorted(groups):
        group_entries = groups[group_idx]
        group_outcomes = _dispatch_group(
            group_entries,
            epic_id=epic_id,
            batch_id=batch_id,
            max_parallel=max_parallel,
            repo_root=repo_root,
            dispatch_root=dispatch_root,
            short_sha=short_sha,
            session_runner=session_runner,
        )
        all_outcomes.extend(group_outcomes)

    return BatchResult(plan=plan, outcomes=tuple(all_outcomes))
