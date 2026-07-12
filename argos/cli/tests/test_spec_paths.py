"""Tests for argos.cli.spec_paths — shared spec-tree resolution (ARG1-075).

Covers the v1.0-vs-flat probe, the single-root guarantee of the derivers, and a
regression that argos's OWN repo still resolves to its v1.0 working tree (so
bare queue commands keep reading the real 65 KB STATE.md, not the flat
meta-backlog).
"""

import os
import tempfile
import unittest
from pathlib import Path

from argos.cli.spec_paths import (
    default_spec_paths,
    default_state_file,
    default_ticket_dir,
    resolve_specs_root,
)

# This file lives at argos/cli/tests/test_spec_paths.py → parents[3] is the
# repo root of the argos checkout under test.
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _make_state(root: Path, rel: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# STATE\n", encoding="utf-8")


class ResolveSpecsRootTests(unittest.TestCase):
    def test_v1_layout_resolves_to_v1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_state(root, "argos/specs/v1.0/STATE.md")
            # A flat STATE.md also present must NOT win — v1.0 takes priority.
            _make_state(root, "argos/specs/STATE.md")
            self.assertEqual(resolve_specs_root(root), Path("argos/specs/v1.0"))

    def test_flat_layout_resolves_to_flat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_state(root, "argos/specs/STATE.md")  # no v1.0/ segment
            self.assertEqual(resolve_specs_root(root), Path("argos/specs"))

    def test_no_specs_defaults_to_flat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Nothing scaffolded yet → flat default (what `init` will create).
            self.assertEqual(resolve_specs_root(tmp), Path("argos/specs"))


class DeriverSingleRootTests(unittest.TestCase):
    def test_derivers_share_one_root_v1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_state(root, "argos/specs/v1.0/STATE.md")
            state_file, ticket_dir = default_spec_paths(root)
            self.assertEqual(state_file, str(Path("argos/specs/v1.0/STATE.md")))
            self.assertEqual(ticket_dir, str(Path("argos/specs/v1.0/tickets")))
            # The standalone derivers agree with the combined call …
            self.assertEqual(default_state_file(root), state_file)
            self.assertEqual(default_ticket_dir(root), ticket_dir)
            # … and STATE.md never pairs with a tickets dir from a different root.
            self.assertEqual(Path(state_file).parent, Path(ticket_dir).parent)

    def test_derivers_share_one_root_flat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_state(root, "argos/specs/STATE.md")
            state_file, ticket_dir = default_spec_paths(root)
            self.assertEqual(state_file, str(Path("argos/specs/STATE.md")))
            self.assertEqual(ticket_dir, str(Path("argos/specs/tickets")))
            self.assertEqual(Path(state_file).parent, Path(ticket_dir).parent)
            self.assertEqual(Path(state_file).parent, Path("argos/specs"))


class SubdirectoryAnchorTests(unittest.TestCase):
    """ARG-006: bare calls anchor at the enclosing repo root from a subdir."""

    def _chdir(self, path: Path) -> None:
        old = Path.cwd()
        os.chdir(path)
        self.addCleanup(os.chdir, old)

    def test_bare_call_from_subdir_anchors_at_repo_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_state(root, "argos/specs/STATE.md")
            sub = root / "docs" / "deep"
            sub.mkdir(parents=True)
            self._chdir(sub)
            anchored = Path.cwd().parents[1]  # tmp, symlink-resolved by cwd
            state_file, ticket_dir = default_spec_paths()
            self.assertEqual(state_file, str(anchored / "argos/specs/STATE.md"))
            self.assertEqual(ticket_dir, str(anchored / "argos/specs/tickets"))
            self.assertEqual(default_state_file(), state_file)
            self.assertEqual(default_ticket_dir(), ticket_dir)

    def test_bare_call_at_repo_root_stays_relative(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_state(root, "argos/specs/STATE.md")
            self._chdir(root)
            self.assertEqual(
                default_spec_paths(),
                (str(Path("argos/specs/STATE.md")), str(Path("argos/specs/tickets"))),
            )

    def test_ascent_stops_at_git_boundary(self) -> None:
        # An unscaffolded repo nested under a scaffolded parent: the .git
        # boundary must win, never the parent's argos/specs/.
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            _make_state(parent, "argos/specs/STATE.md")
            inner = parent / "vendored-repo"
            (inner / ".git").mkdir(parents=True)
            sub = inner / "src"
            sub.mkdir()
            self._chdir(sub)
            anchored = Path.cwd().parent  # inner, symlink-resolved
            self.assertEqual(
                default_state_file(), str(anchored / "argos/specs/STATE.md")
            )

    def test_explicit_root_is_unchanged_from_subdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_state(root, "argos/specs/STATE.md")
            sub = root / "docs"
            sub.mkdir()
            self._chdir(sub)
            # Explicit repo_root keeps the historical relative contract.
            self.assertEqual(
                default_state_file(root), str(Path("argos/specs/STATE.md"))
            )


class ArgosOwnRepoRegressionTests(unittest.TestCase):
    def test_argos_repo_resolves_to_v1(self) -> None:
        # Fixture assumption: argos versions its own specs under v1.0/.
        self.assertTrue(
            (_REPO_ROOT / "argos" / "specs" / "v1.0" / "STATE.md").exists(),
            "expected argos's own repo to carry argos/specs/v1.0/STATE.md",
        )
        self.assertEqual(resolve_specs_root(_REPO_ROOT), Path("argos/specs/v1.0"))
        self.assertEqual(
            default_state_file(_REPO_ROOT), str(Path("argos/specs/v1.0/STATE.md"))
        )
        self.assertEqual(
            default_ticket_dir(_REPO_ROOT), str(Path("argos/specs/v1.0/tickets"))
        )


if __name__ == "__main__":
    unittest.main()
