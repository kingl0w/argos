"""Tests for ARG1-023 ``argos worktree-finalize``.

Each test that exercises ``git merge`` runs in a freshly-initialized
temporary git repo so the merge state is fully hermetic and the host
repo's branches are never disturbed. ADR-001 / ADR-002: stdlib only,
no third-party imports.

The module-level ``setUpModule`` resolves and caches the repo root once
so every test can reach ``argos/scripts/state-merge-driver.sh`` and
``argos/scripts/hooks/pre-commit-state-write.sh`` without re-deriving
the path.

Runnable as::

    python3 -m unittest argos.cli.tests.test_worktree_finalize -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_ARGOS_BIN = Path(__file__).resolve().parents[1] / "argos"
_MERGE_DRIVER = (
    _REPO_ROOT / "argos" / "scripts" / "state-merge-driver.sh"
)
_PRE_COMMIT_HOOK = (
    _REPO_ROOT
    / "argos"
    / "scripts"
    / "hooks"
    / "pre-commit-state-write.sh"
)


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _git_check(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    res = _git(*args, cwd=cwd)
    if res.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed in {cwd}: "
            f"stdout={res.stdout!r} stderr={res.stderr!r}"
        )
    return res


def _init_repo(root: Path) -> None:
    """Initialize a minimal git repo with one commit on ``main``."""
    _git_check("init", "-q", "-b", "main", cwd=root)
    _git_check("config", "user.email", "test@example.com", cwd=root)
    _git_check("config", "user.name", "test", cwd=root)
    _git_check("config", "commit.gpgsign", "false", cwd=root)
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git_check("add", "seed.txt", cwd=root)
    _git_check("commit", "-q", "-m", "seed", cwd=root)


def _install_state_merge_driver(repo: Path) -> None:
    """Register the argos-state merge driver against the test repo."""
    _git_check(
        "config", "merge.argos-state.name",
        "Argos STATE.md append-mostly merge",
        cwd=repo,
    )
    _git_check(
        "config", "merge.argos-state.driver",
        f"{_MERGE_DRIVER} %O %A %B %P %L",
        cwd=repo,
    )
    _git_check(
        "config", "merge.argos-state.recursive", "binary",
        cwd=repo,
    )
    (repo / ".gitattributes").write_text(
        "argos/specs/STATE.md merge=argos-state\n", encoding="utf-8"
    )
    _git_check("add", ".gitattributes", cwd=repo)
    _git_check("commit", "-q", "-m", "register merge driver", cwd=repo)


def _install_pre_commit_hook(repo: Path) -> None:
    """Wire the ARG1-032 pre-commit hook to the test repo's .git/hooks."""
    git_dir_res = _git_check("rev-parse", "--git-dir", cwd=repo)
    git_dir = git_dir_res.stdout.strip()
    if not Path(git_dir).is_absolute():
        git_dir = str(repo / git_dir)
    hooks_dir = Path(git_dir) / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    pc = hooks_dir / "pre-commit"
    pc.write_text(
        f"#!/bin/sh\nset -e\nexec '{_PRE_COMMIT_HOOK}' \"$@\"\n",
        encoding="utf-8",
    )
    pc.chmod(0o755)


def _make_branch_with_commit(
    repo: Path,
    branch: str,
    *,
    file_rel: str,
    content: str,
    message: str,
    base: str = "main",
) -> str:
    """Create ``branch`` from ``base``, add one commit, return its sha.

    Restores HEAD to ``base`` before returning so callers can keep
    setting up additional siblings without juggling checkout state.
    """
    _git_check("checkout", "-q", base, cwd=repo)
    _git_check("checkout", "-q", "-b", branch, cwd=repo)
    target = repo / file_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git_check("add", file_rel, cwd=repo)
    _git_check("commit", "-q", "-m", message, cwd=repo)
    sha = _git_check("rev-parse", "HEAD", cwd=repo).stdout.strip()
    _git_check("checkout", "-q", base, cwd=repo)
    return sha


def _commit_on_branch(
    repo: Path,
    branch: str,
    *,
    file_rel: str,
    content: str,
    message: str,
) -> str:
    """Add one commit to an existing ``branch``; return the new sha.

    Leaves HEAD on ``main`` after the commit so subsequent setup steps
    have a stable starting point.
    """
    _git_check("checkout", "-q", branch, cwd=repo)
    target = repo / file_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git_check("add", file_rel, cwd=repo)
    _git_check("commit", "-q", "-m", message, cwd=repo)
    sha = _git_check("rev-parse", "HEAD", cwd=repo).stdout.strip()
    _git_check("checkout", "-q", "main", cwd=repo)
    return sha


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(_REPO_ROOT)
        + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    )
    return subprocess.run(
        [sys.executable, str(_ARGOS_BIN), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd),
        env=env,
    )


