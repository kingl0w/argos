"""Tests for ARG1-004 ``argos sync``.

Each git-touching test runs in a freshly-initialized temporary repo (with a
file:// bare ``origin`` where the worktree-prune flow needs one), so the
reconciliations are exercised end-to-end without network access. The issues
phase is driven through a fake :class:`IssueBackend`, and the offline guarantee
of ``--no-issues`` is verified with a PATH-shadowing ``gh`` sentinel rather
than ``strace`` (the ticket's portability TODO).

Stdlib only — ADR-001 / ADR-002. Runnable as::

    python3 -m unittest argos.cli.tests.test_sync -v
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli import reconcile  # noqa: E402
from argos.cli.commands import sync as sync_cmd  # noqa: E402
from argos.cli.reconcile import (  # noqa: E402
    STATUS_FIXED,
    STATUS_MISMATCH,
    STATUS_OK,
    STATUS_WOULD_FIX,
    IssueBackend,
)

_ARGOS_BIN = Path(__file__).resolve().parents[1] / "argos"


# --------------------------------------------------------------------------
# git helpers
# --------------------------------------------------------------------------


def _git(args: list, *, cwd: Path, env: "dict | None" = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), env=env, capture_output=True, text=True, check=False
    )


def _git_check(args: list, *, cwd: Path, env: "dict | None" = None) -> subprocess.CompletedProcess:
    res = _git(args, cwd=cwd, env=env)
    if res.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed in {cwd}: "
            f"stdout={res.stdout!r} stderr={res.stderr!r}"
        )
    return res


def _init_repo(root: Path) -> None:
    _git_check(["init", "-q", "-b", "main"], cwd=root)
    _git_check(["config", "user.email", "test@example.com"], cwd=root)
    _git_check(["config", "user.name", "test"], cwd=root)
    _git_check(["config", "commit.gpgsign", "false"], cwd=root)
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git_check(["add", "seed.txt"], cwd=root)
    _git_check(["commit", "-q", "-m", "seed"], cwd=root)


def _seed_state(root: Path, body: str) -> Path:
    state_dir = root / "argos" / "specs" / "v1.0"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "STATE.md"
    state_path.write_text(body, encoding="utf-8")
    _git_check(["add", "argos/specs/v1.0/STATE.md"], cwd=root)
    _git_check(["commit", "-q", "-m", "seed state"], cwd=root)
    return state_path


def _state_with_done(*ticket_ids: str) -> str:
    blocks = []
    for tid in ticket_ids:
        blocks.append(
            f"<!-- argos:entry id=2026-05-03T00:00:00Z-{tid} ticket={tid} "
            f"author=verifier session=sess-{tid} -->\n"
            f"- **[2026-05-03T00:00:00Z] {tid} — verified**\n"
            f"  - Decision: pass\n"
            f"<!-- /argos:entry -->\n"
        )
    done = "\n".join(blocks) if blocks else "_none_\n"
    return (
        "# Argos v1.0 — State\n\n"
        "## Current focus\n\nSyncing.\n\n"
        "## Queue\n\n_none_\n\n"
        "## In progress\n\n_none_\n\n"
        "## Done this cycle\n\n"
        f"{done}\n"
        "## Known drift\n\n_none_\n"
    )


# --------------------------------------------------------------------------
# fake issue backend
# --------------------------------------------------------------------------


class _FakeBackend(IssueBackend):
    def __init__(self, *, available=True, issues=None):
        self._available = available
        # issues: {ticket_id: issue_number}
        self._issues = dict(issues or {})
        self.updated: list = []  # (number, title, path)

    def available(self) -> bool:
        return self._available

    def find_issue(self, ticket_id: str):
        return self._issues.get(ticket_id)

    def update_issue(self, number: int, title: str, body_file: Path) -> None:
        self.updated.append((number, title, Path(body_file)))


class _RepoFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name).resolve()
        _init_repo(self.repo)

    def tearDown(self) -> None:
        self._tmp.cleanup()


# --------------------------------------------------------------------------
# state-git reconciliation (AC#3)
# --------------------------------------------------------------------------


class TestStateGit(_RepoFixture):
    def test_done_ticket_with_merge_commit_is_ok(self) -> None:
        # A commit on main's first-parent history names the ticket.
        _git_check(["commit", "--allow-empty", "-q", "-m", "merge: ARG1-200 done"],
                   cwd=self.repo)
        state_path = _seed_state(self.repo, _state_with_done("ARG1-200"))
        res = reconcile.reconcile_state_git(
            state_file=state_path, repo_root=self.repo, main_ref="main"
        )
        self.assertEqual(res.status, STATUS_OK)

    def test_done_ticket_without_merge_commit_is_mismatch(self) -> None:
        state_path = _seed_state(self.repo, _state_with_done("ARG1-999"))
        res = reconcile.reconcile_state_git(
            state_file=state_path, repo_root=self.repo, main_ref="main"
        )
        self.assertEqual(res.status, STATUS_MISMATCH)
        self.assertTrue(res.is_mismatch)
        joined = "\n".join(res.details)
        self.assertIn("ARG1-999", joined)
        self.assertIn("git log --first-parent main", joined)

    def test_empty_done_section_is_ok(self) -> None:
        state_path = _seed_state(self.repo, _state_with_done())
        res = reconcile.reconcile_state_git(
            state_file=state_path, repo_root=self.repo, main_ref="main"
        )
        self.assertEqual(res.status, STATUS_OK)

    def test_word_boundary_avoids_false_positive(self) -> None:
        # A commit naming ARG1-20 must NOT satisfy ARG1-200.
        _git_check(["commit", "--allow-empty", "-q", "-m", "merge: ARG1-20 other"],
                   cwd=self.repo)
        state_path = _seed_state(self.repo, _state_with_done("ARG1-200"))
        res = reconcile.reconcile_state_git(
            state_file=state_path, repo_root=self.repo, main_ref="main"
        )
        self.assertEqual(res.status, STATUS_MISMATCH)

    def test_cli_exits_nonzero_and_names_ticket_on_mismatch(self) -> None:
        """AC#3 — through run_sync: non-zero exit, stderr names ticket + commit."""
        state_path = _seed_state(self.repo, _state_with_done("ARG1-999"))
        out, err = io.StringIO(), io.StringIO()
        rc = sync_cmd.run_sync(
            repo_root=self.repo,
            state_file=state_path,
            tickets_dir=self.repo / "argos" / "specs" / "v1.0" / "tickets",
            main_ref="main",
            dry_run=False,
            no_issues=True,
            out=out,
            err=err,
        )
        self.assertEqual(rc, 1)
        self.assertIn("ARG1-999", err.getvalue())
        self.assertIn("git log --first-parent main", err.getvalue())


