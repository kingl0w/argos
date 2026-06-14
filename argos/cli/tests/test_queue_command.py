"""Tests for ``argos queue`` (ARG1-078 part B).

Covers add / remove / idempotency / non-present no-op, round-trip through the
queue parser, edit-only behavior, and resolver-driven path detection on a flat
(``init``-scaffolded) repo with no --state-file flag.
"""

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

from argos.cli.commands import queue as queue_cmd
from argos.cli.queue import parse_queue

_SEED = """\
# Argos — State

## Queue

- ARG1-100 existing queued ticket

## In progress

- [ ] _none_

## Done this cycle

- _none yet_
"""

_SEED_EMPTY_QUEUE = """\
# Argos — State

## Queue

## In progress

- [ ] _none_
"""


def _run(argv):
    """Invoke queue.main(argv), returning (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    saved_out, saved_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = queue_cmd.main(argv)
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err
    return code, out.getvalue(), err.getvalue()


class QueueCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.state = self.root / "argos" / "specs" / "STATE.md"
        self.state.parent.mkdir(parents=True)
        self.state.write_text(_SEED, encoding="utf-8")
        self.addCleanup(self._tmp.cleanup)

    def _queue_ids(self) -> list:
        return parse_queue(self.state.read_text(encoding="utf-8"))

    def test_add_appends_and_roundtrips(self) -> None:
        code, out, _ = _run(["add", "ARG1-099", "--state-file", str(self.state)])
        self.assertEqual(code, 0)
        self.assertIn("queued ARG1-099", out)
        ids = self._queue_ids()
        self.assertIn("ARG1-099", ids)
        self.assertEqual(ids, ["ARG1-100", "ARG1-099"])  # appended after existing

    def test_add_is_idempotent(self) -> None:
        _run(["add", "ARG1-099", "--state-file", str(self.state)])
        code, out, _ = _run(["add", "ARG1-099", "--state-file", str(self.state)])
        self.assertEqual(code, 0)
        self.assertIn("already in queue", out)
        # Exactly one occurrence — no duplicate bullet.
        self.assertEqual(self._queue_ids().count("ARG1-099"), 1)

    def test_remove_present(self) -> None:
        code, out, _ = _run(["remove", "ARG1-100", "--state-file", str(self.state)])
        self.assertEqual(code, 0)
        self.assertIn("removed ARG1-100", out)
        self.assertNotIn("ARG1-100", self._queue_ids())

    def test_remove_absent_is_noop(self) -> None:
        before = self.state.read_text(encoding="utf-8")
        code, out, _ = _run(["remove", "ARG1-555", "--state-file", str(self.state)])
        self.assertEqual(code, 0)
        self.assertIn("not in queue", out)
        # No-op: file content unchanged.
        self.assertEqual(self.state.read_text(encoding="utf-8"), before)

    def test_add_into_empty_queue(self) -> None:
        self.state.write_text(_SEED_EMPTY_QUEUE, encoding="utf-8")
        code, _, _ = _run(["add", "ARG1-001", "--state-file", str(self.state)])
        self.assertEqual(code, 0)
        self.assertEqual(self._queue_ids(), ["ARG1-001"])
        # The In-progress section is untouched.
        self.assertIn("## In progress", self.state.read_text(encoding="utf-8"))

    def test_invalid_ticket_id_rejected(self) -> None:
        code, _, err = _run(["add", "not-a-ticket", "--state-file", str(self.state)])
        self.assertEqual(code, 2)
        self.assertIn("not a ticket id", err)

    def test_missing_state_file(self) -> None:
        missing = self.root / "nope" / "STATE.md"
        code, _, err = _run(["add", "ARG1-099", "--state-file", str(missing)])
        self.assertEqual(code, 1)
        self.assertIn("STATE.md not found", err)


class QueueResolverFlatRepoTests(unittest.TestCase):
    def test_resolves_flat_repo_state_with_no_flag(self) -> None:
        # A flat init-scaffolded repo: argos/specs/STATE.md, no v1.0/ tree.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "argos" / "specs" / "STATE.md"
            state.parent.mkdir(parents=True)
            state.write_text(_SEED, encoding="utf-8")
            cwd = os.getcwd()
            os.chdir(root)
            try:
                code, out, _ = _run(["add", "ARG1-077"])  # no --state-file
            finally:
                os.chdir(cwd)
            self.assertEqual(code, 0)
            self.assertIn("queued ARG1-077", out)
            self.assertIn("ARG1-077", parse_queue(state.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
