"""Tests for ARG1-054 ``argos sync --close-cycle``.

Each test that exercises ``git`` runs in a freshly-initialized temporary
git repo with the ARG1-032 pre-commit hook wired in, so the bypass
discipline (``ARGOS_CYCLE_CLOSE=1`` only on the structural commit) is
verified end-to-end. ADR-001 / ADR-002: stdlib only.

Runnable as::

    python3 -m unittest argos.cli.tests.test_cycle_close -v
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli.commands.cycle_close import (  # noqa: E402
    CycleCloseError,
    SectionNotFoundError,
    close_cycle,
)
from argos.cli.state_parser import parse as parse_state  # noqa: E402

_ARGOS_BIN = Path(__file__).resolve().parents[1] / "argos"
_PRE_COMMIT_HOOK = (
    _REPO_ROOT / "argos" / "scripts" / "hooks" / "pre-commit-state-write.sh"
)


_STATE_FIXTURE_THREE = """\
# Argos v1.0 — State

## Current focus

Closing cycle.

## Queue

_(populated as tickets are queued for dispatch)_

## In progress

<!-- argos:entry id=2026-05-03T10:00:00Z-ARG1-IP1 ticket=ARG1-IP1 author=verifier session=sess-ip1 -->
- **[2026-05-03T10:00:00Z] ARG1-IP1 — in progress** (in flight, do not archive)
<!-- /argos:entry -->

## Done this cycle

<!-- argos:entry id=2026-05-03T11:00:00Z-ARG1-A1 ticket=ARG1-A1 author=verifier session=sess-a1 -->
- **[2026-05-03T11:00:00Z] ARG1-A1 — verified**
  - Decision: pass
<!-- /argos:entry -->

<!-- argos:entry id=2026-05-03T11:05:00Z-ARG1-A2 ticket=ARG1-A2 author=verifier session=sess-a2 -->
- **[2026-05-03T11:05:00Z] ARG1-A2 — verified**
  - Decision: pass
<!-- /argos:entry -->

<!-- argos:entry id=2026-05-03T11:10:00Z-ARG1-A3 ticket=ARG1-A3 author=verifier session=sess-a3 -->
- **[2026-05-03T11:10:00Z] ARG1-A3 — verified**
  - Decision: pass
<!-- /argos:entry -->

## Known drift

_none_
"""


_STATE_FIXTURE_EMPTY_DONE = """\
# Argos v1.0 — State

## Current focus

Empty.

## In progress

_none_

## Done this cycle

_none_

## Known drift

_none_
"""


_STATE_FIXTURE_NO_DONE_HEADING = """\
# Argos v1.0 — State

## Current focus

Empty.

## In progress

_none_

## Known drift

_none_
"""


def _git(args: list[str], *, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _git_check(args: list[str], *, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
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


def _seed_state(repo: Path, fixture: str) -> Path:
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
    _git_check(
        [
            "add",
            "argos/specs/v1.0/STATE.md",
            "argos/specs/cycles/.gitkeep",
        ],
        cwd=repo,
    )
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


class TestCloseCycleArchives(_RepoFixture):
    """AC#1, AC#2, AC#3 — happy-path archive + STATE clear."""

    def test_three_blocks_archived_and_section_cleared(self) -> None:
        state_path = _seed_state(self.repo, _STATE_FIXTURE_THREE)
        cycles_dir = self.repo / "argos" / "specs" / "cycles"

        result = close_cycle(
            state_file=state_path,
            cycles_dir=cycles_dir,
            repo_root=self.repo,
            now=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.archived_count, 3)
        self.assertTrue(result.committed)

        # AC#1: cycle archive contains all three blocks verbatim.
        cycle_file = cycles_dir / "2026-05-03.md"
        self.assertTrue(cycle_file.is_file())
        archive_text = cycle_file.read_text(encoding="utf-8")
        self.assertEqual(archive_text.count("<!-- argos:entry"), 3)
        for ticket_id in ("ARG1-A1", "ARG1-A2", "ARG1-A3"):
            self.assertIn(f"ticket={ticket_id}", archive_text)

        # AC#2: STATE.md '## Done this cycle' is empty between headings.
        new_state = state_path.read_text(encoding="utf-8")
        # Find Done this cycle heading and the next ## heading; assert
        # no <!-- argos:entry between them.
        m = re.search(
            r"(?ms)^## Done this cycle\s*\n(?P<body>.*?)(?=^## )",
            new_state,
        )
        self.assertIsNotNone(m, "Done this cycle section heading missing after close")
        assert m is not None
        self.assertNotIn("<!-- argos:entry", m.group("body"))

        # Cross-check via the parser: no Done-this-cycle blocks remain.
        blocks = parse_state(new_state)
        body_text = m.group("body")
        # Compute heading line index (1-indexed) for the newly-cleared section.
        lines = new_state.splitlines()
        done_idx = next(
            i for i, ln in enumerate(lines) if ln.strip() == "## Done this cycle"
        )
        next_idx = next(
            (
                i for i in range(done_idx + 1, len(lines))
                if lines[i].startswith("## ")
            ),
            len(lines),
        )
        in_section = [
            b for b in blocks if done_idx < (b.start_line - 1) < next_idx
        ]
        self.assertEqual(in_section, [])

        # AC#3: '## In progress' block IDs unchanged.
        ip_blocks = [b for b in blocks if b.id.endswith("ARG1-IP1")]
        self.assertEqual(len(ip_blocks), 1)