# --------------------------------------------------------------------------
# worktree pruning (AC#2)
# --------------------------------------------------------------------------


class TestWorktreePrune(_RepoFixture):
    def _make_origin(self) -> Path:
        origin = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(origin, ignore_errors=True))
        _git_check(["init", "-q", "--bare", "-b", "main", str(origin)], cwd=self.repo)
        _git_check(["remote", "add", "origin", str(origin)], cwd=self.repo)
        _git_check(["push", "-q", "origin", "main"], cwd=self.repo)
        return origin

    def _add_worktree(self, ticket: str) -> Path:
        branch = f"argos/{ticket}"
        wt = self.repo / ".argos" / "worktrees" / f"{ticket}-abc123"
        wt.parent.mkdir(parents=True, exist_ok=True)
        _git_check(["worktree", "add", "-q", "-b", branch, str(wt)], cwd=self.repo)
        # produce a commit on the branch
        (wt / "work.txt").write_text("work\n", encoding="utf-8")
        _git_check(["add", "work.txt"], cwd=wt)
        _git_check(["commit", "-q", "-m", f"{ticket} work"], cwd=wt)
        return wt

    def _merge_to_main(self, ticket: str) -> None:
        _git_check(["checkout", "-q", "main"], cwd=self.repo)
        _git_check(["merge", "--no-ff", "--no-edit", "-q", f"argos/{ticket}"],
                   cwd=self.repo)

    def test_merged_and_origin_deleted_is_pruned(self) -> None:
        """AC#2 — branch merged + deleted from origin → worktree gone."""
        self._make_origin()
        wt = self._add_worktree("ARG1-300")
        _git_check(["push", "-q", "origin", "argos/ARG1-300"], cwd=self.repo)
        self._merge_to_main("ARG1-300")
        # Delete the branch on origin (also drops the local tracking ref).
        _git_check(["push", "-q", "origin", "--delete", "argos/ARG1-300"], cwd=self.repo)

        self.assertTrue(wt.exists())
        res = reconcile.reconcile_worktrees(repo_root=self.repo, main_ref="main")
        self.assertEqual(res.status, STATUS_FIXED)
        self.assertFalse(wt.exists())

        listing = _git_check(["worktree", "list", "--porcelain"], cwd=self.repo).stdout
        self.assertNotIn("ARG1-300-abc123", listing)
        # The merged branch is dropped too.
        branches = _git_check(["branch", "--list", "argos/ARG1-300"], cwd=self.repo).stdout
        self.assertEqual(branches.strip(), "")

    def test_unmerged_worktree_is_kept(self) -> None:
        self._make_origin()
        wt = self._add_worktree("ARG1-301")
        _git_check(["push", "-q", "origin", "argos/ARG1-301"], cwd=self.repo)
        _git_check(["push", "-q", "origin", "--delete", "argos/ARG1-301"], cwd=self.repo)
        # Never merged into main.
        res = reconcile.reconcile_worktrees(repo_root=self.repo, main_ref="main")
        self.assertEqual(res.status, STATUS_OK)
        self.assertTrue(wt.exists())

    def test_merged_but_origin_still_has_branch_is_kept(self) -> None:
        self._make_origin()
        wt = self._add_worktree("ARG1-302")
        _git_check(["push", "-q", "origin", "argos/ARG1-302"], cwd=self.repo)
        self._merge_to_main("ARG1-302")
        # Branch still on origin (not deleted) → not stale yet.
        res = reconcile.reconcile_worktrees(repo_root=self.repo, main_ref="main")
        self.assertEqual(res.status, STATUS_OK)
        self.assertTrue(wt.exists())

    def test_dry_run_reports_would_fix_without_removing(self) -> None:
        self._make_origin()
        wt = self._add_worktree("ARG1-303")
        _git_check(["push", "-q", "origin", "argos/ARG1-303"], cwd=self.repo)
        self._merge_to_main("ARG1-303")
        _git_check(["push", "-q", "origin", "--delete", "argos/ARG1-303"], cwd=self.repo)

        res = reconcile.reconcile_worktrees(
            repo_root=self.repo, main_ref="main", dry_run=True
        )
        self.assertEqual(res.status, STATUS_WOULD_FIX)
        self.assertTrue(wt.exists())  # untouched

    def test_no_origin_remote_merged_is_pruned(self) -> None:
        """Local-only repo: a merged worktree is stale (no upstream to hold it)."""
        wt = self._add_worktree("ARG1-304")
        self._merge_to_main("ARG1-304")
        res = reconcile.reconcile_worktrees(repo_root=self.repo, main_ref="main")
        self.assertEqual(res.status, STATUS_FIXED)
        self.assertFalse(wt.exists())


