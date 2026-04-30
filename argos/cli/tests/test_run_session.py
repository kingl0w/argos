"""Tests for ARG1-020 ``argos run-session`` (worktree spawn helper).

Each test that exercises ``git worktree add`` runs in a freshly-initialized
temporary git repo so the worktree state is fully hermetic and the in-repo
``.argos/worktrees/`` directory is never polluted. ADR-001 / ADR-002:
stdlib only, no third-party imports.

Runnable as::

    python3 -m unittest argos.cli.tests.test_run_session -v
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli.worktree import (  # noqa: E402
    BRANCH_PREFIX,
    HARNESS_ENV_VAR,
    InvalidWorktreePathError,
    compute_branch_name,
    validate_worktree_path,
)

_ARGOS_BIN = Path(__file__).resolve().parents[1] / "argos"


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _init_repo(root: Path) -> None:
    """Initialize a minimal git repo with one commit so worktree add works."""
    _git("init", "-q", "-b", "main", cwd=root)
    _git("config", "user.email", "test@example.com", cwd=root)
    _git("config", "user.name", "test", cwd=root)
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git("add", "seed.txt", cwd=root)
    _git("commit", "-q", "-m", "seed", cwd=root)


def _harness_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Env that points the run-session harness at /bin/true so spawns succeed."""
    env = os.environ.copy()
    env[HARNESS_ENV_VAR] = "/bin/true"
    if extra:
        env.update(extra)
    return env


def _run_cli(
    *args: str,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_ARGOS_BIN), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd),
        env=env if env is not None else _harness_env(),
    )