class TestCloseCycleCommit(_RepoFixture):
    """AC#4 — exactly one commit, message format, hook bypass works."""

    def test_single_commit_with_expected_message(self) -> None:
        state_path = _seed_state(self.repo, _STATE_FIXTURE_THREE)
        cycles_dir = self.repo / "argos" / "specs" / "cycles"

        head_before = _git_check(
            ["rev-parse", "HEAD"], cwd=self.repo
        ).stdout.strip()

        close_cycle(
            state_file=state_path,
            cycles_dir=cycles_dir,
            repo_root=self.repo,
            now=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
        )

        head_after = _git_check(
            ["rev-parse", "HEAD"], cwd=self.repo
        ).stdout.strip()
        self.assertNotEqual(head_before, head_after)

        # Exactly one new commit between before and after.
        rev_list = _git_check(
            ["rev-list", "--count", f"{head_before}..{head_after}"],
            cwd=self.repo,
        ).stdout.strip()
        self.assertEqual(rev_list, "1")

        # Commit message matches the AC#4 regex.
        message = _git_check(
            ["log", "-1", "--pretty=%s", head_after], cwd=self.repo
        ).stdout.strip()
        self.assertRegex(message, r"^cycle close \d{4}-\d{2}-\d{2}$")
        self.assertEqual(message, "cycle close 2026-05-03")

    def test_hook_blocks_without_bypass_env(self) -> None:
        """The pre-commit hook *would* reject the deletion if cycle close
        skipped its bypass — sanity-check the gate is real."""
        state_path = _seed_state(self.repo, _STATE_FIXTURE_THREE)

        # Manually delete a block (the kind of edit cycle close performs).
        original = state_path.read_text(encoding="utf-8")
        truncated = re.sub(
            r"<!-- argos:entry id=2026-05-03T11:00:00Z-ARG1-A1[^>]*-->.*?<!-- /argos:entry -->\n",
            "",
            original,
            count=1,
            flags=re.DOTALL,
        )
        self.assertNotEqual(original, truncated)
        state_path.write_text(truncated, encoding="utf-8")
        _git_check(
            ["add", "argos/specs/v1.0/STATE.md"], cwd=self.repo
        )

        env_no_bypass = os.environ.copy()
        env_no_bypass.pop("ARGOS_CYCLE_CLOSE", None)
        res = _git(
            ["commit", "-m", "should fail"],
            cwd=self.repo,
            env=env_no_bypass,
        )
        self.assertNotEqual(res.returncode, 0)
        # Restore so tearDown doesn't see a dirty state.
        _git_check(
            ["checkout", "--", "argos/specs/v1.0/STATE.md"], cwd=self.repo
        )


