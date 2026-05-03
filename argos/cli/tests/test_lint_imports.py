"""Tests for ``argos.cli.lint_imports`` and the ``lint-imports`` CLI shim.

Runnable as::

    python3 -m unittest argos.cli.tests.test_lint_imports -v

Stdlib only (ADR-001 / ADR-002): no pytest, no third-party imports.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli.lint_imports import (  # noqa: E402  (sys.path tweak above)
    STDLIB_ALLOWLIST,
    lint_file,
    lint_tree,
)

_FIXTURE_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "lint_imports"
)


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "argos.cli", "lint-imports", *args],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        check=False,
    )


def _write(tree_root: Path, rel: str, body: str) -> Path:
    p = tree_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# STDLIB_ALLOWLIST contract — guards against silent widening.
# ---------------------------------------------------------------------------


class AllowlistContractTests(unittest.TestCase):
    def test_allowlist_includes_adr001_minimum(self) -> None:
        """ADR-001 §Pros enumerates argparse, re, dataclasses, pathlib, json,
        datetime as the runtime stdlib subset. Plus __future__ and argos.
        """
        for name in (
            "argparse",
            "re",
            "dataclasses",
            "pathlib",
            "json",
            "datetime",
            "__future__",
            "argos",
        ):
            self.assertIn(name, STDLIB_ALLOWLIST)

    def test_allowlist_rejects_known_third_party(self) -> None:
        for name in ("pyyaml", "yaml", "pytest", "requests", "numpy"):
            self.assertNotIn(name, STDLIB_ALLOWLIST)


# ---------------------------------------------------------------------------
# Direct API — lint_file / lint_tree
# ---------------------------------------------------------------------------


class LintFileApiTests(unittest.TestCase):
    def test_stdlib_only_file_passes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = _write(
                root,
                "ok.py",
                """
                from __future__ import annotations
                import json
                from pathlib import Path
                from argos.cli.lint_imports import STDLIB_ALLOWLIST
                """,
            )
            self.assertEqual(lint_file(f, root), [])

    def test_single_forbidden_import_returns_one_violation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = _write(root, "bad.py", "import requests\n")
            v = lint_file(f, root)
            self.assertEqual(len(v), 1)
            relpath, line, name = v[0]
            self.assertEqual(relpath, "bad.py")
            self.assertEqual(line, 1)
            self.assertEqual(name, "requests")

    def test_import_from_third_party_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = _write(root, "bad.py", "from requests import get\n")
            v = lint_file(f, root)
            self.assertEqual(len(v), 1)
            self.assertEqual(v[0][2], "requests")

    def test_dotted_internal_argos_imports_pass(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = _write(
                root,
                "ok.py",
                """
                from argos.cli.foo import bar
                from argos.cli.tests.fixtures import qux
                import argos.cli
                """,
            )
            self.assertEqual(lint_file(f, root), [])

    def test_dotted_third_party_top_level_flagged(self) -> None:
        """``import requests.adapters`` flags the ``requests`` top-level only."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = _write(root, "bad.py", "import requests.adapters\n")
            v = lint_file(f, root)
            self.assertEqual(len(v), 1)
            self.assertEqual(v[0][2], "requests.adapters")

    def test_relative_imports_treated_as_internal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = _write(
                root,
                "pkg/mod.py",
                """
                from . import sibling
                from .other import thing
                """,
            )
            self.assertEqual(lint_file(f, root), [])


class LintTreeApiTests(unittest.TestCase):
    def test_recurses_into_subdirectories(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root, "a.py", "import json\n")
            _write(root, "sub/b.py", "import requests\n")
            _write(root, "sub/deep/c.py", "from yaml import safe_load\n")
            v = lint_tree(root)
            self.assertEqual(len(v), 2)
            relpaths = sorted(item[0] for item in v)
            self.assertEqual(
                relpaths,
                [str(Path("sub") / "b.py"), str(Path("sub") / "deep" / "c.py")],
            )

    def test_multiple_violations_in_one_file_listed_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(
                root,
                "bad.py",
                """
                import requests
                import yaml
                from numpy import array
                """,
            )
            v = lint_tree(root)
            self.assertEqual(len(v), 3)
            self.assertEqual([item[2] for item in v], ["requests", "yaml", "numpy"])

    def test_fixtures_subtree_skipped_when_root_is_above(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root, "src/clean.py", "import json\n")
            _write(root, "src/tests/fixtures/bad.py", "import requests\n")
            self.assertEqual(lint_tree(root), [])

    def test_fixtures_subtree_linted_when_root_targets_it(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "fixtures"
            _write(root, "bad.py", "import requests\n")
            v = lint_tree(root)
            self.assertEqual(len(v), 1)
            self.assertEqual(v[0][2], "requests")


# ---------------------------------------------------------------------------
# CLI — subprocess invocations of `python3 -m argos.cli lint-imports ...`
# ---------------------------------------------------------------------------


class LintImportsCliTests(unittest.TestCase):
    def test_help_exits_zero(self) -> None:
        proc = _run_cli("--help")
        self.assertEqual(proc.returncode, 0, msg=f"stderr: {proc.stderr!r}")
        self.assertIn("lint-imports", proc.stdout)

    def test_listed_under_internal_subcommands(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "argos.cli", "--help"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("lint-imports", proc.stdout)

    def test_clean_argos_tree_exits_zero(self) -> None:
        """AC#3 pre-flight — current main must pass."""
        proc = _run_cli("argos/")
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"stderr was: {proc.stderr!r}",
        )
        self.assertEqual(proc.stderr, "")

    def test_fixture_directory_exits_one_with_canonical_format(self) -> None:
        """AC#4 — bad_import.py fixture surfaces in canonical format."""
        proc = _run_cli(str(_FIXTURE_DIR))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(
            proc.stderr.strip(),
            "lint-imports: bad_import.py:1: forbidden import requests",
        )

    def test_missing_path_exits_one_with_canonical_message(self) -> None:
        """AC#5 — not-found error format."""
        proc = _run_cli("/nonexistent/path-deadbeef")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(
            proc.stderr.strip(),
            "lint-imports: /nonexistent/path-deadbeef: not found",
        )

    def test_multiple_violations_emit_one_line_each(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root, "a.py", "import requests\nimport yaml\n")
            _write(root, "b.py", "from numpy import array\n")
            proc = _run_cli(str(root))
            self.assertEqual(proc.returncode, 1)
            lines = [
                ln for ln in proc.stderr.splitlines() if ln.startswith("lint-imports:")
            ]
            self.assertEqual(len(lines), 3)
            for ln in lines:
                self.assertRegex(
                    ln,
                    r"^lint-imports: \S+:\d+: forbidden import \S+$",
                )

    def test_single_file_root_lints_just_that_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = _write(root, "x.py", "import requests\n")
            proc = _run_cli(str(f))
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(
                proc.stderr.strip(),
                "lint-imports: x.py:1: forbidden import requests",
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