# ---------------------------------------------------------------------------
# Library-level tests — call ``finalize`` directly.
# ---------------------------------------------------------------------------


class FinalizeFastForwardTests(unittest.TestCase):
    """AC#1 — ff merge when the worktree branch is one ahead."""

    def test_ff_merges_and_log_empty(self) -> None:
        from argos.cli.orchestrator.merge import (
            MERGE_STRATEGY_FF,
            finalize,
        )

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            _make_branch_with_commit(
                repo,
                "argos/ARG1-099",
                file_rel="src/feature.txt",
                content="feature\n",
                message="ARG1-099: add feature",
            )

            result = finalize(
                ticket_id="ARG1-099",
                result="pass",
                repo_root=repo,
            )

            self.assertTrue(result.merged)
            self.assertEqual(result.merge_strategy, MERGE_STRATEGY_FF)
            self.assertFalse(result.conflicts)
            self.assertTrue(result.worktree_preserved)

            log = _git_check(
                "log", "--oneline", "main..argos/ARG1-099", cwd=repo
            ).stdout
            self.assertEqual(log.strip(), "")

            head_branch = _git_check(
                "symbolic-ref", "--short", "HEAD", cwd=repo
            ).stdout.strip()
            self.assertEqual(head_branch, "main")


class FinalizeThreeWayTests(unittest.TestCase):
    """AC#2 — three-way merge when base moved but no conflict."""

    def test_three_way_merge_creates_merge_commit(self) -> None:
        from argos.cli.orchestrator.merge import (
            MERGE_STRATEGY_THREE_WAY,
            finalize,
        )

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            _make_branch_with_commit(
                repo,
                "argos/ARG1-099",
                file_rel="src/feature.txt",
                content="feature\n",
                message="ARG1-099: add feature",
            )
            # Move main forward on a disjoint file.
            (repo / "main_only.txt").write_text("main\n", encoding="utf-8")
            _git_check("add", "main_only.txt", cwd=repo)
            _git_check("commit", "-q", "-m", "main ahead", cwd=repo)

            result = finalize(
                ticket_id="ARG1-099",
                result="pass",
                repo_root=repo,
            )

            self.assertTrue(result.merged)
            self.assertEqual(
                result.merge_strategy, MERGE_STRATEGY_THREE_WAY
            )
            self.assertFalse(result.conflicts)

            first_parent_log = _git_check(
                "log", "--first-parent", "--oneline", "main", cwd=repo
            ).stdout.splitlines()
            top = first_parent_log[0]
            # `git log` with --first-parent on a merge commit lists the
            # merge subject; the auto-merge subject starts "Merge branch".
            self.assertIn("Merge branch", top)


class FinalizeConflictTests(unittest.TestCase):
    """AC#3 — conflict aborts the merge and writes a blocking escalation."""

    def test_conflict_aborts_and_escalates(self) -> None:
        from argos.cli.orchestrator.merge import finalize

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            (repo / "shared.txt").write_text("base\n", encoding="utf-8")
            _git_check("add", "shared.txt", cwd=repo)
            _git_check("commit", "-q", "-m", "shared base", cwd=repo)

            _make_branch_with_commit(
                repo,
                "argos/ARG1-099",
                file_rel="shared.txt",
                content="branch\n",
                message="ARG1-099: change shared",
            )
            # Conflicting change on main.
            (repo / "shared.txt").write_text("main\n", encoding="utf-8")
            _git_check("add", "shared.txt", cwd=repo)
            _git_check("commit", "-q", "-m", "main conflicting", cwd=repo)

            esc_dir = repo / "argos" / "specs" / "escalations"

            result = finalize(
                ticket_id="ARG1-099",
                result="pass",
                repo_root=repo,
                escalation_dir=esc_dir,
            )

            self.assertFalse(result.merged)
            self.assertTrue(result.conflicts)
            self.assertIsNone(result.merge_strategy)
            self.assertTrue(result.worktree_preserved)
            self.assertIsNotNone(result.escalation_path)

            # Base clean — "clean tree" in the AC's sense means: merge
            # has been aborted (no MERGE_HEAD), tracked files match
            # HEAD, no staged or unstaged changes. Untracked files
            # (the escalation we just wrote) are expected and don't
            # count toward dirtiness.
            git_dir = _git_check(
                "rev-parse", "--git-dir", cwd=repo
            ).stdout.strip()
            merge_head = (repo / git_dir / "MERGE_HEAD")
            self.assertFalse(merge_head.exists())
            tracked_status = _git_check(
                "status", "--porcelain", "--untracked-files=no",
                cwd=repo,
            ).stdout
            self.assertEqual(tracked_status.strip(), "")

            # Escalation file exists and matches the spec literals.
            esc_path = Path(result.escalation_path)
            self.assertTrue(esc_path.exists())
            self.assertTrue(
                esc_path.name.startswith("ARG1-099-"),
                f"unexpected escalation filename: {esc_path.name}",
            )
            text = esc_path.read_text(encoding="utf-8")
            self.assertIn("severity: blocking", text)
            self.assertIn("merge conflict", text)
            self.assertIn("raised_by: orchestrator", text)


