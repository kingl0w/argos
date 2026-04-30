"""Tests for the ARG1-012 orchestrator dispatch log writer.

Covers all five acceptance criteria from
``argos/specs/v1.0/tickets/ARG1-012-dispatch-log-writer.md``. Stdlib only
(ADR-001 / ADR-002).

Runnable as::

    python3 -m unittest argos.cli.tests.test_dispatch_log -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

# argos/cli/tests/test_dispatch_log.py
#   parents[3] == repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli.dispatch_log import (  # noqa: E402
    DispatchLogExistsError,
    DispatchLogMissingError,
    EVENT_VERIFIER_RESULT,
    InvalidIdError,
    append_event,
    build_event_block,
    dispatch_log_path,
    write_dispatch_log,
)


_REQUIRED_FRONTMATTER_KEYS = (
    "ticket_id",
    "epic_id",
    "batch_id",
    "dispatched_at",
    "worktree_path",
    "session_id",
)


def _make_args(
    *,
    ticket: str = "ARG1-099",
    epic: str = "EPIC-001",
    batch: str = "batch-2026-04-30T10:00:00Z",
    worktree: str = ".argos/worktrees/ARG1-099-3f9c",
    session: str = "sess-2026-04-30T10:00:00Z-a1b2",
) -> dict:
    return {
        "ticket_id": ticket,
        "epic_id": epic,
        "batch_id": batch,
        "worktree_path": worktree,
        "session_id": session,
    }


class _DispatchTempBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dispatch_root = Path(self._tmp.name) / "dispatch"
        # Note: write_dispatch_log creates the parent dir; do NOT pre-create.

    def _t(self, h: int = 10, m: int = 0, s: int = 0) -> datetime:
        return datetime(2026, 4, 30, h, m, s, tzinfo=timezone.utc)


class TestCanonicalPath(_DispatchTempBase):
    """AC#1: file lands at argos/specs/dispatch/{epic}/{ticket}.md."""

    def test_writes_at_canonical_path(self) -> None:
        path = write_dispatch_log(
            **_make_args(),
            dispatch_root=self.dispatch_root,
            dispatched_at=self._t(),
        )
        expected = self.dispatch_root / "EPIC-001" / "ARG1-099.md"
        self.assertEqual(path, expected)
        self.assertTrue(path.is_file(), f"expected file at {path}")

    def test_path_helper_matches_writer(self) -> None:
        helper_path = dispatch_log_path(self.dispatch_root, "EPIC-001", "ARG1-099")
        writer_path = write_dispatch_log(
            **_make_args(),
            dispatch_root=self.dispatch_root,
            dispatched_at=self._t(),
        )
        self.assertEqual(helper_path, writer_path)


class TestFrontmatterShape(_DispatchTempBase):
    """AC#2: frontmatter has the six required keys, parseable via the AC harness."""

    def test_frontmatter_keys_via_argos_frontmatter_parse(self) -> None:
        path = write_dispatch_log(
            **_make_args(),
            dispatch_root=self.dispatch_root,
            dispatched_at=self._t(),
        )

        proc = subprocess.run(
            [sys.executable, "-m", "argos.cli", "frontmatter-parse", str(path)],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"frontmatter-parse failed:\nstdout={proc.stdout}\nstderr={proc.stderr}",
        )

        data = json.loads(proc.stdout)
        for key in _REQUIRED_FRONTMATTER_KEYS:
            self.assertIn(key, data, f"missing required frontmatter key: {key}")

        # Spot-check round-tripping of value shapes that contain colons /
        # path separators — these are the high-risk inputs for the
        # ADR-002 §3 bare-scalar grammar.
        self.assertEqual(data["ticket_id"], "ARG1-099")
        self.assertEqual(data["epic_id"], "EPIC-001")
        self.assertEqual(data["dispatched_at"], "2026-04-30T10:00:00Z")
        self.assertEqual(
            data["worktree_path"], ".argos/worktrees/ARG1-099-3f9c"
        )
        self.assertEqual(
            data["session_id"], "sess-2026-04-30T10:00:00Z-a1b2"
        )


