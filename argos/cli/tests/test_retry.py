"""Tests for ARG1-013: orchestrator auto-fix retry (cap: 1).

Covers every acceptance criterion in
``argos/specs/v1.0/tickets/ARG1-013-orchestrator-auto-fix-retry.md``:

- AC#1 — verifier ``decision: fail`` triggers a retry; two distinct
  ``session_id`` strings appear in the dispatch log.
- AC#2 — verifier fails then passes on retry; final dispatch-log entry
  carries ``decision: pass`` and no escalation file is written.
- AC#3 — verifier fails twice; exactly one blocking escalation file is
  written and there are exactly two distinct ``session_id`` strings in
  the dispatch log (no third dispatch).
- AC#4 — ``decision: pass-with-minors`` does not trigger a retry; one
  ``session_id`` in the dispatch log and a verified-with-minors-shaped
  decision recorded.
- AC#5 — ``verifier.auto_fix_retries = 0`` disables the retry; a
  ``decision: fail`` produces an escalation immediately after the
  first verifier pass and the dispatch log still has exactly one
  ``session_id``.

Plus library-level tests for the helpers in ``argos.cli.orchestrator.retry``:

- ``read_latest_verifier_output`` returns the LAST block (not the first).
- ``compose_retry_session_id`` shape conforms to the dispatch_log slug.
- ``maybe_retry`` is a no-op when no verifier-output is found.

Stdlib only per ADR-001 / ADR-002.

Runnable as::

    python3 -m unittest argos.cli.tests.test_retry -v
"""

from __future__ import annotations

import io
import re
import sys
import tempfile
import textwrap
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli.orchestrator.dispatch import (  # noqa: E402
    SessionRequest,
    dispatch_batch,
)
from argos.cli.orchestrator.retry import (  # noqa: E402
    DEFAULT_TICKET_DIR_IN_WORKTREE,
    RetryConfig,
    compose_retry_session_id,
    maybe_retry,
    read_decision,
    read_latest_verifier_output,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


_TICKET_FRONTMATTER = textwrap.dedent(
    """\
    ---
    ticket_id: {tid}
    ---

    # {tid}

    ## Plan

    files_touched:
      - argos/cli/x{slug}.py
    """
)


def _write_ticket_in_dir(ticket_dir: Path, ticket_id: str) -> Path:
    """Write a synthetic ticket file with a Plan section.

    Used both for the planner's independence detection (top-level
    ``ticket_dir``) and inside a worktree (``worktree/argos/specs/v1.0/
    tickets/``). The body has a Plan section so independence detection
    succeeds.
    """
    slug = ticket_id.split("-")[-1]
    body = _TICKET_FRONTMATTER.format(tid=ticket_id, slug=slug)
    ticket_dir.mkdir(parents=True, exist_ok=True)
    path = ticket_dir / f"{ticket_id}-fixture.md"
    path.write_text(body, encoding="utf-8")
    return path


def _verifier_block(decision: str, *, with_minors: bool = False) -> str:
    """Compose a valid <!-- argos:verifier-output --> block."""
    if decision == "pass":
        return (
            "<!-- argos:verifier-output -->\n"
            "tests_ran: true\n"
            "findings: []\n"
            "decision: pass\n"
            "<!-- /argos:verifier-output -->\n"
        )
    if decision == "pass-with-minors" or (decision == "pass" and with_minors):
        return (
            "<!-- argos:verifier-output -->\n"
            "tests_ran: true\n"
            "findings:\n"
            "  - severity: minor\n"
            '    description: "unused import"\n'
            "decision: pass-with-minors\n"
            "<!-- /argos:verifier-output -->\n"
        )
    if decision == "fail":
        return (
            "<!-- argos:verifier-output -->\n"
            "tests_ran: true\n"
            "findings:\n"
            "  - severity: critical\n"
            '    description: "tests/test_foo.py::test_bar failed"\n'
            "decision: fail\n"
            "<!-- /argos:verifier-output -->\n"
        )
    raise ValueError(f"unknown decision: {decision!r}")


def _append_verifier_block_to_ticket(
    worktree: Path,
    ticket_id: str,
    decision: str,
) -> None:
    """Append a verifier-output block to the in-worktree ticket file."""
    base = worktree / DEFAULT_TICKET_DIR_IN_WORKTREE
    base.mkdir(parents=True, exist_ok=True)
    matches = list(base.glob(f"{ticket_id}*.md"))
    if matches:
        path = matches[0]
        existing = path.read_text(encoding="utf-8")
    else:
        path = base / f"{ticket_id}-fixture.md"
        existing = _TICKET_FRONTMATTER.format(
            tid=ticket_id, slug=ticket_id.split("-")[-1]
        )
    body = existing.rstrip("\n") + "\n\n## Verification\n\n"
    body += _verifier_block(decision)
    path.write_text(body, encoding="utf-8")


def _make_request(
    *,
    ticket_id: str,
    worktree: Path,
    epic_id: str = "EPIC-T013",
    batch_id: str = "batch-test-013",
    session_id: str | None = None,
) -> SessionRequest:
    return SessionRequest(
        ticket_id=ticket_id,
        epic_id=epic_id,
        batch_id=batch_id,
        worktree_path=worktree,
        branch=f"argos/{ticket_id}",
        repo_root=worktree.parent,
        session_id=session_id or f"{batch_id}-{ticket_id}",
    )


def _count_session_id_lines(text: str) -> int:
    """Count `- session: <id>` lines in a dispatch-log file body."""
    return len(re.findall(r"^- session:\s+", text, flags=re.MULTILINE))


def _distinct_session_ids(text: str) -> set[str]:
    """Extract every `- session: <id>` value from a dispatch-log body."""
    return set(re.findall(r"^- session:\s+`?([^`\s]+)`?", text, flags=re.MULTILINE))


# ---------------------------------------------------------------------------
# Library helpers
# ---------------------------------------------------------------------------


class ReadVerifierOutputTests(unittest.TestCase):
    def test_returns_none_when_no_block(self) -> None:
        self.assertIsNone(read_latest_verifier_output("# just a heading\n"))

    def test_returns_last_block_when_multiple(self) -> None:
        # The schema's §Location pin: consumers parse the LAST block.
        text = (
            "# ticket\n\n"
            + _verifier_block("fail")
            + "\nfollow-up notes\n\n"
            + _verifier_block("pass")
        )
        parsed = read_latest_verifier_output(text)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["decision"], "pass")  # type: ignore[index]

    def test_unmatched_open_returns_none(self) -> None:
        text = "<!-- argos:verifier-output -->\nincomplete"
        self.assertIsNone(read_latest_verifier_output(text))