class FinalizeFailPreservesTests(unittest.TestCase):
    """AC#4 — result=fail preserves worktree and branch."""

    def test_fail_no_op_preserves(self) -> None:
        from argos.cli.orchestrator.merge import finalize

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            _make_branch_with_commit(
                repo,
                "argos/ARG1-099",
                file_rel="src/feature.txt",
                content="feature\n",
                message="ARG1-099: add feature",
            )

            result = finalize(
                ticket_id="ARG1-099",
                result="fail",
                repo_root=repo,
            )

            self.assertFalse(result.merged)
            self.assertFalse(result.conflicts)
            self.assertIsNone(result.merge_strategy)
            self.assertTrue(result.worktree_preserved)

            branches = _git_check(
                "branch", "--list", "argos/ARG1-099", cwd=repo
            ).stdout
            self.assertIn("argos/ARG1-099", branches)

            # main HEAD has not advanced.
            log = _git_check(
                "log", "--oneline", "main", cwd=repo
            ).stdout.splitlines()
            self.assertEqual(len(log), 1)


class FinalizePassWithMinorsTests(unittest.TestCase):
    """AC#5 — pass-with-minors behaves identically to pass."""

    def test_pass_with_minors_merges(self) -> None:
        from argos.cli.orchestrator.merge import (
            MERGE_STRATEGY_FF,
            finalize,
        )

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            _make_branch_with_commit(
                repo,
                "argos/ARG1-099",
                file_rel="src/feature.txt",
                content="feature\n",
                message="ARG1-099: add feature",
            )

            result = finalize(
                ticket_id="ARG1-099",
                result="pass-with-minors",
                repo_root=repo,
            )

            self.assertTrue(result.merged)
            self.assertEqual(result.merge_strategy, MERGE_STRATEGY_FF)
            self.assertFalse(result.conflicts)


# ---------------------------------------------------------------------------
# CLI-surface tests — invoke ``argos worktree-finalize`` as a subprocess.
# ---------------------------------------------------------------------------


class FinalizeCLIFastForwardTests(unittest.TestCase):
    """AC#1 via the CLI — exit 0, post-merge log empty."""

    def test_cli_ff_exit_zero_log_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            _make_branch_with_commit(
                repo,
                "argos/ARG1-099",
                file_rel="src/feature.txt",
                content="feature\n",
                message="ARG1-099: add feature",
            )

            res = _run_cli(
                "worktree-finalize",
                "--ticket", "ARG1-099",
                "--result", "pass",
                cwd=repo,
            )
            self.assertEqual(
                res.returncode, 0,
                f"stdout={res.stdout!r} stderr={res.stderr!r}",
            )
            log = _git_check(
                "log", "--oneline", "main..argos/ARG1-099", cwd=repo
            ).stdout
            self.assertEqual(log.strip(), "")


class FinalizeCLIThreeWayTests(unittest.TestCase):
    """AC#2 via the CLI — first-parent log on main starts with a merge commit."""

    def test_cli_three_way_first_parent_is_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            _make_branch_with_commit(
                repo,
                "argos/ARG1-099",
                file_rel="src/feature.txt",
                content="feature\n",
                message="ARG1-099: add feature",
            )
            (repo / "main_only.txt").write_text("main\n", encoding="utf-8")
            _git_check("add", "main_only.txt", cwd=repo)
            _git_check("commit", "-q", "-m", "main ahead", cwd=repo)

            res = _run_cli(
                "worktree-finalize",
                "--ticket", "ARG1-099",
                "--result", "pass",
                cwd=repo,
            )
            self.assertEqual(
                res.returncode, 0,
                f"stdout={res.stdout!r} stderr={res.stderr!r}",
            )
            head_msg = _git_check(
                "log", "--first-parent", "-n", "1",
                "--pretty=%s", "main", cwd=repo,
            ).stdout.strip()
            self.assertIn("Merge branch", head_msg)