class TestAppendPreservesFrontmatter(_DispatchTempBase):
    """AC#3: a second event grows the file; frontmatter is unchanged."""

    def test_size_grows_and_frontmatter_byte_equal(self) -> None:
        path = write_dispatch_log(
            **_make_args(),
            dispatch_root=self.dispatch_root,
            dispatched_at=self._t(),
        )
        size_before = path.stat().st_size
        text_before = path.read_text(encoding="utf-8")
        # Locate the frontmatter region: from BOF up to and including the
        # second '---' line + the trailing newline.
        head_idx = text_before.index("---")
        close_idx = text_before.index("---", head_idx + 3) + len("---") + 1
        fm_before = text_before[:close_idx]

        appended_block = append_event(
            dispatch_file=path,
            event_type=EVENT_VERIFIER_RESULT,
            body="- decision: pass\n- findings: 0 critical, 0 major, 0 minor",
            at=self._t(11, 0, 0),
        )

        size_after = path.stat().st_size
        text_after = path.read_text(encoding="utf-8")
        fm_after = text_after[:close_idx]

        self.assertGreater(
            size_after,
            size_before,
            f"file size did not grow: before={size_before} after={size_after}",
        )
        self.assertEqual(
            fm_before, fm_after, "frontmatter region was modified by append"
        )
        # The newly appended block must be present verbatim.
        self.assertIn(appended_block, text_after)
        self.assertIn("type=verifier-result", text_after)

    def test_many_appends_keep_frontmatter_byte_equal(self) -> None:
        path = write_dispatch_log(
            **_make_args(),
            dispatch_root=self.dispatch_root,
            dispatched_at=self._t(),
        )
        text_before = path.read_text(encoding="utf-8")
        head_idx = text_before.index("---")
        close_idx = text_before.index("---", head_idx + 3) + len("---") + 1
        fm_before = text_before[:close_idx]

        last_size = path.stat().st_size
        for i in range(5):
            append_event(
                dispatch_file=path,
                event_type="retry",
                body=f"- attempt: {i}",
                at=self._t(12 + i, 0, 0),
            )
            new_size = path.stat().st_size
            self.assertGreater(new_size, last_size)
            last_size = new_size

        text_after = path.read_text(encoding="utf-8")
        self.assertEqual(text_after[:close_idx], fm_before)


class TestDryRun(_DispatchTempBase):
    """AC#4: ``argos orchestrate --dry-run`` writes nothing.

    The literal AC text is verified at the writer boundary: when ``dry_run``
    is True, no file under ``dispatch_root`` is created. ARG1-011 wires the
    flag through; this test asserts the writer-side guarantee that flag
    propagation is sufficient.
    """

    def test_dry_run_creates_no_files(self) -> None:
        marker = Path(self._tmp.name) / "before-marker"
        marker.touch()
        before_mtime = marker.stat().st_mtime

        path = write_dispatch_log(
            **_make_args(),
            dispatch_root=self.dispatch_root,
            dispatched_at=self._t(),
            dry_run=True,
        )

        # Path is reported (callers may want to log it) but nothing on disk.
        self.assertEqual(path, self.dispatch_root / "EPIC-001" / "ARG1-099.md")
        self.assertFalse(self.dispatch_root.exists())
        self.assertFalse(path.exists())

        # Mirror the AC's `find ... -newer ...` discipline.
        if self.dispatch_root.exists():
            results = list(self.dispatch_root.rglob("*"))
            newer = [
                p for p in results if p.stat().st_mtime > before_mtime
            ]
            self.assertEqual(newer, [])

    def test_dry_run_append_returns_block_without_writing(self) -> None:
        # First make a real log so the path resolution has something to peek.
        path = write_dispatch_log(
            **_make_args(),
            dispatch_root=self.dispatch_root,
            dispatched_at=self._t(),
        )
        size_before = path.stat().st_size
        block = append_event(
            dispatch_file=path,
            event_type="merged",
            body="- decision: merged",
            at=self._t(13, 0, 0),
            dry_run=True,
        )
        self.assertIn("type=merged", block)
        self.assertIn("- decision: merged", block)
        # Disk untouched.
        self.assertEqual(path.stat().st_size, size_before)


class TestConcurrentDispatch(_DispatchTempBase):
    """AC#5: two concurrent dispatches to different tickets produce two files."""

    def test_two_concurrent_dispatches_two_files(self) -> None:
        ready = threading.Event()
        errors: list[BaseException] = []

        def _dispatch(ticket: str) -> None:
            try:
                ready.wait()
                write_dispatch_log(
                    **_make_args(ticket=ticket),
                    dispatch_root=self.dispatch_root,
                    dispatched_at=self._t(),
                )
            except BaseException as exc:  # pragma: no cover - assertion path
                errors.append(exc)

        t1 = threading.Thread(target=_dispatch, args=("ARG1-100",))
        t2 = threading.Thread(target=_dispatch, args=("ARG1-101",))
        t1.start()
        t2.start()
        ready.set()
        t1.join(timeout=5)
        t2.join(timeout=5)

        self.assertFalse(errors, f"concurrent dispatch errored: {errors}")

        f1 = self.dispatch_root / "EPIC-001" / "ARG1-100.md"
        f2 = self.dispatch_root / "EPIC-001" / "ARG1-101.md"
        self.assertTrue(f1.is_file())
        self.assertTrue(f2.is_file())
        self.assertNotEqual(
            f1.read_text(encoding="utf-8"),
            f2.read_text(encoding="utf-8"),
            "two concurrent dispatches produced identical files (collision)",
        )
        # Sanity: each frontmatter cites its own ticket id.
        self.assertIn("ticket_id: ARG1-100", f1.read_text(encoding="utf-8"))
        self.assertIn("ticket_id: ARG1-101", f2.read_text(encoding="utf-8"))


