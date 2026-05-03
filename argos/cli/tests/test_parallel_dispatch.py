"""Tests for ARG1-022: parallel dispatch loop.

Covers the library surface (``plan_dispatch``, ``render_dry_run_table``,
``dispatch_batch``) and the CLI surface (``argos orchestrate`` real
dispatch + dry-run table). Stdlib-only per ADR-001 / ADR-002.

Runnable as::

    python3 -m unittest argos.cli.tests.test_parallel_dispatch -v
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli.orchestrator.dispatch import (  # noqa: E402
    SERIAL_FALLBACK_MESSAGE,
    DispatchEntry,
    DispatchPlan,
    SessionRequest,
    dispatch_batch,
    plan_dispatch,
    render_dry_run_table,
)

_ARGOS_BIN = Path(__file__).resolve().parents[1] / "argos"


# ---------------------------------------------------------------------------
# Ticket-fixture helpers
# ---------------------------------------------------------------------------


_TICKET_TEMPLATE = textwrap.dedent(
    """\
    ---
    ticket_id: {tid}
    {depends_block}---

    # {tid}

    ## Plan

    files_touched:
    {files_block}
    """
)


def _write_ticket(
    ticket_dir: Path,
    ticket_id: str,
    files: list[str],
    depends_on: list[str] | None = None,
) -> Path:
    """Write a synthetic ticket file under ``ticket_dir`` and return its path."""
    if depends_on:
        depends_block = (
            "depends_on:\n"
            + "".join(f"  - {d}\n" for d in depends_on)
        )
    else:
        depends_block = ""
    files_block = "\n".join(f"  - {f}" for f in files) or "  - (none)"
    body = _TICKET_TEMPLATE.format(
        tid=ticket_id,
        depends_block=depends_block,
        files_block=files_block,
    )
    path = ticket_dir / f"{ticket_id}-fixture.md"
    path.write_text(body, encoding="utf-8")
    return path


def _write_three_independent_tickets(ticket_dir: Path) -> tuple[str, str, str]:
    a, b, c = "ARG1-901", "ARG1-902", "ARG1-903"
    _write_ticket(ticket_dir, a, ["argos/cli/x901.py"])
    _write_ticket(ticket_dir, b, ["argos/cli/x902.py"])
    _write_ticket(ticket_dir, c, ["argos/cli/x903.py"])
    return a, b, c


def _write_two_dependent_one_independent(ticket_dir: Path) -> tuple[str, str, str]:
    a, b, c = "ARG1-911", "ARG1-912", "ARG1-913"
    _write_ticket(ticket_dir, a, ["argos/cli/shared.py"])
    _write_ticket(ticket_dir, b, ["argos/cli/shared.py"])  # shares with A
    _write_ticket(ticket_dir, c, ["argos/cli/x913.py"])
    return a, b, c


# ---------------------------------------------------------------------------
# Fake repo helpers
# ---------------------------------------------------------------------------


def _git_init_repo(repo_root: Path) -> str:
    """Initialize a fresh git repo with one commit; return short HEAD sha."""
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(repo_root)],
        check=True,
        capture_output=True,
    )
    # Identity required for commits in CI.
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "user.name", "Test"],
        check=True,
    )
    (repo_root / "README.md").write_text("seed", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo_root), "add", "README.md"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_root), "commit", "-m", "seed"],
        check=True,
        capture_output=True,
    )
    res = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--short=7", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return res.stdout.strip()


# ---------------------------------------------------------------------------
# Stub session runners
# ---------------------------------------------------------------------------


class _RecordingRunner:
    """Records start/end timestamps + concurrency for each session call.

    A single instance is shared across worker threads so the test can
    inspect the recorded outcomes after ``dispatch_batch`` returns.
    """

    def __init__(self, sleep_for: float = 0.0, returncodes: dict | None = None) -> None:
        self.sleep_for = sleep_for
        self.returncodes = returncodes or {}
        self._lock = threading.Lock()
        self.calls: list[dict] = []
        self._active = 0
        self.peak = 0

    def __call__(self, req: SessionRequest) -> int:
        with self._lock:
            self._active += 1
            self.peak = max(self.peak, self._active)
            self.calls.append(
                {
                    "ticket_id": req.ticket_id,
                    "epic_id": req.epic_id,
                    "started_at": time.time(),
                    "worktree_path": req.worktree_path,
                }
            )
            idx = len(self.calls) - 1
        try:
            if self.sleep_for > 0:
                time.sleep(self.sleep_for)
        finally:
            with self._lock:
                self._active -= 1
                self.calls[idx]["finished_at"] = time.time()
        return int(self.returncodes.get(req.ticket_id, 0))


# ---------------------------------------------------------------------------
# plan_dispatch
# ---------------------------------------------------------------------------


class PlanDispatchTests(unittest.TestCase):
    def test_three_independent_tickets_one_group(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            a, b, c = _write_three_independent_tickets(tdir)
            plan = plan_dispatch([a, b, c], ticket_dir=tdir)
            self.assertFalse(plan.serial_fallback)
            self.assertEqual(len(plan.entries), 3)
            self.assertEqual({e.group for e in plan.entries}, {1})
            for entry in plan.entries:
                self.assertEqual(set(entry.parallel_with), {a, b, c} - {entry.ticket_id})

    def test_dependent_pair_serializes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            a, b, c = _write_two_dependent_one_independent(tdir)
            plan = plan_dispatch([a, b, c], ticket_dir=tdir)
            self.assertFalse(plan.serial_fallback)
            groups = sorted({e.group for e in plan.entries})
            self.assertEqual(groups, [1, 2])
            entry_a = next(e for e in plan.entries if e.ticket_id == a)
            entry_b = next(e for e in plan.entries if e.ticket_id == b)
            self.assertNotEqual(entry_a.group, entry_b.group)

    def test_missing_plan_section_falls_back_to_serial(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            (tdir / "ARG1-921-broken.md").write_text(
                "---\nticket_id: ARG1-921\n---\n\n# ARG1-921\n", encoding="utf-8"
            )
            plan = plan_dispatch(["ARG1-921"], ticket_dir=tdir)
            self.assertTrue(plan.serial_fallback)
            self.assertEqual(len(plan.entries), 1)
            self.assertEqual(plan.entries[0].group, 1)

    def test_input_order_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            a, b, c = _write_three_independent_tickets(tdir)
            plan = plan_dispatch([c, a, b], ticket_dir=tdir)
            self.assertEqual([e.ticket_id for e in plan.entries], [c, a, b])


# ---------------------------------------------------------------------------
# render_dry_run_table
# ---------------------------------------------------------------------------


class RenderTableTests(unittest.TestCase):
    def test_header_columns(self) -> None:
        plan = DispatchPlan(entries=(), serial_fallback=False)
        out = render_dry_run_table(plan)
        first_line = out.splitlines()[0]
        # Required columns in canonical order, AC#6 verbatim.
        self.assertIn("ticket_id", first_line)
        self.assertIn("group", first_line)
        self.assertIn("dispatch_order", first_line)
        self.assertIn("parallel_with", first_line)
        self.assertLess(first_line.index("ticket_id"), first_line.index("group"))
        self.assertLess(first_line.index("group"), first_line.index("dispatch_order"))
        self.assertLess(
            first_line.index("dispatch_order"), first_line.index("parallel_with")
        )

    def test_body_rows_one_per_entry(self) -> None:
        plan = DispatchPlan(
            entries=(
                DispatchEntry("ARG1-901", 1, 1, ("ARG1-902",)),
                DispatchEntry("ARG1-902", 1, 2, ("ARG1-901",)),
                DispatchEntry("ARG1-903", 2, 1, ()),
            ),
            serial_fallback=False,
        )
        out = render_dry_run_table(plan)
        body = out.splitlines()[2:]
        self.assertEqual(len(body), 3)
        self.assertIn("ARG1-901", body[0])
        self.assertIn("ARG1-902", body[1])
        self.assertIn("ARG1-903", body[2])
        # No-parallel entry renders the column as ``-`` (not blank).
        self.assertIn("| - |", body[2])


# ---------------------------------------------------------------------------
# dispatch_batch
# ---------------------------------------------------------------------------


class DispatchBatchTests(unittest.TestCase):
    """End-to-end tests of dispatch_batch with stub session runners."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name).resolve()
        self.short_sha = _git_init_repo(self.repo_root)
        self.ticket_dir = self.repo_root / "tickets"
        self.ticket_dir.mkdir()
        self.dispatch_root = self.repo_root / "argos" / "specs" / "dispatch"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_max_parallel_3_observes_three_concurrent(self) -> None:
        # AC#1 (library form): three independent tickets, max_parallel=3,
        # peak observed concurrency is 3.
        a, b, c = _write_three_independent_tickets(self.ticket_dir)
        runner = _RecordingRunner(sleep_for=0.3)
        info = io.StringIO()
        result = dispatch_batch(
            [a, b, c],
            epic_id="EPIC-901",
            batch_id="batch-test-001",
            max_parallel=3,
            repo_root=self.repo_root,
            dispatch_root=self.dispatch_root,
            ticket_dir=self.ticket_dir,
            short_sha=self.short_sha,
            info_stream=info,
            session_runner=runner,
        )
        self.assertEqual(runner.peak, 3)
        self.assertEqual(len(result.outcomes), 3)
        self.assertFalse(result.plan.serial_fallback)
        self.assertNotIn("falling back to serial", info.getvalue())

    def test_max_parallel_1_serializes(self) -> None:
        # AC#2: max_parallel=1 → wall-clock ≥ 0.95 × Σ durations.
        a, b, c = _write_three_independent_tickets(self.ticket_dir)
        per_session = 0.2
        runner = _RecordingRunner(sleep_for=per_session)
        t0 = time.time()
        result = dispatch_batch(
            [a, b, c],
            epic_id="EPIC-902",
            batch_id="batch-test-002",
            max_parallel=1,
            repo_root=self.repo_root,
            dispatch_root=self.dispatch_root,
            ticket_dir=self.ticket_dir,
            short_sha=self.short_sha,
            info_stream=io.StringIO(),
            session_runner=runner,
        )
        wall = time.time() - t0
        self.assertGreaterEqual(wall, 3 * per_session * 0.95)
        self.assertEqual(runner.peak, 1)
        self.assertEqual(len(result.outcomes), 3)

    def test_dependent_pair_serialized_independent_overlaps(self) -> None:
        # AC#3: dispatch log timestamps prove two-dependent are serial,
        # independent runs in parallel with the first dependent.
        a, b, c = _write_two_dependent_one_independent(self.ticket_dir)
        runner = _RecordingRunner(sleep_for=0.2)
        result = dispatch_batch(
            [a, b, c],
            epic_id="EPIC-903",
            batch_id="batch-test-003",
            max_parallel=3,
            repo_root=self.repo_root,
            dispatch_root=self.dispatch_root,
            ticket_dir=self.ticket_dir,
            short_sha=self.short_sha,
            info_stream=io.StringIO(),
            session_runner=runner,
        )
        outcomes = {o.ticket_id: o for o in result.outcomes}
        # Group 1 is [a, c] (greedy first-fit places them together);
        # Group 2 is [b]. So a/c overlap, then b runs after both finish.
        a_outcome = outcomes[a]
        b_outcome = outcomes[b]
        c_outcome = outcomes[c]
        # The dependent ticket b started after both a and c finished
        # (group barrier).
        self.assertGreaterEqual(b_outcome.started_at, a_outcome.finished_at)
        self.assertGreaterEqual(b_outcome.started_at, c_outcome.finished_at)
        # The independent c overlapped with a.
        self.assertLess(c_outcome.started_at, a_outcome.finished_at)
        # Verify dispatch log wrote the timestamps too.
        log_a = self.dispatch_root / "EPIC-903" / f"{a}.md"
        self.assertTrue(log_a.is_file())
        log_b = self.dispatch_root / "EPIC-903" / f"{b}.md"
        self.assertTrue(log_b.is_file())

    def test_independence_failure_falls_back_to_serial(self) -> None:
        # AC#4: ARG1-021 raises (one ticket missing files_touched) →
        # stdout contains the canonical message AND each ticket runs
        # serially (peak concurrency 1).
        a = "ARG1-931"
        b = "ARG1-932"
        c = "ARG1-933"
        _write_ticket(self.ticket_dir, a, ["argos/cli/x931.py"])
        # B is missing the Plan section entirely.
        (self.ticket_dir / f"{b}-broken.md").write_text(
            f"---\nticket_id: {b}\n---\n\n# {b}\n", encoding="utf-8"
        )
        _write_ticket(self.ticket_dir, c, ["argos/cli/x933.py"])
        runner = _RecordingRunner(sleep_for=0.2)
        info = io.StringIO()
        result = dispatch_batch(
            [a, b, c],
            epic_id="EPIC-904",
            batch_id="batch-test-004",
            max_parallel=3,
            repo_root=self.repo_root,
            dispatch_root=self.dispatch_root,
            ticket_dir=self.ticket_dir,
            short_sha=self.short_sha,
            info_stream=info,
            session_runner=runner,
        )
        self.assertIn(SERIAL_FALLBACK_MESSAGE, info.getvalue())
        self.assertTrue(result.plan.serial_fallback)
        # Each ticket alone in its own group → max concurrency is 1.
        self.assertEqual(runner.peak, 1)

    def test_no_orphaned_worktrees_under_stub_runner(self) -> None:
        # AC#5: no worktrees beyond expected. The stub runner does not
        # create worktrees (it's a no-op stub), so we verify dispatch
        # itself created none either — the worktree creation lives in
        # the run-session subprocess, which the stub bypasses.
        a, b, c = _write_three_independent_tickets(self.ticket_dir)
        runner = _RecordingRunner(sleep_for=0.05)
        dispatch_batch(
            [a, b, c],
            epic_id="EPIC-905",
            batch_id="batch-test-005",
            max_parallel=3,
            repo_root=self.repo_root,
            dispatch_root=self.dispatch_root,
            ticket_dir=self.ticket_dir,
            short_sha=self.short_sha,
            info_stream=io.StringIO(),
            session_runner=runner,
        )
        worktrees_root = self.repo_root / ".argos" / "worktrees"
        # Either non-existent or empty — stub does not create worktrees,
        # and dispatcher itself does not pre-create them.
        if worktrees_root.exists():
            self.assertEqual(list(worktrees_root.iterdir()), [])

    def test_partial_failure_does_not_kill_peers(self) -> None:
        # Q2 architectural choice: option (a) — A fails, B and C complete.
        a, b, c = _write_three_independent_tickets(self.ticket_dir)
        runner = _RecordingRunner(
            sleep_for=0.1,
            returncodes={a: 7},  # A fails; B and C succeed.
        )
        result = dispatch_batch(
            [a, b, c],
            epic_id="EPIC-906",
            batch_id="batch-test-006",
            max_parallel=3,
            repo_root=self.repo_root,
            dispatch_root=self.dispatch_root,
            ticket_dir=self.ticket_dir,
            short_sha=self.short_sha,
            info_stream=io.StringIO(),
            session_runner=runner,
        )
        codes = {o.ticket_id: o.returncode for o in result.outcomes}
        self.assertEqual(codes[a], 7)
        self.assertEqual(codes[b], 0)
        self.assertEqual(codes[c], 0)

    def test_dispatch_log_files_written(self) -> None:
        # The orchestrator writes ARG1-012's dispatch log per ticket.
        a, b, c = _write_three_independent_tickets(self.ticket_dir)
        runner = _RecordingRunner(sleep_for=0.0)
        dispatch_batch(
            [a, b, c],
            epic_id="EPIC-907",
            batch_id="batch-test-007",
            max_parallel=3,
            repo_root=self.repo_root,
            dispatch_root=self.dispatch_root,
            ticket_dir=self.ticket_dir,
            short_sha=self.short_sha,
            info_stream=io.StringIO(),
            session_runner=runner,
        )
        epic_dir = self.dispatch_root / "EPIC-907"
        self.assertTrue(epic_dir.is_dir())
        names = sorted(p.name for p in epic_dir.glob("*.md"))
        self.assertEqual(names, sorted([f"{a}.md", f"{b}.md", f"{c}.md"]))
        for tid in (a, b, c):
            text = (epic_dir / f"{tid}.md").read_text(encoding="utf-8")
            self.assertIn("type=dispatched", text)
            self.assertIn("type=verifier-result", text)