class FinalizeCLIConflictTests(unittest.TestCase):
    """AC#3 via the CLI — non-zero exit, base clean, escalation written."""

    def test_cli_conflict_writes_escalation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            (repo / "shared.txt").write_text("base\n", encoding="utf-8")
            _git_check("add", "shared.txt", cwd=repo)
            _git_check("commit", "-q", "-m", "shared base", cwd=repo)

            _make_branch_with_commit(
                repo,
                "argos/ARG1-099",
                file_rel="shared.txt",
                content="branch\n",
                message="ARG1-099: change shared",
            )
            (repo / "shared.txt").write_text("main\n", encoding="utf-8")
            _git_check("add", "shared.txt", cwd=repo)
            _git_check("commit", "-q", "-m", "main conflicting", cwd=repo)

            res = _run_cli(
                "worktree-finalize",
                "--ticket", "ARG1-099",
                "--result", "pass",
                cwd=repo,
            )
            self.assertNotEqual(res.returncode, 0)

            tracked_status = _git_check(
                "status", "--porcelain", "--untracked-files=no",
                cwd=repo,
            ).stdout
            self.assertEqual(tracked_status.strip(), "")
            git_dir = _git_check(
                "rev-parse", "--git-dir", cwd=repo
            ).stdout.strip()
            self.assertFalse((repo / git_dir / "MERGE_HEAD").exists())

            esc_dir = repo / "argos" / "specs" / "escalations"
            esc_files = [
                p for p in esc_dir.glob("ARG1-099-*.md") if p.is_file()
            ]
            self.assertEqual(len(esc_files), 1, esc_files)
            text = esc_files[0].read_text(encoding="utf-8")
            self.assertIn("severity: blocking", text)
            self.assertIn("merge conflict", text)


class FinalizeCLIFailTests(unittest.TestCase):
    """AC#4 via the CLI — fail preserves worktree directory and branch."""

    def test_cli_fail_preserves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            _make_branch_with_commit(
                repo,
                "argos/ARG1-099",
                file_rel="src/feature.txt",
                content="feature\n",
                message="ARG1-099: add feature",
            )
            # Add a real worktree to mirror what the orchestrator would
            # have created. The AC's `test -d .argos/worktrees/ARG1-099-*`
            # check passes iff this directory survives finalize.
            wt = (
                repo / ".argos" / "worktrees" / "ARG1-099-deadbee"
            )
            wt.parent.mkdir(parents=True, exist_ok=True)
            _git_check(
                "worktree", "add", str(wt), "argos/ARG1-099", cwd=repo
            )

            res = _run_cli(
                "worktree-finalize",
                "--ticket", "ARG1-099",
                "--result", "fail",
                cwd=repo,
            )
            self.assertEqual(
                res.returncode, 0,
                f"stdout={res.stdout!r} stderr={res.stderr!r}",
            )

            self.assertTrue(wt.exists())
            branches = _git_check(
                "branch", "--list", "argos/ARG1-099", cwd=repo
            ).stdout
            self.assertIn("argos/ARG1-099", branches)


class FinalizeCLIPassWithMinorsTests(unittest.TestCase):
    """AC#5 via the CLI — identical exit to pass."""

    def test_cli_pass_with_minors_merges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            _make_branch_with_commit(
                repo,
                "argos/ARG1-099",
                file_rel="src/feature.txt",
                content="feature\n",
                message="ARG1-099: add feature",
            )

            res = _run_cli(
                "worktree-finalize",
                "--ticket", "ARG1-099",
                "--result", "pass-with-minors",
                cwd=repo,
            )
            self.assertEqual(
                res.returncode, 0,
                f"stdout={res.stdout!r} stderr={res.stderr!r}",
            )
            log = _git_check(
                "log", "--oneline", "main..argos/ARG1-099", cwd=repo
            ).stdout
            self.assertEqual(log.strip(), "")


