"""Tests for ``argos init`` (ARG1-002).

Stdlib ``unittest`` only — no pytest (ADR-001 / ADR-002). Run from repo
root:

    python3 -m unittest argos.cli.tests.test_init -v

Each test scaffolds into a fresh ``tempfile.TemporaryDirectory`` and
invokes the CLI as a subprocess via the in-repo launcher
(``argos/cli/argos``), mirroring how the verifier runs the acceptance
criteria (``argos init`` from a fresh directory).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# argos/cli/tests/test_init.py
#   parents[0] = argos/cli/tests
#   parents[1] = argos/cli
#   parents[2] = argos
#   parents[3] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_LAUNCHER = _REPO_ROOT / "argos" / "cli" / "argos"

_GIT = shutil.which("git")


def _run_init(cwd: Path, *extra: str) -> subprocess.CompletedProcess:
    """Invoke ``argos init`` through the launcher with ``cwd`` as CWD."""
    return subprocess.run(
        [sys.executable, str(_LAUNCHER), "init", *extra],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


def _mtimes(root: Path, rels) -> dict:
    return {rel: (root / rel).stat().st_mtime_ns for rel in rels}


_SCAFFOLDED = (
    "argos/specs/STATE.md",
    "argos/specs/PRD.md",
    "argos/specs/ARCHITECTURE.md",
    "argos/config.toml",
    ".argos/local.toml",
)


class InitFreshTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_fresh_init_exit_zero_and_says_initialized(self) -> None:
        """AC#1: fresh init exits 0 and stdout contains ``initialized``."""
        proc = _run_init(self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("initialized", proc.stdout)

    def test_spec_files_exist(self) -> None:
        """AC#2: STATE.md, PRD.md, ARCHITECTURE.md all exist after init."""
        _run_init(self.root)
        for rel in ("argos/specs/STATE.md", "argos/specs/PRD.md",
                    "argos/specs/ARCHITECTURE.md"):
            self.assertTrue((self.root / rel).is_file(), rel)

    def test_config_files_exist(self) -> None:
        """AC#3: argos/config.toml and .argos/local.toml exist after init."""
        _run_init(self.root)
        self.assertTrue((self.root / "argos/config.toml").is_file())
        self.assertTrue((self.root / ".argos/local.toml").is_file())

    def test_conventions_scaffolded_and_rendered(self) -> None:
        """argos/conventions.md is scaffolded, names the project, no placeholders."""
        _run_init(self.root, "--name", "Acme", "--prefix", "ACME")
        conventions = self.root / "argos" / "conventions.md"
        self.assertTrue(conventions.is_file(), conventions)
        text = conventions.read_text(encoding="utf-8")
        self.assertIn("Acme", text)
        self.assertNotIn("{{", text)
        self.assertNotIn("}}", text)

    def test_gitignore_has_argos_entry(self) -> None:
        """AC#4: .gitignore contains the exact whole line ``.argos/``."""
        _run_init(self.root)
        gitignore = self.root / ".gitignore"
        self.assertTrue(gitignore.is_file())
        lines = gitignore.read_text(encoding="utf-8").splitlines()
        self.assertIn(".argos/", lines)

    @unittest.skipIf(_GIT is None, "git not available")
    def test_merge_driver_registered(self) -> None:
        """AC#5: git config merge.argos-state.driver is set and non-empty."""
        _run_init(self.root)
        proc = subprocess.run(
            [_GIT, "-C", str(self.root), "config", "--get",
             "merge.argos-state.driver"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.strip(), "driver value is empty")

    def test_templates_rendered_no_placeholders(self) -> None:
        """Rendered spec files carry no leftover {{...}} placeholders."""
        _run_init(self.root, "--name", "Acme", "--prefix", "ACME")
        for rel in ("argos/specs/STATE.md", "argos/specs/PRD.md",
                    "argos/specs/ARCHITECTURE.md"):
            text = (self.root / rel).read_text(encoding="utf-8")
            self.assertNotIn("{{", text, rel)
            self.assertNotIn("}}", text, rel)
        self.assertIn("Acme", (self.root / "argos/specs/STATE.md").read_text())


class InitIdempotencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_rerun_says_already_initialized_and_preserves_mtimes(self) -> None:
        """AC#6: re-run exits 0, says ``already initialized``, no mtime change."""
        first = _run_init(self.root)
        self.assertEqual(first.returncode, 0, first.stderr)
        before = _mtimes(self.root, _SCAFFOLDED)

        second = _run_init(self.root)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("already initialized", second.stdout)

        after = _mtimes(self.root, _SCAFFOLDED)
        self.assertEqual(before, after, "re-run must not touch scaffolded files")


class InitForceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_force_overwrites_but_preserves_tickets(self) -> None:
        """AC#7: --force rewrites scaffolded files but never touches tickets."""
        first = _run_init(self.root)
        self.assertEqual(first.returncode, 0, first.stderr)

        # Drop an operator-authored ticket into the tickets dir.
        ticket = self.root / "argos/specs/tickets/ACME-001.md"
        ticket.write_text("# ACME-001 — real ticket\n", encoding="utf-8")
        ticket_before_mtime = ticket.stat().st_mtime_ns
        ticket_before_text = ticket.read_text(encoding="utf-8")

        # Stamp every scaffolded file (and the ticket) to the epoch so any
        # rewrite is unambiguously detectable regardless of clock granularity.
        for rel in (*_SCAFFOLDED, "argos/specs/tickets/ACME-001.md"):
            os.utime(self.root / rel, ns=(0, 0))
        ticket_before_mtime = ticket.stat().st_mtime_ns  # now 0

        forced = _run_init(self.root, "--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)

        after = _mtimes(self.root, _SCAFFOLDED)
        for rel in _SCAFFOLDED:
            self.assertNotEqual(after[rel], 0, f"--force must rewrite {rel}")

        # Tickets are untouched: same content and same (epoch) mtime.
        self.assertEqual(ticket.read_text(encoding="utf-8"), ticket_before_text)
        self.assertEqual(ticket.stat().st_mtime_ns, ticket_before_mtime)


class InitPositionalNameTests(unittest.TestCase):
    """ARG1-074: `argos init <project>` positional aliases --name."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_positional_sets_project_name_in_cwd(self) -> None:
        # `argos init Zephyr` → scaffolds cwd, project name "Zephyr".
        proc = _run_init(self.root, "Zephyr")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Zephyr", proc.stdout)
        self.assertTrue((self.root / "argos/specs/STATE.md").is_file())
        self.assertIn("Zephyr", (self.root / "argos/specs/STATE.md").read_text(encoding="utf-8"))

    def test_positional_with_path_targets_path(self) -> None:
        # `argos init Zephyr --path <target>` → name "Zephyr", scaffolds target.
        target = self.root / "subrepo"
        target.mkdir()
        proc = _run_init(self.root, "Zephyr", "--path", str(target))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((target / "argos/specs/STATE.md").is_file())
        self.assertIn("Zephyr", (target / "argos/specs/STATE.md").read_text(encoding="utf-8"))
        # Nothing scaffolded in cwd itself.
        self.assertFalse((self.root / "argos/specs/STATE.md").is_file())

    def test_explicit_name_flag_wins_over_positional(self) -> None:
        proc = _run_init(self.root, "Positional", "--name", "FlagName")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = (self.root / "argos/specs/STATE.md").read_text(encoding="utf-8")
        self.assertIn("FlagName", text)
        self.assertNotIn("Positional", text)

    def test_bare_init_still_works(self) -> None:
        # No positional, no --name: unchanged behavior (detected name, cwd).
        proc = _run_init(self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("initialized", proc.stdout)
        self.assertTrue((self.root / "argos/specs/STATE.md").is_file())


if __name__ == "__main__":
    unittest.main()