class ComposeRetrySessionIdTests(unittest.TestCase):
    def test_shape_and_slug_conformance(self) -> None:
        original = "batch-20260503T120000Z-abcd-ARG1-099"
        retry_id = compose_retry_session_id(original)
        self.assertEqual(retry_id, original + "-retry-1")
        # dispatch_log session-id slug: ^[A-Za-z0-9._:T-]+$
        self.assertRegex(retry_id, r"^[A-Za-z0-9._:T-]+$")

    def test_empty_rejected(self) -> None:
        with self.assertRaises(ValueError):
            compose_retry_session_id("")


class ReadDecisionTests(unittest.TestCase):
    def test_no_ticket_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(
                read_decision(
                    worktree_path=Path(td),
                    ticket_id="ARG1-099",
                )
            )

    def test_no_verifier_block_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            wt = Path(td)
            base = wt / DEFAULT_TICKET_DIR_IN_WORKTREE
            base.mkdir(parents=True)
            (base / "ARG1-099-fixture.md").write_text(
                "# no block here\n", encoding="utf-8"
            )
            self.assertIsNone(
                read_decision(worktree_path=wt, ticket_id="ARG1-099")
            )

    def test_returns_pass(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            wt = Path(td)
            _append_verifier_block_to_ticket(wt, "ARG1-099", "pass")
            self.assertEqual(
                read_decision(worktree_path=wt, ticket_id="ARG1-099"),
                "pass",
            )


# ---------------------------------------------------------------------------
# maybe_retry decision tree
# ---------------------------------------------------------------------------


class MaybeRetryTests(unittest.TestCase):
    """Direct tests of the retry decision function."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name)
        self.worktree = self.repo_root / "wt"
        self.worktree.mkdir()
        self.dispatch_root = self.repo_root / "dispatch"
        self.dispatch_root.mkdir()
        self.escalation_dir = self.repo_root / "escalations"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write_dispatch_log(self, ticket_id: str, session_id: str) -> Path:
        from argos.cli import dispatch_log

        path = dispatch_log.write_dispatch_log(
            ticket_id=ticket_id,
            epic_id="EPIC-T013",
            batch_id="batch-test-013",
            worktree_path=str(self.worktree),
            session_id=session_id,
            dispatch_root=self.dispatch_root,
            dispatched_at=datetime.now(timezone.utc),
        )
        return path

    def test_no_verifier_output_no_action(self) -> None:
        req = _make_request(ticket_id="ARG1-770", worktree=self.worktree)
        log_path = self._write_dispatch_log(req.ticket_id, req.session_id)
        config = RetryConfig(enabled=True, escalation_dir=self.escalation_dir)
        outcome = maybe_retry(
            req=req,
            initial_returncode=0,
            dispatch_file=log_path,
            config=config,
            retry_runner=lambda r: 0,
        )
        self.assertFalse(outcome.retried)
        self.assertIsNone(outcome.final_decision)
        self.assertIsNone(outcome.escalation_path)

    def test_pass_no_retry_no_escalation(self) -> None:
        req = _make_request(ticket_id="ARG1-771", worktree=self.worktree)
        _append_verifier_block_to_ticket(self.worktree, req.ticket_id, "pass")
        log_path = self._write_dispatch_log(req.ticket_id, req.session_id)
        config = RetryConfig(enabled=True, escalation_dir=self.escalation_dir)

        called = {"count": 0}

        def runner(_r: SessionRequest) -> int:
            called["count"] += 1
            return 0

        outcome = maybe_retry(
            req=req,
            initial_returncode=0,
            dispatch_file=log_path,
            config=config,
            retry_runner=runner,
        )
        self.assertFalse(outcome.retried)
        self.assertEqual(outcome.final_decision, "pass")
        self.assertIsNone(outcome.escalation_path)
        self.assertEqual(called["count"], 0)

    def test_pass_with_minors_no_retry_no_escalation(self) -> None:
        # AC#4 (library form).
        req = _make_request(ticket_id="ARG1-772", worktree=self.worktree)
        _append_verifier_block_to_ticket(
            self.worktree, req.ticket_id, "pass-with-minors"
        )
        log_path = self._write_dispatch_log(req.ticket_id, req.session_id)
        config = RetryConfig(enabled=True, escalation_dir=self.escalation_dir)

        outcome = maybe_retry(
            req=req,
            initial_returncode=0,
            dispatch_file=log_path,
            config=config,
            retry_runner=lambda r: 0,
        )
        self.assertFalse(outcome.retried)
        self.assertEqual(outcome.final_decision, "pass-with-minors")
        self.assertIsNone(outcome.escalation_path)

    def test_fail_with_retry_disabled_escalates_immediately(self) -> None:
        # AC#5 (library form).
        req = _make_request(ticket_id="ARG1-773", worktree=self.worktree)
        _append_verifier_block_to_ticket(self.worktree, req.ticket_id, "fail")
        log_path = self._write_dispatch_log(req.ticket_id, req.session_id)
        config = RetryConfig(enabled=False, escalation_dir=self.escalation_dir)

        called = {"count": 0}

        def runner(_r: SessionRequest) -> int:
            called["count"] += 1
            return 0

        outcome = maybe_retry(
            req=req,
            initial_returncode=1,
            dispatch_file=log_path,
            config=config,
            retry_runner=runner,
        )
        self.assertFalse(outcome.retried)
        self.assertEqual(outcome.final_decision, "fail")
        self.assertEqual(called["count"], 0)
        self.assertIsNotNone(outcome.escalation_path)
        # File written with severity: blocking and raised_by: orchestrator.
        body = outcome.escalation_path.read_text(encoding="utf-8")
        self.assertIn("severity: blocking", body)
        self.assertIn("raised_by: orchestrator", body)
        self.assertIn("ARG1-773", body)

    def test_fail_then_pass_on_retry_no_escalation(self) -> None:
        # AC#2 (library form).
        req = _make_request(ticket_id="ARG1-774", worktree=self.worktree)
        _append_verifier_block_to_ticket(self.worktree, req.ticket_id, "fail")
        log_path = self._write_dispatch_log(req.ticket_id, req.session_id)
        config = RetryConfig(enabled=True, escalation_dir=self.escalation_dir)

        def passing_retry(retry_req: SessionRequest) -> int:
            # Retry overwrites the verifier-output block with a `pass`.
            base = self.worktree / DEFAULT_TICKET_DIR_IN_WORKTREE
            path = next(base.glob(f"{retry_req.ticket_id}*.md"))
            existing = path.read_text(encoding="utf-8")
            existing += "\n\n## Verification (retry)\n\n"
            existing += _verifier_block("pass")
            path.write_text(existing, encoding="utf-8")
            return 0

        outcome = maybe_retry(
            req=req,
            initial_returncode=1,
            dispatch_file=log_path,
            config=config,
            retry_runner=passing_retry,
        )
        self.assertTrue(outcome.retried)
        self.assertEqual(outcome.final_decision, "pass")
        self.assertEqual(outcome.final_returncode, 0)
        self.assertIsNone(outcome.escalation_path)
        # Dispatch log has the retry event with the new session id.
        log_text = log_path.read_text(encoding="utf-8")
        self.assertIn("type=retry", log_text)
        self.assertIn(compose_retry_session_id(req.session_id), log_text)

    def test_fail_twice_writes_one_escalation(self) -> None:
        # AC#3 (library form).
        req = _make_request(ticket_id="ARG1-775", worktree=self.worktree)
        _append_verifier_block_to_ticket(self.worktree, req.ticket_id, "fail")
        log_path = self._write_dispatch_log(req.ticket_id, req.session_id)
        config = RetryConfig(enabled=True, escalation_dir=self.escalation_dir)

        retry_calls = {"count": 0}

        def failing_retry(retry_req: SessionRequest) -> int:
            retry_calls["count"] += 1
            base = self.worktree / DEFAULT_TICKET_DIR_IN_WORKTREE
            path = next(base.glob(f"{retry_req.ticket_id}*.md"))
            existing = path.read_text(encoding="utf-8")
            existing += "\n\n## Verification (retry)\n\n"
            existing += _verifier_block("fail")
            path.write_text(existing, encoding="utf-8")
            return 1

        outcome = maybe_retry(
            req=req,
            initial_returncode=1,
            dispatch_file=log_path,
            config=config,
            retry_runner=failing_retry,
        )
        self.assertTrue(outcome.retried)
        self.assertEqual(outcome.final_decision, "fail")
        self.assertIsNotNone(outcome.escalation_path)
        # Exactly one escalation file.
        files = list(self.escalation_dir.glob("ARG1-775-*.md"))
        self.assertEqual(len(files), 1)
        # Exactly one retry call (cap-1).
        self.assertEqual(retry_calls["count"], 1)


# ---------------------------------------------------------------------------
# End-to-end through dispatch_batch
# ---------------------------------------------------------------------------


class _ScriptedSessionRunner:
    """A SessionRunner that writes pre-scripted verifier blocks per attempt.

    Each ticket has a list of decisions (one per attempt). On call N, the
    runner writes the Nth decision into the worktree's ticket file and
    returns the matching returncode (0 for pass / pass-with-minors,
    1 for fail).
    """

    def __init__(self, decisions: dict[str, list[str]]) -> None:
        self._decisions = decisions
        self._calls: dict[str, int] = {tid: 0 for tid in decisions}
        self._lock = threading.Lock()
        # Pre-create worktree ticket files when the runner is invoked
        # so the verifier-output reader has somewhere to scan.
        self.invocations: list[str] = []

    def __call__(self, req: SessionRequest) -> int:
        with self._lock:
            attempt = self._calls.get(req.ticket_id, 0)
            self._calls[req.ticket_id] = attempt + 1
            self.invocations.append(req.session_id)
        decisions = self._decisions.get(req.ticket_id, [])
        if attempt >= len(decisions):
            return 0
        decision = decisions[attempt]
        # Make sure the worktree exists before writing into it; the
        # production runner (run-session) creates it, but the test
        # bypasses run-session entirely.
        req.worktree_path.mkdir(parents=True, exist_ok=True)
        _append_verifier_block_to_ticket(
            req.worktree_path, req.ticket_id, decision
        )
        return 0 if decision in ("pass", "pass-with-minors") else 1


def _bootstrap_dispatch_repo(repo_root: Path) -> tuple[Path, Path]:
    """Create the ticket dir + dispatch dir for a synthetic dispatch test.

    Independence detection consumes ``ticket_dir`` (the source-of-truth
    ticket files) directly, so we write a Plan-bearing fixture there.
    The dispatcher's ``dispatch_root`` and worktree paths are derived
    from ``repo_root``.
    """
    ticket_dir = repo_root / "tickets"
    dispatch_root = repo_root / "argos" / "specs" / "dispatch"
    ticket_dir.mkdir(parents=True, exist_ok=True)
    return ticket_dir, dispatch_root


class DispatchBatchRetryEndToEndTests(unittest.TestCase):
    """End-to-end tests through ``dispatch_batch`` with a scripted runner."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name)
        self.short_sha = "abc1234"
        self.ticket_dir, self.dispatch_root = _bootstrap_dispatch_repo(
            self.repo_root
        )
        self.escalation_dir = self.repo_root / "argos" / "specs" / "escalations"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _read_dispatch_log(self, ticket_id: str) -> str:
        path = self.dispatch_root / "EPIC-T013" / f"{ticket_id}.md"
        return path.read_text(encoding="utf-8")

    def test_ac1_critical_fail_triggers_retry_two_session_ids(self) -> None:
        # AC#1.
        tid = "ARG1-781"
        _write_ticket_in_dir(self.ticket_dir, tid)
        runner = _ScriptedSessionRunner({tid: ["fail", "fail"]})
        result = dispatch_batch(
            [tid],
            epic_id="EPIC-T013",
            batch_id="batch-test-013",
            max_parallel=1,
            repo_root=self.repo_root,
            dispatch_root=self.dispatch_root,
            ticket_dir=self.ticket_dir,
            short_sha=self.short_sha,
            info_stream=io.StringIO(),
            session_runner=runner,
            auto_fix_retries=1,
            retry_runner=runner,
            escalation_dir=self.escalation_dir,
        )
        log_text = self._read_dispatch_log(tid)
        # Two distinct session ids: the original and the retry id.
        ids = _distinct_session_ids(log_text)
        self.assertEqual(len(ids), 2, msg=f"got session ids: {ids}")
        # The runner saw two invocations.
        self.assertEqual(len(runner.invocations), 2)
        # The retry session id has the canonical -retry-1 suffix.
        retry_ids = [i for i in ids if i.endswith("-retry-1")]
        self.assertEqual(len(retry_ids), 1)
        # Result outcomes still come back per ticket.
        self.assertEqual(len(result.outcomes), 1)

    def test_ac2_fail_then_pass_no_escalation(self) -> None:
        # AC#2.
        tid = "ARG1-782"
        _write_ticket_in_dir(self.ticket_dir, tid)
        runner = _ScriptedSessionRunner({tid: ["fail", "pass"]})
        dispatch_batch(
            [tid],
            epic_id="EPIC-T013",
            batch_id="batch-test-013",
            max_parallel=1,
            repo_root=self.repo_root,
            dispatch_root=self.dispatch_root,
            ticket_dir=self.ticket_dir,
            short_sha=self.short_sha,
            info_stream=io.StringIO(),
            session_runner=runner,
            auto_fix_retries=1,
            retry_runner=runner,
            escalation_dir=self.escalation_dir,
        )
        log_text = self._read_dispatch_log(tid)
        # Final entry: decision: pass.
        self.assertIn("decision: pass", log_text)
        # No escalation file written.
        if self.escalation_dir.exists():
            files = list(self.escalation_dir.glob(f"{tid}-*.md"))
            self.assertEqual(files, [], msg=f"unexpected escalations: {files}")

    def test_ac3_fail_twice_one_escalation_two_session_ids(self) -> None:
        # AC#3.
        tid = "ARG1-783"
        _write_ticket_in_dir(self.ticket_dir, tid)
        runner = _ScriptedSessionRunner({tid: ["fail", "fail"]})
        dispatch_batch(
            [tid],
            epic_id="EPIC-T013",
            batch_id="batch-test-013",
            max_parallel=1,
            repo_root=self.repo_root,
            dispatch_root=self.dispatch_root,
            ticket_dir=self.ticket_dir,
            short_sha=self.short_sha,
            info_stream=io.StringIO(),
            session_runner=runner,
            auto_fix_retries=1,
            retry_runner=runner,
            escalation_dir=self.escalation_dir,
        )
        log_text = self._read_dispatch_log(tid)
        ids = _distinct_session_ids(log_text)
        self.assertEqual(len(ids), 2)
        # Exactly one escalation file with severity blocking.
        files = list(self.escalation_dir.glob(f"{tid}-*.md"))
        self.assertEqual(len(files), 1, msg=f"got: {files}")
        body = files[0].read_text(encoding="utf-8")
        self.assertIn("severity: blocking", body)
        self.assertIn(f"ticket_id: {tid}", body)
        # Cap-1 enforced — exactly two runner invocations, no third.
        self.assertEqual(len(runner.invocations), 2)

    def test_ac4_pass_with_minors_no_retry_one_session_id(self) -> None:
        # AC#4.
        tid = "ARG1-784"
        _write_ticket_in_dir(self.ticket_dir, tid)
        runner = _ScriptedSessionRunner({tid: ["pass-with-minors"]})
        dispatch_batch(
            [tid],
            epic_id="EPIC-T013",
            batch_id="batch-test-013",
            max_parallel=1,
            repo_root=self.repo_root,
            dispatch_root=self.dispatch_root,
            ticket_dir=self.ticket_dir,
            short_sha=self.short_sha,
            info_stream=io.StringIO(),
            session_runner=runner,
            auto_fix_retries=1,
            retry_runner=runner,
            escalation_dir=self.escalation_dir,
        )
        log_text = self._read_dispatch_log(tid)
        ids = _distinct_session_ids(log_text)
        self.assertEqual(len(ids), 1)
        # The verified-with-minors decision surfaces in the log entry.
        self.assertIn("decision: pass-with-minors", log_text)
        # The retry runner was never invoked beyond the first attempt.
        self.assertEqual(len(runner.invocations), 1)
        # No escalation written.
        if self.escalation_dir.exists():
            files = list(self.escalation_dir.glob(f"{tid}-*.md"))
            self.assertEqual(files, [])

    def test_ac5_disabled_retry_escalates_immediately(self) -> None:
        # AC#5: verifier.auto_fix_retries = 0 disables retry; first fail
        # produces an escalation immediately and the dispatch log has
        # exactly one session id.
        tid = "ARG1-785"
        _write_ticket_in_dir(self.ticket_dir, tid)
        runner = _ScriptedSessionRunner({tid: ["fail"]})
        dispatch_batch(
            [tid],
            epic_id="EPIC-T013",
            batch_id="batch-test-013",
            max_parallel=1,
            repo_root=self.repo_root,
            dispatch_root=self.dispatch_root,
            ticket_dir=self.ticket_dir,
            short_sha=self.short_sha,
            info_stream=io.StringIO(),
            session_runner=runner,
            auto_fix_retries=0,  # disabled
            retry_runner=runner,
            escalation_dir=self.escalation_dir,
        )
        log_text = self._read_dispatch_log(tid)
        ids = _distinct_session_ids(log_text)
        self.assertEqual(len(ids), 1, msg=f"got: {ids}")
        # No retry event.
        self.assertNotIn("type=retry", log_text)
        # Escalation written immediately.
        files = list(self.escalation_dir.glob(f"{tid}-*.md"))
        self.assertEqual(len(files), 1)
        body = files[0].read_text(encoding="utf-8")
        self.assertIn("severity: blocking", body)
        self.assertIn("raised_by: orchestrator", body)
        # Runner invoked exactly once.
        self.assertEqual(len(runner.invocations), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