class FinalizeCLIJSONTests(unittest.TestCase):
    """AC#6 via the CLI — JSON output has the required keys."""

    def test_cli_json_contains_required_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            _make_branch_with_commit(
                repo,
                "argos/ARG1-099",
                file_rel="src/feature.txt",
                content="feature\n",
                message="ARG1-099: add feature",
            )

            res = _run_cli(
                "worktree-finalize",
                "--json",
                "--ticket", "ARG1-099",
                "--result", "pass",
                cwd=repo,
            )
            self.assertEqual(
                res.returncode, 0,
                f"stdout={res.stdout!r} stderr={res.stderr!r}",
            )
            payload = json.loads(res.stdout.strip())
            for key in (
                "merged", "merge_strategy", "conflicts", "worktree_preserved"
            ):
                self.assertIn(key, payload)
            self.assertTrue(payload["merged"])
            self.assertEqual(payload["merge_strategy"], "ff")
            self.assertFalse(payload["conflicts"])
            self.assertTrue(payload["worktree_preserved"])


# ---------------------------------------------------------------------------
# Empirical pre-commit-hook + STATE.md merge-driver coexistence test.
# ---------------------------------------------------------------------------


class FinalizeWithStateAndHookTests(unittest.TestCase):
    """Three-way merge with STATE.md changes on both sides + ARG1-032 hook.

    Confirms the brief's empirical claim: "Merge commits don't need
    bypass — STATE.md is reconciled via the ARG1-052 driver during
    merge, not via direct write." With the merge driver registered
    AND the pre-commit hook installed, an auto-merge that brings new
    verifier-author argos:entry blocks from the worktree branch must
    pass the hook.
    """

    def _verifier_block(self, *, ticket: str, marker: str) -> str:
        return (
            f"<!-- argos:entry id={marker}-{ticket} ticket={ticket} "
            f"author=verifier session=sess-{marker} -->\n"
            f"- {marker}: ticket {ticket} verified.\n"
            f"<!-- /argos:entry -->\n"
        )

    def test_merge_with_state_changes_and_hook_succeeds(self) -> None:
        from argos.cli.orchestrator.merge import (
            MERGE_STRATEGY_THREE_WAY,
            finalize,
        )

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            # Seed STATE.md with one base block that both sides preserve.
            state_path = repo / "argos" / "specs" / "STATE.md"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(
                "# state\n\n## Done this cycle\n\n"
                + self._verifier_block(
                    ticket="ARG1-000", marker="2026-04-01T00:00:00Z"
                ),
                encoding="utf-8",
            )
            _git_check("add", "argos/specs/STATE.md", cwd=repo)
            _git_check("commit", "-q", "-m", "seed STATE.md", cwd=repo)

            # Register the merge driver + install the hook AFTER the
            # initial commits so the hook sees only the merge diff.
            _install_state_merge_driver(repo)
            _install_pre_commit_hook(repo)

            # Worktree branch appends one new verifier block.
            _git_check("checkout", "-q", "-b", "argos/ARG1-099", cwd=repo)
            state_text = state_path.read_text(encoding="utf-8")
            state_path.write_text(
                state_text
                + "\n"
                + self._verifier_block(
                    ticket="ARG1-099", marker="2026-04-26T00:00:00Z"
                ),
                encoding="utf-8",
            )
            _git_check("add", "argos/specs/STATE.md", cwd=repo)
            _git_check(
                "commit", "-q", "-m", "ARG1-099: verifier block",
                cwd=repo,
            )

            # main: append a different verifier block to STATE.md so
            # both sides have non-trivial STATE.md diffs.
            _git_check("checkout", "-q", "main", cwd=repo)
            state_text = state_path.read_text(encoding="utf-8")
            state_path.write_text(
                state_text
                + "\n"
                + self._verifier_block(
                    ticket="ARG1-088", marker="2026-04-27T00:00:00Z"
                ),
                encoding="utf-8",
            )
            _git_check("add", "argos/specs/STATE.md", cwd=repo)
            _git_check(
                "commit", "-q", "-m", "ARG1-088: verifier block",
                cwd=repo,
            )

            result = finalize(
                ticket_id="ARG1-099",
                result="pass",
                repo_root=repo,
            )

            self.assertTrue(
                result.merged,
                f"expected merge to succeed; "
                f"strategy={result.merge_strategy} "
                f"conflicts={result.conflicts} "
                f"escalation={result.escalation_path}",
            )
            self.assertEqual(
                result.merge_strategy, MERGE_STRATEGY_THREE_WAY
            )
            self.assertFalse(result.conflicts)

            # Sanity: merged STATE.md contains both new blocks plus the seed.
            merged_state = state_path.read_text(encoding="utf-8")
            self.assertIn("ticket=ARG1-000", merged_state)
            self.assertIn("ticket=ARG1-088", merged_state)
            self.assertIn("ticket=ARG1-099", merged_state)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