class TestExistsContract(_DispatchTempBase):
    """Initial write refuses to overwrite — second initial-write raises."""

    def test_second_initial_write_raises(self) -> None:
        write_dispatch_log(
            **_make_args(),
            dispatch_root=self.dispatch_root,
            dispatched_at=self._t(),
        )
        with self.assertRaises(DispatchLogExistsError):
            write_dispatch_log(
                **_make_args(),
                dispatch_root=self.dispatch_root,
                dispatched_at=self._t(11, 0, 0),
            )


class TestMissingContract(_DispatchTempBase):
    """append_event on a non-existent file raises DispatchLogMissingError."""

    def test_append_missing_raises(self) -> None:
        path = self.dispatch_root / "EPIC-001" / "ARG1-999.md"
        with self.assertRaises(DispatchLogMissingError):
            append_event(
                dispatch_file=path,
                event_type=EVENT_VERIFIER_RESULT,
                at=self._t(),
            )


class TestSlugValidation(_DispatchTempBase):
    """ticket_id, epic_id, event_type, session_id all slug-shape-validated."""

    def test_invalid_epic_id_rejected(self) -> None:
        with self.assertRaises(InvalidIdError):
            write_dispatch_log(
                **_make_args(epic="../etc/passwd"),
                dispatch_root=self.dispatch_root,
                dispatched_at=self._t(),
            )

    def test_invalid_ticket_id_rejected(self) -> None:
        with self.assertRaises(InvalidIdError):
            write_dispatch_log(
                **_make_args(ticket="ARG1/099"),
                dispatch_root=self.dispatch_root,
                dispatched_at=self._t(),
            )

    def test_invalid_event_type_rejected(self) -> None:
        path = write_dispatch_log(
            **_make_args(),
            dispatch_root=self.dispatch_root,
            dispatched_at=self._t(),
        )
        with self.assertRaises(InvalidIdError):
            append_event(
                dispatch_file=path,
                event_type="Verifier_Result",
                at=self._t(11, 0, 0),
            )

    def test_empty_session_id_rejected(self) -> None:
        with self.assertRaises(InvalidIdError):
            write_dispatch_log(
                **_make_args(session=""),
                dispatch_root=self.dispatch_root,
                dispatched_at=self._t(),
            )


class TestBlockIdUniqueness(_DispatchTempBase):
    """Same-second appends of the same event_type get distinct ids."""

    def test_same_second_appends_get_disambiguated(self) -> None:
        path = write_dispatch_log(
            **_make_args(),
            dispatch_root=self.dispatch_root,
            dispatched_at=self._t(),
        )
        b1 = append_event(
            dispatch_file=path,
            event_type="retry",
            body="- attempt: 0",
            at=self._t(11, 0, 0),
        )
        b2 = append_event(
            dispatch_file=path,
            event_type="retry",
            body="- attempt: 1",
            at=self._t(11, 0, 0),
        )
        self.assertNotEqual(b1, b2)
        text = path.read_text(encoding="utf-8")
        # Both blocks present.
        self.assertIn(b1, text)
        self.assertIn(b2, text)


class TestBuildEventBlockShape(unittest.TestCase):
    """Sanity check on the block string format consumed by parsers."""

    def test_block_has_open_and_close_tags(self) -> None:
        block = build_event_block(
            block_id="2026-04-30T10:00:00Z-ARG1-099-dispatched",
            event_type="dispatched",
            ticket_id="ARG1-099",
            at="2026-04-30T10:00:00Z",
            body="- worktree: x",
        )
        self.assertTrue(block.startswith("<!-- argos:dispatch-event"))
        self.assertIn(
            "id=2026-04-30T10:00:00Z-ARG1-099-dispatched", block
        )
        self.assertIn("type=dispatched", block)
        self.assertIn("ticket=ARG1-099", block)
        self.assertIn("at=2026-04-30T10:00:00Z", block)
        self.assertTrue(block.rstrip().endswith("<!-- /argos:dispatch-event -->"))


if __name__ == "__main__":
    unittest.main()