# --------------------------------------------------------------------------
# issues reconciliation (phase 1)
# --------------------------------------------------------------------------


class TestIssues(_RepoFixture):
    def _seed_ticket(self, tid: str, title: str) -> Path:
        tdir = self.repo / "argos" / "specs" / "v1.0" / "tickets"
        tdir.mkdir(parents=True, exist_ok=True)
        p = tdir / f"{tid}-some-slug.md"
        p.write_text(f"# {title}\n\nbody\n", encoding="utf-8")
        return p

    @property
    def tickets_dir(self) -> Path:
        return self.repo / "argos" / "specs" / "v1.0" / "tickets"

    def test_skip_flag_makes_no_backend_calls(self) -> None:
        backend = _FakeBackend(available=True, issues={"ARG1-400": 7})
        self._seed_ticket("ARG1-400", "ARG1-400 thing")
        res = reconcile.reconcile_issues(
            tickets_dir=self.tickets_dir, repo_root=self.repo,
            backend=backend, skip=True,
        )
        self.assertEqual(res.status, STATUS_OK)
        self.assertIn("skipped", res.summary)
        self.assertEqual(backend.updated, [])

    def test_unavailable_backend_is_skipped_ok(self) -> None:
        backend = _FakeBackend(available=False)
        res = reconcile.reconcile_issues(
            tickets_dir=self.tickets_dir, repo_root=self.repo, backend=backend,
        )
        self.assertEqual(res.status, STATUS_OK)

    def test_existing_issue_rerendered_on_real_run(self) -> None:
        backend = _FakeBackend(available=True, issues={"ARG1-401": 11})
        self._seed_ticket("ARG1-401", "ARG1-401 implement thing")
        res = reconcile.reconcile_issues(
            tickets_dir=self.tickets_dir, repo_root=self.repo, backend=backend,
        )
        self.assertEqual(res.status, STATUS_FIXED)
        self.assertEqual(len(backend.updated), 1)
        number, title, _ = backend.updated[0]
        self.assertEqual(number, 11)
        self.assertEqual(title, "ARG1-401 implement thing")

    def test_missing_issue_is_not_created(self) -> None:
        backend = _FakeBackend(available=True, issues={})  # no issues exist
        self._seed_ticket("ARG1-402", "ARG1-402 thing")
        res = reconcile.reconcile_issues(
            tickets_dir=self.tickets_dir, repo_root=self.repo, backend=backend,
        )
        self.assertEqual(res.status, STATUS_OK)
        self.assertEqual(backend.updated, [])

    def test_dry_run_would_fix_no_update(self) -> None:
        backend = _FakeBackend(available=True, issues={"ARG1-403": 3})
        self._seed_ticket("ARG1-403", "ARG1-403 thing")
        res = reconcile.reconcile_issues(
            tickets_dir=self.tickets_dir, repo_root=self.repo,
            backend=backend, dry_run=True,
        )
        self.assertEqual(res.status, STATUS_WOULD_FIX)
        self.assertEqual(backend.updated, [])


