"""Tests for ARG1-068 ``argos sync --clean-queue``.

Each test that exercises ``git`` runs in a freshly-initialized temporary git
repo with the ARG1-032 pre-commit hook wired in, so the bypass discipline
(``ARGOS_CYCLE_CLOSE=1`` only on the structural commit) is verified
end-to-end. ADR-001 / ADR-002: stdlib only.

Runnable as::

    python3 -m unittest argos.cli.tests.test_clean_queue -v
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli.commands.clean_queue import (  # noqa: E402
    CleanQueueError,
    QueueSectionMissingError,
    clean_queue,
)
from argos.cli.queue import parse_queue  # noqa: E402

_ARGOS_BIN = Path(__file__).resolve().parents[1] / "argos"
_PRE_COMMIT_HOOK = (
    _REPO_ROOT / "argos" / "scripts" / "hooks" / "pre-commit-state-write.sh"
)


# Queue holds three shipped (ARG1-201/202 under live ## Done this cycle,
# ARG1-203 unshipped here) and two not-yet-shipped (ARG1-301/302) tickets.
# Ticket ids are numeric so they satisfy queue.TICKET_ID_RE.
_STATE_FIXTURE = """\
# Argos v1.0 — State

## Current focus

Cleaning queue.

## Queue

- ARG1-201 — shipped one (P0)
- ARG1-301 — still queued (P1)
- ARG1-202 — shipped two (P0)
- ARG1-203 — not shipped here (P2)
- ARG1-302 — still queued (P1)

## In progress

_none_

## Done this cycle

<!-- argos:entry id=2026-05-03T11:00:00Z-ARG1-201 ticket=ARG1-201 author=verifier session=sess-201 -->
- **[2026-05-03T11:00:00Z] ARG1-201 — verified**
  - Decision: pass
<!-- /argos:entry -->

<!-- argos:entry id=2026-05-03T11:05:00Z-ARG1-202 ticket=ARG1-202 author=verifier session=sess-202 -->
- **[2026-05-03T11:05:00Z] ARG1-202 — verified**
  - Decision: pass
<!-- /argos:entry -->

## Known drift

_none_
"""


# Queue lists ARG1-203 (shipped only in the cycle archive, not in live Done)
# plus ARG1-301 (unshipped). Live Done is empty.
_STATE_FIXTURE_ARCHIVE_ONLY = """\
# Argos v1.0 — State

## Current focus

Cleaning queue from archive.

## Queue

- ARG1-203 — shipped, archived (P0)
- ARG1-301 — still queued (P1)

## In progress

_none_

## Done this cycle

_none_

## Known drift

_none_
"""


_CYCLE_ARCHIVE = """\
# Argos cycle archive — 2026-05-02

<!-- argos:entry id=2026-05-02T09:00:00Z-ARG1-203 ticket=ARG1-203 author=verifier session=sess-203 -->
- **[2026-05-02T09:00:00Z] ARG1-203 — verified**
  - Decision: pass
<!-- /argos:entry -->
"""


_STATE_FIXTURE_EMPTY_QUEUE = """\
# Argos v1.0 — State

## Current focus

Empty queue.

## Queue

_(populated as tickets are queued for dispatch; orchestrator reads this section)_

## In progress

_none_

## Done this cycle

_none_

## Known drift

_none_
"""


_STATE_FIXTURE_NO_QUEUE_HEADING = """\
# Argos v1.0 — State

## Current focus

No queue heading.

## In progress

_none_

## Done this cycle

_none_

## Known drift