# ---------------------------------------------------------------------------
# CLI: --dry-run table (AC#6)
# ---------------------------------------------------------------------------


def _write_state_with_queue(path: Path, ticket_ids: list[str]) -> None:
    body = "# STATE\n\n## Queue\n\n"
    for tid in ticket_ids:
        body += f"- {tid} — fixture (P0)\n"
    body += "\n## In progress\n\n_none_\n"
    path.write_text(body, encoding="utf-8")


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_ARGOS_BIN), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd) if cwd is not None else None,
    )


class OrchestrateDryRunTableTests(unittest.TestCase):
    """AC#6: ``argos orchestrate --batch-size 5 --dry-run`` emits the table."""

    def test_dry_run_emits_markdown_table(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td) / "tickets"
            tdir.mkdir()
            a, b, c = _write_three_independent_tickets(tdir)
            state = Path(td) / "STATE.md"
            _write_state_with_queue(state, [a, b, c])
            res = _run_cli(
                "orchestrate",
                "--dry-run",
                "--batch-size",
                "5",
                "--state-file",
                str(state),
                "--ticket-dir",
                str(tdir),
            )
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            stdout = res.stdout
            # Header columns in canonical order.
            self.assertIn("ticket_id", stdout)
            self.assertIn("group", stdout)
            self.assertIn("dispatch_order", stdout)
            self.assertIn("parallel_with", stdout)
            # One body row per queued ticket.
            for tid in (a, b, c):
                self.assertIn(tid, stdout)

    def test_dry_run_falls_back_to_id_list_when_plans_missing(self) -> None:
        # ARG1-011 backwards compatibility — the existing test fixture
        # never had ticket files; we keep the id-per-line behavior in
        # that case.
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "STATE.md"
            _write_state_with_queue(state, ["ARG1-991", "ARG1-992", "ARG1-993"])
            res = _run_cli(
                "orchestrate",
                "--dry-run",
                "--state-file",
                str(state),
                "--ticket-dir",
                str(Path(td) / "no-tickets-here"),
            )
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            self.assertEqual(
                res.stdout.splitlines(),
                ["ARG1-991", "ARG1-992", "ARG1-993"],
            )