# --------------------------------------------------------------------------
# full command surface (AC#1, AC#4, AC#5)
# --------------------------------------------------------------------------


class TestDryRunTable(_RepoFixture):
    def test_dry_run_lists_three_phases_and_exits_zero(self) -> None:
        """AC#1 — dry-run exits 0, lists all three phases with status tokens."""
        state_path = _seed_state(self.repo, _state_with_done())
        out, err = io.StringIO(), io.StringIO()
        rc = sync_cmd.run_sync(
            repo_root=self.repo,
            state_file=state_path,
            tickets_dir=self.repo / "argos" / "specs" / "v1.0" / "tickets",
            main_ref="main",
            dry_run=True,
            no_issues=True,
            out=out,
            err=err,
        )
        self.assertEqual(rc, 0)
        text = out.getvalue()
        for phase in ("issues", "state-git", "worktrees"):
            self.assertIn(phase, text)
        # Every phase status is from the dry-run vocabulary.
        for line in text.splitlines()[1:]:
            tokens = line.split()
            self.assertTrue(
                any(s in tokens for s in (STATUS_OK, STATUS_WOULD_FIX, STATUS_MISMATCH)),
                msg=f"unexpected status in line: {line!r}",
            )

    def test_dry_run_zero_even_with_mismatch(self) -> None:
        """AC#1 — dry-run is a report; a mismatch does not flip the exit code."""
        state_path = _seed_state(self.repo, _state_with_done("ARG1-999"))
        out, err = io.StringIO(), io.StringIO()
        rc = sync_cmd.run_sync(
            repo_root=self.repo,
            state_file=state_path,
            tickets_dir=self.repo / "argos" / "specs" / "v1.0" / "tickets",
            main_ref="main",
            dry_run=True,
            no_issues=True,
            out=out,
            err=err,
        )
        self.assertEqual(rc, 0)
        self.assertIn(STATUS_MISMATCH, out.getvalue())


class TestDelegation(_RepoFixture):
    def test_close_cycle_delegates(self) -> None:
        """AC#4 — --close-cycle returns the cycle-close handler's exit code."""
        # No '## Done this cycle' blocks → cycle-close prints 'nothing to close'
        # and exits 0.
        _seed_state(self.repo, _state_with_done())
        res = subprocess.run(
            [str(_ARGOS_BIN), "sync", "--close-cycle",
             "--state-file", str(self.repo / "argos/specs/v1.0/STATE.md"),
             "--repo-root", str(self.repo)],
            cwd=str(self.repo), capture_output=True, text=True, check=False,
        )
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn("nothing to close", res.stdout)

    def test_clean_queue_delegates(self) -> None:
        _seed_state(self.repo, _state_with_done())
        res = subprocess.run(
            [str(_ARGOS_BIN), "sync", "--clean-queue",
             "--state-file", str(self.repo / "argos/specs/v1.0/STATE.md"),
             "--repo-root", str(self.repo)],
            cwd=str(self.repo), capture_output=True, text=True, check=False,
        )
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn("nothing to clean", res.stdout)


class TestNoIssuesOffline(_RepoFixture):
    def test_no_issues_invokes_no_gh(self) -> None:
        """AC#5 — --no-issues makes zero gh calls (PATH-shadow sentinel)."""
        state_path = _seed_state(self.repo, _state_with_done())

        # Build a fake `gh` that records any invocation, and put it first on PATH.
        bindir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(bindir, ignore_errors=True))
        sentinel = bindir / "gh-was-called"
        fake_gh = bindir / "gh"
        fake_gh.write_text(
            f"#!/bin/sh\necho called >> '{sentinel}'\nexit 0\n", encoding="utf-8"
        )
        fake_gh.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = f"{bindir}{os.pathsep}{env.get('PATH', '')}"

        res = subprocess.run(
            [sys.executable, str(_ARGOS_BIN), "sync", "--no-issues",
             "--state-file", str(state_path), "--repo-root", str(self.repo)],
            cwd=str(self.repo), capture_output=True, text=True, check=False, env=env,
        )
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn("issues", res.stdout)
        self.assertFalse(sentinel.exists(), msg="gh was invoked despite --no-issues")


class TestCLIHelp(_RepoFixture):
    def test_help_exits_zero(self) -> None:
        res = subprocess.run(
            [str(_ARGOS_BIN), "sync", "--help"],
            cwd=str(self.repo), capture_output=True, text=True, check=False,
        )
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn("usage:", res.stdout)
        self.assertIn("--no-issues", res.stdout)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