_none_
"""


def _git(args: list, *, cwd: Path, env: "dict | None" = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
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


def _install_pre_commit_hook(repo: Path) -> None:
    git_dir = _git_check(["rev-parse", "--git-dir"], cwd=repo).stdout.strip()
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


def _seed_state(repo: Path, fixture: str, *, archive: "str | None" = None) -> Path:
    """Seed STATE.md + cycles/ then install the pre-commit hook.

    Order matters: the ARG1-032 hook would reject the initial commit (which
    introduces non-block prose lines such as the H1 and section headings).
    Tests that exercise the hook install it after the seed is committed.
    """
    state_dir = repo / "argos" / "specs" / "v1.0"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "STATE.md"
    state_path.write_text(fixture, encoding="utf-8")
    cycles_dir = repo / "argos" / "specs" / "cycles"
    cycles_dir.mkdir(parents=True, exist_ok=True)
    (cycles_dir / ".gitkeep").write_text("", encoding="utf-8")
    add_paths = ["argos/specs/v1.0/STATE.md", "argos/specs/cycles/.gitkeep"]
    if archive is not None:
        (cycles_dir / "2026-05-02.md").write_text(archive, encoding="utf-8")
        add_paths.append("argos/specs/cycles/2026-05-02.md")
    _git_check(["add", *add_paths], cwd=repo)
    _git_check(["commit", "-q", "-m", "seed state"], cwd=repo)
    _install_pre_commit_hook(repo)
    return state_path


class _RepoFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name).resolve()
        _init_repo(self.repo)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @property
    def cycles_dir(self) -> Path:
        return self.repo / "argos" / "specs" / "cycles"


class TestRemovesExactlyShipped(_RepoFixture):
    """AC#2 — remove shipped queue entries, leave unshipped ones."""

    def test_removes_done_section_shipped_keeps_unshipped(self) -> None:
        state_path = _seed_state(self.repo, _STATE_FIXTURE)

        result = clean_queue(
            state_file=state_path,
            cycles_dir=self.cycles_dir,
            repo_root=self.repo,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.committed)
        # ARG1-201, ARG1-202 are in live Done this cycle; ARG1-203 is not
        # shipped anywhere here, so it stays.
        self.assertEqual(sorted(result.removed_ids), ["ARG1-201", "ARG1-202"])

        remaining = parse_queue(state_path.read_text(encoding="utf-8"))
        self.assertEqual(remaining, ["ARG1-301", "ARG1-203", "ARG1-302"])

    def test_archive_only_shipped_is_removed(self) -> None:
        state_path = _seed_state(
            self.repo, _STATE_FIXTURE_ARCHIVE_ONLY, archive=_CYCLE_ARCHIVE
        )

        result = clean_queue(
            state_file=state_path,
            cycles_dir=self.cycles_dir,
            repo_root=self.repo,
        )

        self.assertIsNotNone(result)
        assert result is not None
        # ARG1-203 shipped only via the cycle archive; ARG1-301 stays.
        self.assertEqual(result.removed_ids, ["ARG1-203"])
        remaining = parse_queue(state_path.read_text(encoding="utf-8"))
        self.assertEqual(remaining, ["ARG1-301"])

    def test_non_shipped_block_lines_untouched(self) -> None:
        """Only the matched bullet lines are deleted; Done blocks survive."""
        state_path = _seed_state(self.repo, _STATE_FIXTURE)
        clean_queue(
            state_file=state_path,
            cycles_dir=self.cycles_dir,
            repo_root=self.repo,
        )
        new_state = state_path.read_text(encoding="utf-8")
        # The Done this cycle entries are unaffected.
        self.assertIn("ticket=ARG1-201", new_state)
        self.assertIn("ticket=ARG1-202", new_state)
        # The queue bullets for shipped tickets are gone.
        self.assertNotIn("- ARG1-201 — shipped one", new_state)
        self.assertNotIn("- ARG1-202 — shipped two", new_state)
        # Section headings preserved.
        for heading in ("## Queue", "## In progress", "## Done this cycle", "## Known drift"):
            self.assertIn(heading, new_state)


class TestIdempotent(_RepoFixture):
    """AC#3 — second invocation is a no-op."""

    def test_second_run_no_op(self) -> None:
        state_path = _seed_state(self.repo, _STATE_FIXTURE)

        clean_queue(
            state_file=state_path,
            cycles_dir=self.cycles_dir,
            repo_root=self.repo,
        )
        head_after_first = _git_check(
            ["rev-parse", "HEAD"], cwd=self.repo
        ).stdout.strip()

        result2 = clean_queue(
            state_file=state_path,
            cycles_dir=self.cycles_dir,
            repo_root=self.repo,
        )
        self.assertIsNone(result2)

        head_after_second = _git_check(
            ["rev-parse", "HEAD"], cwd=self.repo
        ).stdout.strip()
        self.assertEqual(head_after_first, head_after_second)