# ---------------------------------------------------------------------------
# CLI: real dispatch via the launcher (smoke + AC#5 scoping)
# ---------------------------------------------------------------------------


class OrchestrateRealDispatchTests(unittest.TestCase):
    """End-to-end dispatch through ``python3 -m argos.cli orchestrate``.

    Uses a fake harness binary (so ``argos run-session`` doesn't try to
    spawn real ``claude``) plus a fresh git repo. Verifies the
    real-dispatch path returns 0 on stub-success, writes one dispatch
    log per ticket, creates one worktree per ticket, and surfaces the
    serial-fallback message when a ticket lacks a Plan section.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name).resolve()
        self.short_sha = _git_init_repo(self.repo_root)
        self.ticket_dir = self.repo_root / "tickets"
        self.ticket_dir.mkdir()
        # Fake harness binary that exits 0 immediately. The real claude
        # binary is replaced via ARGOS_RUN_SESSION_HARNESS_BIN so the
        # subprocess runs without external dependencies.
        self.fake_harness = self.repo_root / "fake-claude"
        self.fake_harness.write_text(
            "#!/bin/sh\nexit 0\n", encoding="utf-8"
        )
        os.chmod(self.fake_harness, 0o755)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _state_path(self) -> Path:
        return self.repo_root / "STATE.md"

    def _run_orchestrate(self, *extra_args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["ARGOS_RUN_SESSION_HARNESS_BIN"] = str(self.fake_harness)
        return subprocess.run(
            [
                sys.executable,
                str(_ARGOS_BIN),
                "orchestrate",
                *extra_args,
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(self.repo_root),
            env=env,
        )

    def test_real_dispatch_three_independent_returns_zero(self) -> None:
        a, b, c = _write_three_independent_tickets(self.ticket_dir)
        _write_state_with_queue(self._state_path(), [a, b, c])
        res = self._run_orchestrate(
            "--state-file",
            str(self._state_path()),
            "--ticket-dir",
            str(self.ticket_dir),
            "--epic",
            "EPIC-T01",
            "--max-parallel",
            "3",
            "--batch-size",
            "3",
        )
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        # One dispatch log per ticket.
        epic_dir = self.repo_root / "argos" / "specs" / "dispatch" / "EPIC-T01"
        self.assertTrue(epic_dir.is_dir())
        names = sorted(p.name for p in epic_dir.glob("*.md"))
        self.assertEqual(names, sorted([f"{a}.md", f"{b}.md", f"{c}.md"]))
        # AC#5 scoping: worktrees-root contains exactly the dispatched
        # ticket worktrees, no orphans.
        worktrees_root = self.repo_root / ".argos" / "worktrees"
        self.assertTrue(worktrees_root.is_dir())
        worktree_names = sorted(p.name for p in worktrees_root.iterdir())
        self.assertEqual(
            worktree_names,
            sorted(
                [
                    f"{a}-{self.short_sha}",
                    f"{b}-{self.short_sha}",
                    f"{c}-{self.short_sha}",
                ]
            ),
        )

    def test_real_dispatch_missing_epic_rejected(self) -> None:
        a, b, c = _write_three_independent_tickets(self.ticket_dir)
        _write_state_with_queue(self._state_path(), [a, b, c])
        res = self._run_orchestrate(
            "--state-file",
            str(self._state_path()),
            "--ticket-dir",
            str(self.ticket_dir),
        )
        self.assertEqual(res.returncode, 2)
        self.assertIn("--epic is required", res.stderr)

    def test_real_dispatch_serial_fallback_message_on_missing_plan(self) -> None:
        a = "ARG1-941"
        b = "ARG1-942"
        _write_ticket(self.ticket_dir, a, ["argos/cli/x941.py"])
        # b lacks a Plan section — independence raises
        # MissingFilesTouchedError.
        (self.ticket_dir / f"{b}-broken.md").write_text(
            f"---\nticket_id: {b}\n---\n\n# {b}\n", encoding="utf-8"
        )
        _write_state_with_queue(self._state_path(), [a, b])
        res = self._run_orchestrate(
            "--state-file",
            str(self._state_path()),
            "--ticket-dir",
            str(self.ticket_dir),
            "--epic",
            "EPIC-T02",
        )
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn(SERIAL_FALLBACK_MESSAGE, res.stdout)


# ---------------------------------------------------------------------------
# AC#1 wrapper: ps -ef proves overlap with real subprocesses
# ---------------------------------------------------------------------------


@unittest.skipUnless(shutil.which("ps"), "ps not on PATH; AC#1 wrapper is POSIX-only")
class WrapperHarnessProcessOverlapTests(unittest.TestCase):
    """AC#1 (verbatim): three concurrent ``claude`` processes at peak.

    Spawns three sessions through the real ``argos run-session`` path
    using a fake harness named ``claude`` (so ``ps -ef | grep claude``
    matches), polls ``ps`` while orchestrate runs, and asserts the
    peak overlap is ≥ 3.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name).resolve()
        self.short_sha = _git_init_repo(self.repo_root)
        self.ticket_dir = self.repo_root / "tickets"
        self.ticket_dir.mkdir()
        # Fake "claude" sleeps so we get an observable overlap window.
        bin_dir = self.repo_root / "bin"
        bin_dir.mkdir()
        fake_claude = bin_dir / "claude"
        fake_claude.write_text(
            "#!/bin/sh\nsleep 1.5\nexit 0\n", encoding="utf-8"
        )
        os.chmod(fake_claude, 0o755)
        self.fake_claude = fake_claude

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _ps_count(self, marker: str) -> int:
        try:
            res = subprocess.run(
                ["ps", "-eo", "pid,command"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            return 0
        if res.returncode != 0:
            return 0
        count = 0
        for line in res.stdout.splitlines():
            if marker in line and "grep" not in line:
                count += 1
        return count

    def test_three_concurrent_claude_processes_at_peak(self) -> None:
        a, b, c = _write_three_independent_tickets(self.ticket_dir)
        state = self.repo_root / "STATE.md"
        _write_state_with_queue(state, [a, b, c])
        env = dict(os.environ)
        env["ARGOS_RUN_SESSION_HARNESS_BIN"] = str(self.fake_claude)
        proc = subprocess.Popen(
            [
                sys.executable,
                str(_ARGOS_BIN),
                "orchestrate",
                "--state-file",
                str(state),
                "--ticket-dir",
                str(self.ticket_dir),
                "--epic",
                "EPIC-PSACT",
                "--max-parallel",
                "3",
                "--batch-size",
                "3",
            ],
            cwd=str(self.repo_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        peak = 0
        marker = str(self.fake_claude)
        deadline = time.time() + 5.0
        try:
            while proc.poll() is None and time.time() < deadline:
                peak = max(peak, self._ps_count(marker))
                time.sleep(0.05)
        finally:
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr.read() if proc.stderr else "")
        self.assertGreaterEqual(
            peak,
            3,
            msg=f"expected peak ≥ 3 concurrent {marker} processes, observed {peak}",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