class TestCloseCycleIdempotent(_RepoFixture):
    """AC#5 — second same-day run is a no-op."""

    def test_second_run_says_nothing_to_close_no_commit(self) -> None:
        state_path = _seed_state(self.repo, _STATE_FIXTURE_THREE)
        cycles_dir = self.repo / "argos" / "specs" / "cycles"
        now = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)

        close_cycle(
            state_file=state_path,
            cycles_dir=cycles_dir,
            repo_root=self.repo,
            now=now,
        )
        head_after_first = _git_check(
            ["rev-parse", "HEAD"], cwd=self.repo
        ).stdout.strip()

        # Second run: section is empty → returns None.
        result2 = close_cycle(
            state_file=state_path,
            cycles_dir=cycles_dir,
            repo_root=self.repo,
            now=now,
        )
        self.assertIsNone(result2)

        head_after_second = _git_check(
            ["rev-parse", "HEAD"], cwd=self.repo
        ).stdout.strip()
        self.assertEqual(head_after_first, head_after_second)

    def test_cli_prints_nothing_to_close(self) -> None:
        state_path = _seed_state(self.repo, _STATE_FIXTURE_EMPTY_DONE)

        res = subprocess.run(
            [
                str(_ARGOS_BIN),
                "sync",
                "--close-cycle",
                "--state-file",
                str(state_path),
                "--cycles-dir",
                str(self.repo / "argos" / "specs" / "cycles"),
                "--repo-root",
                str(self.repo),
            ],
            cwd=str(self.repo),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertEqual(res.stdout.strip(), "nothing to close")


class TestCloseCycleAppendsSameDay(_RepoFixture):
    """AC#6 — same-day re-close appends to the existing archive."""

    def test_second_close_same_day_appends_blocks(self) -> None:
        state_path = _seed_state(self.repo, _STATE_FIXTURE_THREE)
        cycles_dir = self.repo / "argos" / "specs" / "cycles"
        now = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)

        close_cycle(
            state_file=state_path,
            cycles_dir=cycles_dir,
            repo_root=self.repo,
            now=now,
        )
        cycle_file = cycles_dir / "2026-05-03.md"
        first_count = cycle_file.read_text(encoding="utf-8").count(
            "<!-- argos:entry"
        )
        self.assertEqual(first_count, 3)

        # Simulate another verifier appending two more blocks to the same
        # section after the first close. Use ARGOS_CYCLE_CLOSE=1 only as a
        # convenience here for the test seed; in production the verifier
        # would author them via state-append.
        cur = state_path.read_text(encoding="utf-8")
        addition = (
            "<!-- argos:entry id=2026-05-03T13:00:00Z-ARG1-A4 "
            "ticket=ARG1-A4 author=verifier session=sess-a4 -->\n"
            "- **[2026-05-03T13:00:00Z] ARG1-A4 — verified**\n"
            "  - Decision: pass\n"
            "<!-- /argos:entry -->\n\n"
            "<!-- argos:entry id=2026-05-03T13:05:00Z-ARG1-A5 "
            "ticket=ARG1-A5 author=verifier session=sess-a5 -->\n"
            "- **[2026-05-03T13:05:00Z] ARG1-A5 — verified**\n"
            "  - Decision: pass\n"
            "<!-- /argos:entry -->\n\n"
        )
        new_state = cur.replace(
            "## Done this cycle\n\n_none_\n\n",
            "## Done this cycle\n\n" + addition,
        )
        self.assertNotEqual(cur, new_state)
        state_path.write_text(new_state, encoding="utf-8")
        seed_env = os.environ.copy()
        seed_env["ARGOS_CYCLE_CLOSE"] = "1"
        _git_check(
            ["add", "argos/specs/v1.0/STATE.md"], cwd=self.repo
        )
        _git_check(
            ["commit", "-m", "seed extra blocks"],
            cwd=self.repo,
            env=seed_env,
        )

        # Second close on the same UTC day — must append, not overwrite.
        close_cycle(
            state_file=state_path,
            cycles_dir=cycles_dir,
            repo_root=self.repo,
            now=now,
        )
        second_count = cycle_file.read_text(encoding="utf-8").count(
            "<!-- argos:entry"
        )
        self.assertEqual(second_count, 5)