class RunSessionLibraryTests(unittest.TestCase):
    """Pure-library checks that don't need a git repo."""

    def test_compute_branch_name_basic(self) -> None:
        self.assertEqual(compute_branch_name("ARG1-099"), "argos/ARG1-099")
        self.assertEqual(compute_branch_name("ARG1-099"), f"{BRANCH_PREFIX}/ARG1-099")

    def test_compute_branch_name_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            compute_branch_name("")

    def test_compute_branch_name_rejects_slash(self) -> None:
        with self.assertRaises(ValueError):
            compute_branch_name("ARG1/099")

    def test_validate_worktree_path_accepts_under_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            target = root / ".argos" / "worktrees" / "ARG1-099"
            out = validate_worktree_path(root, str(target))
            self.assertEqual(out, target.resolve())

    def test_validate_worktree_path_rejects_outside(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            with self.assertRaises(InvalidWorktreePathError):
                validate_worktree_path(root, "/tmp/foo")

    def test_validate_worktree_path_rejects_root_itself(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            with self.assertRaises(InvalidWorktreePathError):
                validate_worktree_path(root, str(root / ".argos" / "worktrees"))

    def test_validate_worktree_path_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            attack = root / ".argos" / "worktrees" / ".." / ".." / "etc"
            with self.assertRaises(InvalidWorktreePathError):
                validate_worktree_path(root, str(attack))


class RunSessionCLITests(unittest.TestCase):
    """End-to-end CLI tests covering ARG1-020 acceptance criteria."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name).resolve()
        _init_repo(self.repo)

    def tearDown(self) -> None:
        # Prune any leftover worktrees so TemporaryDirectory cleanup succeeds
        # even on systems where git's worktree links keep file handles.
        _git("worktree", "prune", cwd=self.repo)
        self._tmp.cleanup()

    # -------- AC#1 --------

    def test_dry_run_prints_branch_and_absolute_path(self) -> None:
        result = _run_cli(
            "run-session",
            "--ticket", "ARG1-099",
            "--worktree", ".argos/worktrees/ARG1-099-test",
            "--epic", "EPIC-001",
            "--dry-run",
            cwd=self.repo,
        )
        self.assertEqual(result.returncode, 0, f"stderr={result.stderr!r}")
        self.assertIn("argos/ARG1-099", result.stdout)
        expected_path = str((self.repo / ".argos" / "worktrees" / "ARG1-099-test").resolve())
        self.assertIn(expected_path, result.stdout)

    def test_dry_run_does_not_create_worktree(self) -> None:
        result = _run_cli(
            "run-session",
            "--ticket", "ARG1-099",
            "--worktree", ".argos/worktrees/ARG1-099-test",
            "--epic", "EPIC-001",
            "--dry-run",
            cwd=self.repo,
        )
        self.assertEqual(result.returncode, 0)
        self.assertFalse(
            (self.repo / ".argos" / "worktrees" / "ARG1-099-test").exists(),
            "dry-run created the worktree directory",
        )
        listed = _git("worktree", "list", "--porcelain", cwd=self.repo)
        self.assertNotIn("ARG1-099-test", listed.stdout)

    # -------- AC#2 --------

    def test_real_run_creates_worktree_with_branch(self) -> None:
        result = _run_cli(
            "run-session",
            "--ticket", "ARG1-099",
            "--worktree", ".argos/worktrees/ARG1-099-test",
            "--epic", "EPIC-001",
            cwd=self.repo,
        )
        self.assertEqual(result.returncode, 0, f"stderr={result.stderr!r}")
        listed = _git("worktree", "list", "--porcelain", cwd=self.repo)
        self.assertIn("ARG1-099-test", listed.stdout)
        # Branch named per the architecture invariant.
        branches = _git("branch", "--list", "argos/ARG1-099", cwd=self.repo)
        self.assertIn("argos/ARG1-099", branches.stdout)

    # -------- AC#3 --------

    def test_session_exit_preserves_worktree(self) -> None:
        result = _run_cli(
            "run-session",
            "--ticket", "ARG1-099",
            "--worktree", ".argos/worktrees/ARG1-099-test",
            "--epic", "EPIC-001",
            cwd=self.repo,
        )
        self.assertEqual(result.returncode, 0, f"stderr={result.stderr!r}")
        # No auto-cleanup — the directory must still be on disk after spawn.
        self.assertTrue(
            (self.repo / ".argos" / "worktrees" / "ARG1-099-test").is_dir(),
            "worktree was cleaned up after the session exited",
        )

    # -------- AC#4 --------

    def test_second_dispatch_for_same_ticket_rejected(self) -> None:
        first = _run_cli(
            "run-session",
            "--ticket", "ARG1-099",
            "--worktree", ".argos/worktrees/ARG1-099-test",
            "--epic", "EPIC-001",
            cwd=self.repo,
        )
        self.assertEqual(first.returncode, 0, f"stderr={first.stderr!r}")
        second = _run_cli(
            "run-session",
            "--ticket", "ARG1-099",
            "--worktree", ".argos/worktrees/ARG1-099-test",
            "--epic", "EPIC-001",
            cwd=self.repo,
        )
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("worktree already exists", second.stderr)

    def test_concurrent_dispatch_for_same_ticket_one_loses(self) -> None:
        results: list[subprocess.CompletedProcess] = []
        lock = threading.Lock()

        def run() -> None:
            r = _run_cli(
                "run-session",
                "--ticket", "ARG1-099",
                "--worktree", ".argos/worktrees/ARG1-099-test",
                "--epic", "EPIC-001",
                cwd=self.repo,
            )
            with lock:
                results.append(r)

        threads = [threading.Thread(target=run) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        codes = sorted(r.returncode for r in results)
        # Exactly one success; one rejection.
        self.assertEqual(codes[0], 0, f"no successful dispatch; results={[(r.returncode, r.stderr) for r in results]}")
        self.assertNotEqual(codes[1], 0, "both concurrent dispatches succeeded")
        loser = next(r for r in results if r.returncode != 0)
        self.assertIn("worktree already exists", loser.stderr)

    # -------- AC#5 --------

    def test_path_outside_worktrees_dir_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            result = _run_cli(
                "run-session",
                "--ticket", "ARG1-099",
                "--worktree", str(Path(outside) / "foo"),
                "--epic", "EPIC-001",
                cwd=self.repo,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("worktree must live under .argos/worktrees/", result.stderr)

    def test_relative_path_outside_argos_rejected(self) -> None:
        result = _run_cli(
            "run-session",
            "--ticket", "ARG1-099",
            "--worktree", "src/foo",
            "--epic", "EPIC-001",
            cwd=self.repo,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("worktree must live under .argos/worktrees/", result.stderr)

    # -------- AC#6 --------

    def test_debug_print_cwd_emits_absolute_worktree_path(self) -> None:
        result = _run_cli(
            "run-session",
            "--ticket", "ARG1-099",
            "--worktree", ".argos/worktrees/ARG1-099-test",
            "--epic", "EPIC-001",
            "--debug-print-cwd",
            cwd=self.repo,
        )
        self.assertEqual(result.returncode, 0, f"stderr={result.stderr!r}")
        expected = str((self.repo / ".argos" / "worktrees" / "ARG1-099-test").resolve())
        self.assertIn(expected, result.stdout)
        self.assertNotIn(str(self.repo) + "\n", result.stdout.split(expected)[0])

    def test_debug_print_cwd_creates_worktree(self) -> None:
        result = _run_cli(
            "run-session",
            "--ticket", "ARG1-099",
            "--worktree", ".argos/worktrees/ARG1-099-test",
            "--epic", "EPIC-001",
            "--debug-print-cwd",
            cwd=self.repo,
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(
            (self.repo / ".argos" / "worktrees" / "ARG1-099-test").is_dir()
        )

    # -------- defensive --------

    def test_missing_required_args_exits_nonzero(self) -> None:
        result = _run_cli(
            "run-session",
            "--ticket", "ARG1-099",
            cwd=self.repo,
        )
        self.assertNotEqual(result.returncode, 0)


class RunSessionEnvTests(unittest.TestCase):
    """The harness binary is invoked with cwd pinned and ARGOS_* env vars set."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name).resolve()
        _init_repo(self.repo)

    def tearDown(self) -> None:
        _git("worktree", "prune", cwd=self.repo)
        self._tmp.cleanup()

    def test_harness_sees_pinned_cwd_and_env(self) -> None:
        # Tiny harness script that records the env it was invoked with so
        # we can assert the spawn pinned cwd and exported ARGOS_* keys.
        script = self.repo / "harness.sh"
        record = self.repo / "harness.out"
        script.write_text(
            "#!/bin/sh\n"
            f'printf "cwd=%s\\n" "$(pwd)" > "{record}"\n'
            f'printf "ticket=%s\\n" "$ARGOS_TICKET" >> "{record}"\n'
            f'printf "epic=%s\\n" "$ARGOS_EPIC" >> "{record}"\n'
            f'printf "worktree=%s\\n" "$ARGOS_WORKTREE" >> "{record}"\n',
            encoding="utf-8",
        )
        script.chmod(0o755)

        env = os.environ.copy()
        env[HARNESS_ENV_VAR] = str(script)
        result = _run_cli(
            "run-session",
            "--ticket", "ARG1-099",
            "--worktree", ".argos/worktrees/ARG1-099-env",
            "--epic", "EPIC-001",
            cwd=self.repo,
            env=env,
        )
        self.assertEqual(result.returncode, 0, f"stderr={result.stderr!r}")
        self.assertTrue(record.exists(), "harness did not run")
        recorded = dict(
            line.split("=", 1)
            for line in record.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        expected_wt = str((self.repo / ".argos" / "worktrees" / "ARG1-099-env").resolve())
        self.assertEqual(recorded["cwd"], expected_wt)
        self.assertEqual(recorded["ticket"], "ARG1-099")
        self.assertEqual(recorded["epic"], "EPIC-001")
        self.assertEqual(recorded["worktree"], expected_wt)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