class TestCommitBypass(_RepoFixture):
    """AC#4 — exactly one commit; the deletion needs the hook bypass."""

    def test_single_commit_message_and_count(self) -> None:
        state_path = _seed_state(self.repo, _STATE_FIXTURE)
        head_before = _git_check(["rev-parse", "HEAD"], cwd=self.repo).stdout.strip()

        clean_queue(
            state_file=state_path,
            cycles_dir=self.cycles_dir,
            repo_root=self.repo,
        )

        head_after = _git_check(["rev-parse", "HEAD"], cwd=self.repo).stdout.strip()
        self.assertNotEqual(head_before, head_after)
        count = _git_check(
            ["rev-list", "--count", f"{head_before}..{head_after}"], cwd=self.repo
        ).stdout.strip()
        self.assertEqual(count, "1")
        message = _git_check(
            ["log", "-1", "--pretty=%s", head_after], cwd=self.repo
        ).stdout.strip()
        self.assertEqual(
            message, "clean queue: remove 2 shipped ticket(s)"
        )

    def test_queue_deletion_commits_clean_without_bypass(self) -> None:
        """A ## Queue bullet deletion commits cleanly with no bypass (ARG1-078).

        ARG1-078 made ## Queue an operator-managed section exempt from the
        append-only rule, so removing a shipped ticket's queue bullet no longer
        needs ARGOS_CYCLE_CLOSE. (Pre-ARG1-078 the hook rejected this; this test
        previously asserted that rejection. clean_queue still sets the bypass on
        its commit, which is now belt-and-suspenders for the Queue-only edit.)"""
        state_path = _seed_state(self.repo, _STATE_FIXTURE)

        original = state_path.read_text(encoding="utf-8")
        truncated = original.replace("- ARG1-201 — shipped one (P0)\n", "")
        self.assertNotEqual(original, truncated)
        state_path.write_text(truncated, encoding="utf-8")
        _git_check(["add", "argos/specs/v1.0/STATE.md"], cwd=self.repo)

        env_no_bypass = os.environ.copy()
        env_no_bypass.pop("ARGOS_CYCLE_CLOSE", None)
        res = _git(
            ["commit", "-m", "queue cleanup"], cwd=self.repo, env=env_no_bypass
        )
        self.assertEqual(res.returncode, 0, res.stderr)


class TestAtomicRewrite(_RepoFixture):
    """AC#5 — atomic tempfile + os.replace; no torn write left behind."""

    def test_no_temp_files_remain_after_write(self) -> None:
        state_path = _seed_state(self.repo, _STATE_FIXTURE)
        clean_queue(
            state_file=state_path,
            cycles_dir=self.cycles_dir,
            repo_root=self.repo,
        )
        leftovers = [
            p.name
            for p in state_path.parent.iterdir()
            if p.name.startswith("STATE.md.tmp.")
        ]
        self.assertEqual(leftovers, [])
        # File is whole and parses cleanly.
        remaining = parse_queue(state_path.read_text(encoding="utf-8"))
        self.assertEqual(remaining, ["ARG1-301", "ARG1-203", "ARG1-302"])


class TestDryRun(_RepoFixture):
    """AC#6 — --dry-run prints intent and changes nothing."""

    def test_dry_run_no_write_no_commit(self) -> None:
        state_path = _seed_state(self.repo, _STATE_FIXTURE)
        before = state_path.read_text(encoding="utf-8")
        head_before = _git_check(["rev-parse", "HEAD"], cwd=self.repo).stdout.strip()

        result = clean_queue(
            state_file=state_path,
            cycles_dir=self.cycles_dir,
            repo_root=self.repo,
            dry_run=True,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.committed)
        self.assertEqual(sorted(result.removed_ids), ["ARG1-201", "ARG1-202"])

        self.assertEqual(state_path.read_text(encoding="utf-8"), before)
        head_after = _git_check(["rev-parse", "HEAD"], cwd=self.repo).stdout.strip()
        self.assertEqual(head_before, head_after)


