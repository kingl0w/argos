"""Tests for ARG1-069 ``spawn_session`` headless invocation.

A stub harness binary records the argv it was called with to a file; the
tests assert ``spawn_session`` invokes it as
``binary -p "<prompt>" --allow-dangerously-skip-permissions`` and that the
auto-built prompt carries the ticket. No live ``claude``. ADR-001 / ADR-002:
stdlib only.

Runnable as::

    python3 -m unittest argos.cli.tests.test_spawn_session -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli.orchestrator import session_prompt  # noqa: E402
from argos.cli.worktree import (  # noqa: E402
    TICKET_SUBDIR_IN_WORKTREE,
    spawn_session,
)


_FIXTURE_TICKET = """\
---
id: ARG1-099
title: A fixture ticket
files_touched: [argos/cli/example.py]
---

## Acceptance criteria

- [ ] AC#1: the widget frobnicates the sprocket.
"""


def _make_argv_recorder(tmp: Path) -> tuple[Path, Path]:
    """Write a stub harness that NUL-delimits its argv to a sidecar file.

    Returns ``(script_path, record_path)``. NUL delimiting keeps the prompt
    (which contains newlines) recoverable as a single argument.
    """
    record = tmp / "argv.out"
    script = tmp / "harness.sh"
    # `printf '%s\\0' "$@"` writes each arg followed by a NUL byte.
    script.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\0" "$@" > "{record}"\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script, record


def _read_argv(record: Path) -> list[str]:
    raw = record.read_bytes()
    parts = raw.split(b"\x00")
    # Trailing NUL produces a final empty element; drop it.
    if parts and parts[-1] == b"":
        parts = parts[:-1]
    return [p.decode("utf-8") for p in parts]


class SpawnSessionArgvTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.worktree = Path(self._tmp.name).resolve()
        self.ticket_dir = self.worktree / TICKET_SUBDIR_IN_WORKTREE
        self.ticket_dir.mkdir(parents=True)
        (self.ticket_dir / "ARG1-099-fixture.md").write_text(
            _FIXTURE_TICKET, encoding="utf-8"
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_invokes_headless_with_prompt(self) -> None:
        script, record = _make_argv_recorder(self.worktree)
        rc = spawn_session(
            str(script),
            self.worktree,
            ticket="ARG1-099",
            epic="EPIC-001",
        )
        self.assertEqual(rc, 0)
        argv = _read_argv(record)
        # Exact argv shape from AC#2: [-p, <prompt>, <permission flag>].
        self.assertEqual(argv[0], "-p")
        self.assertEqual(argv[2], session_prompt.DEFAULT_PERMISSION_ARG)
        prompt = argv[1]
        self.assertIn("ARG1-099", prompt)
        self.assertIn("the widget frobnicates the sprocket", prompt)
        for rule in session_prompt.STANDING_RULES:
            self.assertIn(rule, prompt)

    def test_exports_context_env(self) -> None:
        script = self.worktree / "harness.sh"
        record = self.worktree / "env.out"
        script.write_text(
            "#!/bin/sh\n"
            f'printf "cwd=%s\\n" "$(pwd)" > "{record}"\n'
            f'printf "ticket=%s\\n" "$ARGOS_TICKET" >> "{record}"\n'
            f'printf "epic=%s\\n" "$ARGOS_EPIC" >> "{record}"\n'
            f'printf "worktree=%s\\n" "$ARGOS_WORKTREE" >> "{record}"\n',
            encoding="utf-8",
        )
        script.chmod(0o755)
        rc = spawn_session(
            str(script),
            self.worktree,
            ticket="ARG1-099",
            epic="EPIC-001",
        )
        self.assertEqual(rc, 0)
        recorded = dict(
            line.split("=", 1)
            for line in record.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        self.assertEqual(recorded["cwd"], str(self.worktree))
        self.assertEqual(recorded["ticket"], "ARG1-099")
        self.assertEqual(recorded["epic"], "EPIC-001")
        self.assertEqual(recorded["worktree"], str(self.worktree))

    def test_returns_child_exit_code(self) -> None:
        script = self.worktree / "fail.sh"
        script.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
        script.chmod(0o755)
        rc = spawn_session(
            str(script),
            self.worktree,
            ticket="ARG1-099",
            epic="EPIC-001",
        )
        self.assertEqual(rc, 7)

    def test_missing_ticket_file_still_spawns(self) -> None:
        # A worktree with no ticket file (the ARG1-020 test-repo case): the
        # prompt degrades but the harness is still invoked headlessly.
        bare = Path(self._tmp.name).resolve() / "bare"
        bare.mkdir()
        script, record = _make_argv_recorder(bare)
        rc = spawn_session(
            str(script),
            bare,
            ticket="ARG1-099",
            epic="EPIC-001",
        )
        self.assertEqual(rc, 0)
        argv = _read_argv(record)
        self.assertEqual(argv[0], "-p")
        self.assertEqual(argv[2], session_prompt.DEFAULT_PERMISSION_ARG)
        self.assertIn("ARG1-099", argv[1])

    def test_custom_permission_arg(self) -> None:
        script, record = _make_argv_recorder(self.worktree)
        rc = spawn_session(
            str(script),
            self.worktree,
            ticket="ARG1-099",
            epic="EPIC-001",
            permission_arg="--permission-mode=plan",
        )
        self.assertEqual(rc, 0)
        argv = _read_argv(record)
        self.assertEqual(argv[2], "--permission-mode=plan")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