class TestCloseCycleDryRun(_RepoFixture):
    """AC#7 — --dry-run prints intent and changes nothing."""

    def test_dry_run_no_writes_no_commit(self) -> None:
        state_path = _seed_state(self.repo, _STATE_FIXTURE_THREE)
        cycles_dir = self.repo / "argos" / "specs" / "cycles"
        before_state = state_path.read_text(encoding="utf-8")
        before_files = sorted(p.name for p in cycles_dir.iterdir())

        head_before = _git_check(
            ["rev-parse", "HEAD"], cwd=self.repo
        ).stdout.strip()

        result = close_cycle(
            state_file=state_path,
            cycles_dir=cycles_dir,
            repo_root=self.repo,
            dry_run=True,
            now=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.committed)
        self.assertEqual(result.archived_count, 3)

        self.assertEqual(state_path.read_text(encoding="utf-8"), before_state)
        self.assertEqual(
            sorted(p.name for p in cycles_dir.iterdir()), before_files
        )

        head_after = _git_check(
            ["rev-parse", "HEAD"], cwd=self.repo
        ).stdout.strip()
        self.assertEqual(head_before, head_after)

    def test_cli_dry_run(self) -> None:
        state_path = _seed_state(self.repo, _STATE_FIXTURE_THREE)
        cycles_dir = self.repo / "argos" / "specs" / "cycles"
        before_state = state_path.read_text(encoding="utf-8")

        res = subprocess.run(
            [
                str(_ARGOS_BIN),
                "sync",
                "--close-cycle",
                "--dry-run",
                "--state-file",
                str(state_path),
                "--cycles-dir",
                str(cycles_dir),
                "--repo-root",
                str(self.repo),
            ],
            cwd=str(self.repo),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn("would archive 3 block", res.stdout)
        self.assertEqual(state_path.read_text(encoding="utf-8"), before_state)


class TestCloseCycleSectionMissing(_RepoFixture):
    def test_missing_section_errors(self) -> None:
        state_path = _seed_state(self.repo, _STATE_FIXTURE_NO_DONE_HEADING)
        cycles_dir = self.repo / "argos" / "specs" / "cycles"
        with self.assertRaises(SectionNotFoundError):
            close_cycle(
                state_file=state_path,
                cycles_dir=cycles_dir,
                repo_root=self.repo,
            )


class TestCloseCycleArchiveHeadingNotMatched(_RepoFixture):
    """The regex must NOT pick up '## Done this cycle (ARG1-001)' archives."""

    def test_archive_heading_with_suffix_is_skipped(self) -> None:
        fixture = (
            "# State\n\n"
            "## In progress\n\n_none_\n\n"
            "## Done this cycle\n\n"
            "<!-- argos:entry id=2026-05-03T11:00:00Z-ARG1-X ticket=ARG1-X "
            "author=verifier session=sess-x -->\n"
            "- body\n"
            "<!-- /argos:entry -->\n\n"
            "## Known drift\n\n_none_\n\n"
            "## Done this cycle (ARG1-001)\n\n"
            "<!-- argos:entry id=2026-04-26T15:45:00Z-ARG1-001-done "
            "ticket=ARG1-001 author=verifier session=arg1-001 -->\n"
            "- archived\n"
            "<!-- /argos:entry -->\n"
        )
        state_path = _seed_state(self.repo, fixture)
        cycles_dir = self.repo / "argos" / "specs" / "cycles"

        result = close_cycle(
            state_file=state_path,
            cycles_dir=cycles_dir,
            repo_root=self.repo,
            now=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
        )
        self.assertIsNotNone(result)
        assert result is not None
        # Only the live ## Done this cycle block should be archived; the
        # historical ## Done this cycle (ARG1-001) block must remain in
        # STATE.md untouched.
        self.assertEqual(result.archived_count, 1)
        new_state = state_path.read_text(encoding="utf-8")
        self.assertIn("ARG1-001-done", new_state)
        self.assertNotIn("ARG1-X", new_state.split("## Done this cycle (ARG1-001)")[0])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