class TestEmptyQueueNoOp(_RepoFixture):
    """AC#7 — empty queue → no-op, no commit."""

    def test_placeholder_only_queue_is_noop(self) -> None:
        state_path = _seed_state(self.repo, _STATE_FIXTURE_EMPTY_QUEUE)
        head_before = _git_check(["rev-parse", "HEAD"], cwd=self.repo).stdout.strip()

        result = clean_queue(
            state_file=state_path,
            cycles_dir=self.cycles_dir,
            repo_root=self.repo,
        )
        self.assertIsNone(result)
        head_after = _git_check(["rev-parse", "HEAD"], cwd=self.repo).stdout.strip()
        self.assertEqual(head_before, head_after)


class TestQueueSectionMissing(_RepoFixture):
    def test_missing_queue_heading_errors(self) -> None:
        state_path = _seed_state(self.repo, _STATE_FIXTURE_NO_QUEUE_HEADING)
        with self.assertRaises(QueueSectionMissingError):
            clean_queue(
                state_file=state_path,
                cycles_dir=self.cycles_dir,
                repo_root=self.repo,
            )


class TestCLI(_RepoFixture):
    """AC#1 / AC#6 / AC#7 surfaced through the real ``argos`` launcher."""

    def test_help_exits_zero(self) -> None:
        res = subprocess.run(
            [str(_ARGOS_BIN), "sync", "--clean-queue", "--help"],
            cwd=str(self.repo),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn("usage:", res.stdout)
        self.assertIn("clean-queue", res.stdout)

    def test_cli_dry_run(self) -> None:
        state_path = _seed_state(self.repo, _STATE_FIXTURE)
        before = state_path.read_text(encoding="utf-8")
        res = subprocess.run(
            [
                str(_ARGOS_BIN), "sync", "--clean-queue", "--dry-run",
                "--state-file", str(state_path),
                "--cycles-dir", str(self.cycles_dir),
                "--repo-root", str(self.repo),
            ],
            cwd=str(self.repo),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn("would remove 2 shipped ticket", res.stdout)
        self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_cli_empty_queue_prints_nothing_to_clean(self) -> None:
        state_path = _seed_state(self.repo, _STATE_FIXTURE_EMPTY_QUEUE)
        res = subprocess.run(
            [
                str(_ARGOS_BIN), "sync", "--clean-queue",
                "--state-file", str(state_path),
                "--cycles-dir", str(self.cycles_dir),
                "--repo-root", str(self.repo),
            ],
            cwd=str(self.repo),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertEqual(res.stdout.strip(), "nothing to clean")

    def test_cli_real_run_commits(self) -> None:
        state_path = _seed_state(self.repo, _STATE_FIXTURE)
        res = subprocess.run(
            [
                str(_ARGOS_BIN), "sync", "--clean-queue",
                "--state-file", str(state_path),
                "--cycles-dir", str(self.cycles_dir),
                "--repo-root", str(self.repo),
            ],
            cwd=str(self.repo),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn("removed 2 shipped ticket", res.stdout)
        remaining = parse_queue(state_path.read_text(encoding="utf-8"))
        self.assertEqual(remaining, ["ARG1-301", "ARG1-203", "ARG1-302"])


class TestMalformedArchive(_RepoFixture):
    def test_malformed_archive_raises(self) -> None:
        bad_archive = (
            "<!-- argos:entry id=x ticket=ARG1-Z author=verifier session=s -->\n"
            "- unclosed block, no end tag\n"
        )
        state_path = _seed_state(
            self.repo, _STATE_FIXTURE_ARCHIVE_ONLY, archive=bad_archive
        )
        with self.assertRaises(CleanQueueError):
            clean_queue(
                state_file=state_path,
                cycles_dir=self.cycles_dir,
                repo_root=self.repo,
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
