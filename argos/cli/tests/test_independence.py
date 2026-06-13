"""Tests for ARG1-066: merge-aware independence detection.

Supersedes ARG1-021's strict file-overlap tests. The strict-criterion library
and CLI tests are retained as the *static fallback* path (exercised when a
pair's ``argos/<id>`` branches do not exist), keeping their original intent
(AC#11). New ``MergeDryRunTests`` / ``CLIMergeTests`` cover the merge-dryrun
mechanism: merge-driver compatibility (AC#4), hook non-interaction (AC#5),
registration-pattern coverage (AC#6), depends_on precedence (AC#7), and
rollback discipline (AC#8).

Stdlib-only per ADR-001 / ADR-002 — :mod:`unittest`, :mod:`subprocess`,
:mod:`tempfile`, :mod:`json`, :mod:`pathlib`, :mod:`shutil`, :mod:`os`. No
third-party imports.

Runnable as::

    python3 -m unittest argos.cli.tests.test_independence -v
"""

from __future__ import annotations

import json
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

from argos.cli.orchestrator.independence import (  # noqa: E402
    DEFAULT_TICKET_DIR,
    MergeStagingArea,
    MissingFilesTouchedError,
    Ticket,
    TicketNotFoundError,
    compute_branch_name,
    is_independent,
    load_ticket,
    partition,
)


_ARGOS_BIN = Path(__file__).resolve().parents[1] / "argos"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_ARGOS_BIN), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _write_ticket(
    ticket_dir: Path,
    ticket_id: str,
    *,
    files_touched: list[str] | None,
    depends_on: list[str] | None = None,
    extra_plan: str = "",
    flow_depends_on: bool = False,
    omit_plan: bool = False,
) -> Path:
    """Write a synthetic ticket file to ``ticket_dir/<id>-test.md``.

    ``files_touched=None`` simulates a Plan section that does not declare
    the field. ``omit_plan=True`` simulates a ticket without a ``## Plan``
    heading at all (also a missing-field condition).
    """
    fm_lines = [
        "---",
        f"ticket_id: {ticket_id}",
    ]
    if depends_on is not None:
        if flow_depends_on:
            fm_lines.append(
                "depends_on: [" + ", ".join(depends_on) + "]"
            )
        else:
            if depends_on:
                fm_lines.append("depends_on:")
                for d in depends_on:
                    fm_lines.append(f"  - {d}")
            else:
                fm_lines.append("depends_on:")
    fm_lines.append("---")
    body: list[str] = []
    body.extend(fm_lines)
    body.append("")
    body.append(f"# {ticket_id} — synthetic test ticket")
    body.append("")
    body.append("## Intent")
    body.append("")
    body.append("Synthetic.")
    body.append("")
    if not omit_plan:
        body.append("## Plan")
        body.append("")
        if files_touched is not None:
            body.append("files_touched:")
            for f in files_touched:
                body.append(f"  - {f}")
            body.append("")
        if extra_plan:
            body.append(extra_plan)
            body.append("")
    path = ticket_dir / f"{ticket_id}-test.md"
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Library API tests
# ---------------------------------------------------------------------------


class LoadTicketTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tdir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_loads_files_touched_block_sequence(self) -> None:
        _write_ticket(
            self.tdir,
            "ARG1-099",
            files_touched=["argos/cli/foo.py", "argos/cli/bar.py"],
        )
        t = load_ticket("ARG1-099", self.tdir)
        self.assertEqual(t.ticket_id, "ARG1-099")
        self.assertEqual(
            t.files_touched, ("argos/cli/foo.py", "argos/cli/bar.py")
        )
        self.assertEqual(t.depends_on, ())

    def test_loads_depends_on_flow_style(self) -> None:
        _write_ticket(
            self.tdir,
            "ARG1-102",
            files_touched=["argos/cli/baz.py"],
            depends_on=["ARG1-099"],
            flow_depends_on=True,
        )
        t = load_ticket("ARG1-102", self.tdir)
        self.assertEqual(t.depends_on, ("ARG1-099",))

    def test_loads_depends_on_block_sequence(self) -> None:
        _write_ticket(
            self.tdir,
            "ARG1-200",
            files_touched=["a.py"],
            depends_on=["ARG1-100", "ARG1-101"],
        )
        t = load_ticket("ARG1-200", self.tdir)
        self.assertEqual(t.depends_on, ("ARG1-100", "ARG1-101"))

    def test_missing_files_touched_raises(self) -> None:
        _write_ticket(self.tdir, "ARG1-300", files_touched=None)
        with self.assertRaises(MissingFilesTouchedError) as cm:
            load_ticket("ARG1-300", self.tdir)
        self.assertEqual(cm.exception.ticket_id, "ARG1-300")
        self.assertIn("missing files_touched", str(cm.exception))

    def test_missing_plan_section_raises(self) -> None:
        _write_ticket(
            self.tdir, "ARG1-301", files_touched=["x.py"], omit_plan=True
        )
        with self.assertRaises(MissingFilesTouchedError):
            load_ticket("ARG1-301", self.tdir)

    def test_ticket_not_found_raises(self) -> None:
        with self.assertRaises(TicketNotFoundError):
            load_ticket("ARG1-999", self.tdir)

    def test_empty_files_touched_is_valid(self) -> None:
        _write_ticket(self.tdir, "ARG1-400", files_touched=[])
        t = load_ticket("ARG1-400", self.tdir)
        self.assertEqual(t.files_touched, ())

    def test_extra_plan_content_does_not_swallow_files_touched(self) -> None:
        # A files_touched block followed by a normal "Files touched" table
        # must still parse cleanly — the table is human-readable prose, not
        # a continuation of the block sequence.
        _write_ticket(
            self.tdir,
            "ARG1-410",
            files_touched=["argos/cli/foo.py"],
            extra_plan=(
                "### Files touched (table)\n"
                "\n"
                "| Path | Status |\n"
                "|------|--------|\n"
                "| argos/cli/foo.py | new |\n"
            ),
        )
        t = load_ticket("ARG1-410", self.tdir)
        self.assertEqual(t.files_touched, ("argos/cli/foo.py",))


class IsIndependentTests(unittest.TestCase):
    def _t(
        self,
        tid: str,
        files: list[str],
        depends_on: list[str] | None = None,
    ) -> Ticket:
        return Ticket(
            ticket_id=tid,
            path=Path(f"/tmp/{tid}.md"),
            depends_on=tuple(depends_on or ()),
            files_touched=tuple(files),
        )

    def test_disjoint_files_no_depends_on_independent(self) -> None:
        a = self._t("ARG1-099", ["argos/cli/a.py"])
        b = self._t("ARG1-100", ["argos/cli/b.py"])
        r = is_independent(a, b)
        self.assertTrue(r.independent)
        self.assertEqual(r.reason, "")

    def test_shared_file_dependent(self) -> None:
        a = self._t("ARG1-099", ["argos/cli/a.py"])
        b = self._t("ARG1-101", ["argos/cli/a.py", "argos/cli/c.py"])
        r = is_independent(a, b)
        self.assertFalse(r.independent)
        self.assertIn("shared file", r.reason)
        self.assertIn("argos/cli/a.py", r.reason)
        self.assertEqual(r.shared_files, ("argos/cli/a.py",))

    def test_depends_on_dependent(self) -> None:
        a = self._t("ARG1-099", ["argos/cli/a.py"])
        b = self._t("ARG1-102", ["argos/cli/d.py"], depends_on=["ARG1-099"])
        r = is_independent(a, b)
        self.assertFalse(r.independent)
        self.assertEqual(r.reason, "depends_on")

    def test_reverse_depends_on_dependent(self) -> None:
        # B → A direction also catches dependence.
        a = self._t("ARG1-099", ["argos/cli/a.py"], depends_on=["ARG1-100"])
        b = self._t("ARG1-100", ["argos/cli/b.py"])
        r = is_independent(a, b)
        self.assertFalse(r.independent)
        self.assertEqual(r.reason, "depends_on")

    def test_depends_on_takes_priority_over_shared_file(self) -> None:
        # When both conditions fail, the reason is depends_on (deterministic).
        a = self._t("ARG1-099", ["argos/cli/a.py"])
        b = self._t(
            "ARG1-100", ["argos/cli/a.py"], depends_on=["ARG1-099"]
        )
        r = is_independent(a, b)
        self.assertFalse(r.independent)
        self.assertEqual(r.reason, "depends_on")


class PartitionTests(unittest.TestCase):
    def _t(
        self,
        tid: str,
        files: list[str],
        depends_on: list[str] | None = None,
    ) -> Ticket:
        return Ticket(
            ticket_id=tid,
            path=Path(f"/tmp/{tid}.md"),
            depends_on=tuple(depends_on or ()),
            files_touched=tuple(files),
        )

    def test_three_independent_one_group(self) -> None:
        ts = [
            self._t("ARG1-099", ["a.py"]),
            self._t("ARG1-100", ["b.py"]),
            self._t("ARG1-101", ["c.py"]),
        ]
        groups = partition(ts)
        self.assertEqual(groups, [["ARG1-099", "ARG1-100", "ARG1-101"]])

    def test_two_share_third_independent(self) -> None:
        # ARG1-099 and ARG1-100 share a.py; ARG1-101 is disjoint with both.
        ts = [
            self._t("ARG1-099", ["a.py"]),
            self._t("ARG1-100", ["a.py"]),
            self._t("ARG1-101", ["c.py"]),
        ]
        groups = partition(ts)
        # Greedy first-fit: 099 opens grp1; 100 conflicts with grp1 so opens
        # grp2; 101 is independent of 099, joins grp1.
        self.assertEqual(
            sorted(g for g in groups[0]), ["ARG1-099", "ARG1-101"]
        )
        self.assertEqual(groups[1], ["ARG1-100"])
        self.assertEqual(len(groups), 2)

    def test_chain_depends_on(self) -> None:
        # 100 depends_on 099; 101 depends_on 100. Three serial groups.
        ts = [
            self._t("ARG1-099", ["a.py"]),
            self._t("ARG1-100", ["b.py"], depends_on=["ARG1-099"]),
            self._t("ARG1-101", ["c.py"], depends_on=["ARG1-100"]),
        ]
        groups = partition(ts)
        # 100 conflicts with 099 → grp2; 101 conflicts with 100, fits with
        # 099 → joins grp1.
        self.assertEqual(len(groups), 2)
        self.assertEqual(
            sorted(groups[0]), ["ARG1-099", "ARG1-101"]
        )
        self.assertEqual(groups[1], ["ARG1-100"])

    def test_deterministic(self) -> None:
        ts = [
            self._t("ARG1-099", ["a.py"]),
            self._t("ARG1-100", ["b.py"]),
            self._t("ARG1-101", ["a.py"]),
        ]
        self.assertEqual(partition(ts), partition(ts))


# ---------------------------------------------------------------------------
# CLI / Acceptance-criteria tests
# ---------------------------------------------------------------------------


class CLIAcceptanceTests(unittest.TestCase):
    """Live CLI invocations covering every ARG1-021 acceptance criterion."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tdir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        # Three synthetic tickets used across the AC tests.
        # ARG1-099: touches argos/cli/a.py
        # ARG1-100: touches argos/cli/b.py (disjoint with 099)
        # ARG1-101: touches argos/cli/a.py (shares with 099)
        # ARG1-102: depends_on [ARG1-099], disjoint files (per AC#3 literal)
        _write_ticket(self.tdir, "ARG1-099", files_touched=["argos/cli/a.py"])
        _write_ticket(self.tdir, "ARG1-100", files_touched=["argos/cli/b.py"])
        _write_ticket(self.tdir, "ARG1-101", files_touched=["argos/cli/a.py"])
        _write_ticket(
            self.tdir,
            "ARG1-102",
            files_touched=["argos/cli/d.py"],
            depends_on=["ARG1-099"],
            flow_depends_on=True,
        )

    def _cli(self, *args: str) -> subprocess.CompletedProcess:
        return _run_cli(
            "independence", "--ticket-dir", str(self.tdir), *args
        )

    # AC#1
    def test_ac1_disjoint_files_independent(self) -> None:
        r = self._cli("ARG1-099", "ARG1-100")
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertIn("independent", r.stdout)

    # AC#2
    def test_ac2_shared_file_dependent_names_path(self) -> None:
        r = self._cli("ARG1-099", "ARG1-101")
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertIn("dependent", r.stdout)
        self.assertIn("argos/cli/a.py", r.stdout)

    # AC#3
    def test_ac3_depends_on_dependent(self) -> None:
        r = self._cli("ARG1-099", "ARG1-102")
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertIn("dependent", r.stdout)
        self.assertIn("depends_on", r.stdout)

    # AC#4
    def test_ac4_missing_files_touched_errors(self) -> None:
        _write_ticket(self.tdir, "ARG1-300", files_touched=None)
        r = self._cli("ARG1-099", "ARG1-300")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ARG1-300", r.stderr)
        self.assertIn("missing files_touched", r.stderr)

    # AC#5
    def test_ac5_json_groups_key(self) -> None:
        r = self._cli("--json", "ARG1-099", "ARG1-100", "ARG1-101")
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        payload = json.loads(r.stdout)
        self.assertIn("groups", payload)
        self.assertIsInstance(payload["groups"], list)
        for grp in payload["groups"]:
            self.assertIsInstance(grp, list)
            for tid in grp:
                self.assertIsInstance(tid, str)
        # Sanity check: 099 and 101 share a file, so they cannot share a group.
        groups_with_099 = [g for g in payload["groups"] if "ARG1-099" in g]
        self.assertEqual(len(groups_with_099), 1)
        self.assertNotIn("ARG1-101", groups_with_099[0])

    # AC#6
    def test_ac6_planner_md_contains_files_touched_literal(self) -> None:
        planner_path = (
            _REPO_ROOT / ".claude" / "agents" / "planner.md"
        )
        body = planner_path.read_text(encoding="utf-8")
        self.assertIn("files_touched:", body)


class CLIRoundTripTests(unittest.TestCase):
    """Cross-cutting CLI behavior beyond the literal ACs."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tdir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        _write_ticket(self.tdir, "ARG1-099", files_touched=["a.py"])
        _write_ticket(self.tdir, "ARG1-100", files_touched=["b.py"])

    def test_no_args_exits_2(self) -> None:
        r = _run_cli("independence")
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage", r.stderr.lower())

    def test_unknown_ticket_exits_2(self) -> None:
        r = _run_cli(
            "independence", "--ticket-dir", str(self.tdir), "ARG1-999"
        )
        self.assertEqual(r.returncode, 2)
        self.assertIn("ticket not found", r.stderr)

    def test_subcommand_in_main_help(self) -> None:
        r = _run_cli("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("independence", r.stdout)


class PlannerMirrorTests(unittest.TestCase):
    """Mirror invariant: .claude/agents/planner.md == argos/specs/v1.0/agents/planner.md."""

    def test_mirror_is_byte_identical(self) -> None:
        a = (_REPO_ROOT / ".claude" / "agents" / "planner.md").read_bytes()
        b = (
            _REPO_ROOT / "argos" / "specs" / "v1.0" / "agents" / "planner.md"
        ).read_bytes()
        self.assertEqual(a, b)

    def test_specs_mirror_contains_files_touched(self) -> None:
        b = (
            _REPO_ROOT / "argos" / "specs" / "v1.0" / "agents" / "planner.md"
        ).read_text(encoding="utf-8")
        self.assertIn("files_touched:", b)


# ---------------------------------------------------------------------------
# Merge-dryrun mechanism (ARG1-066) — real git repos with real branches
# ---------------------------------------------------------------------------


_REAL_DRIVER = (
    _REPO_ROOT / "argos" / "scripts" / "state-merge-driver.sh"
)


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    res = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and res.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed: {res.stderr or res.stdout}"
        )
    return res


def _init_repo(repo: Path) -> None:
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(repo)],
        check=True,
        capture_output=True,
    )
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")


def _write(repo: Path, rel: str, content: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _commit_all(repo: Path, msg: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", msg)


def _branch_with(repo: Path, ticket_id: str, files: dict, msg: str, base: str = "main") -> None:
    """Create branch ``argos/<ticket_id>`` off ``base`` with ``files`` written."""
    _git(repo, "checkout", "-q", base)
    _git(repo, "checkout", "-q", "-b", compute_branch_name(ticket_id))
    for rel, content in files.items():
        _write(repo, rel, content)
    _commit_all(repo, msg)
    _git(repo, "checkout", "-q", base)


def _T(ticket_id: str, files=(), depends_on=()) -> Ticket:
    return Ticket(
        ticket_id=ticket_id,
        path=Path(f"/tmp/{ticket_id}.md"),
        depends_on=tuple(depends_on),
        files_touched=tuple(files),
    )


class MergeDryRunTests(unittest.TestCase):
    """The merge-aware criterion against real branches in a real repo."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        _init_repo(self.repo)
        # A __main__.py-style registration file at distinct line ranges.
        _write(self.repo, "argos/cli/reg.py", "one\ntwo\nthree\n")
        _commit_all(self.repo, "seed")

    # AC#6 — registration-pattern coverage (the case strict got wrong).
    def test_registration_pattern_independent(self) -> None:
        _branch_with(self.repo, "ARG1-201", {"argos/cli/reg.py": "one\ntwo\nthree\nFOUR\n"}, "add four")
        _branch_with(self.repo, "ARG1-202", {"argos/cli/reg.py": "ZERO\none\ntwo\nthree\n"}, "add zero")
        r = is_independent(_T("ARG1-201"), _T("ARG1-202"), repo_root=self.repo)
        self.assertTrue(r.independent, msg=r.reason)
        self.assertEqual(r.reason, "")

    def test_same_line_edit_conflicts_dependent(self) -> None:
        _branch_with(self.repo, "ARG1-203", {"argos/cli/reg.py": "one\nTWO-A\nthree\n"}, "edit two A")
        _branch_with(self.repo, "ARG1-204", {"argos/cli/reg.py": "one\nTWO-B\nthree\n"}, "edit two B")
        r = is_independent(_T("ARG1-203"), _T("ARG1-204"), repo_root=self.repo)
        self.assertFalse(r.independent)
        self.assertIn("merge conflict", r.reason)
        self.assertIn("argos/cli/reg.py", r.reason)
        self.assertEqual(r.shared_files, ("argos/cli/reg.py",))

    def test_disjoint_files_independent(self) -> None:
        _branch_with(self.repo, "ARG1-205", {"argos/cli/p205.py": "a\n"}, "p205")
        _branch_with(self.repo, "ARG1-206", {"argos/cli/p206.py": "b\n"}, "p206")
        r = is_independent(_T("ARG1-205"), _T("ARG1-206"), repo_root=self.repo)
        self.assertTrue(r.independent, msg=r.reason)

    # AC#7 — depends_on is the cheap first pass: declared dependency wins even
    # when the branches themselves would merge cleanly (no dry-run consulted).
    def test_depends_on_precedes_merge(self) -> None:
        _branch_with(self.repo, "ARG1-207", {"argos/cli/p207.py": "a\n"}, "p207")
        _branch_with(self.repo, "ARG1-208", {"argos/cli/p208.py": "b\n"}, "p208")
        # Disjoint files → would be merge-clean, but B depends_on A.
        r = is_independent(
            _T("ARG1-207"),
            _T("ARG1-208", depends_on=["ARG1-207"]),
            repo_root=self.repo,
        )
        self.assertFalse(r.independent)
        self.assertEqual(r.reason, "depends_on")

    # Lifecycle: a missing branch degrades to the strict file-set criterion.
    def test_missing_branch_falls_back_to_static_independent(self) -> None:
        _branch_with(self.repo, "ARG1-209", {"argos/cli/p209.py": "a\n"}, "p209")
        # ARG1-210 has no branch → static fallback over files_touched (disjoint).
        r = is_independent(
            _T("ARG1-209", files=["x.py"]),
            _T("ARG1-210", files=["y.py"]),
            repo_root=self.repo,
        )
        self.assertTrue(r.independent, msg=r.reason)

    def test_missing_branch_falls_back_to_static_shared(self) -> None:
        _branch_with(self.repo, "ARG1-211", {"argos/cli/p211.py": "a\n"}, "p211")
        r = is_independent(
            _T("ARG1-211", files=["shared.py"]),
            _T("ARG1-212", files=["shared.py"]),
            repo_root=self.repo,
        )
        self.assertFalse(r.independent)
        self.assertIn("shared file", r.reason)

    # AC#8 — rollback discipline: no leaked worktrees, byte-equivalent status.
    def test_no_leaked_worktree_and_clean_status(self) -> None:
        _branch_with(self.repo, "ARG1-213", {"argos/cli/reg.py": "one\ntwo\nthree\nFOUR\n"}, "f")
        _branch_with(self.repo, "ARG1-214", {"argos/cli/reg.py": "ZERO\none\ntwo\nthree\n"}, "z")
        status_before = _git(self.repo, "status", "--porcelain").stdout
        wt_before = _git(self.repo, "worktree", "list", "--porcelain").stdout
        with MergeStagingArea(self.repo) as st:
            is_independent(_T("ARG1-213"), _T("ARG1-214"), staging=st)
        status_after = _git(self.repo, "status", "--porcelain").stdout
        wt_after = _git(self.repo, "worktree", "list", "--porcelain").stdout
        self.assertEqual(status_before, status_after)
        self.assertEqual(wt_before, wt_after)
        # Exactly one worktree (the main one) remains.
        self.assertEqual(wt_after.count("worktree "), 1)

    def test_partition_reuses_one_staging_no_leak(self) -> None:
        _branch_with(self.repo, "ARG1-215", {"argos/cli/reg.py": "one\ntwo\nthree\nFOUR\n"}, "f")
        _branch_with(self.repo, "ARG1-216", {"argos/cli/reg.py": "ZERO\none\ntwo\nthree\n"}, "z")
        _branch_with(self.repo, "ARG1-217", {"argos/cli/reg.py": "one\nTWO-X\nthree\n"}, "x")
        with MergeStagingArea(self.repo) as st:
            groups = partition(
                [_T("ARG1-215"), _T("ARG1-216"), _T("ARG1-217")], staging=st
            )
        # 215 & 216 merge clean (distinct ranges); 217 edits the 'two' line so
        # it conflicts with neither 215's nor 216's change? 217 vs 215: 215 adds
        # FOUR at end, 217 edits 'two' → distinct → clean. 217 vs 216: 216 adds
        # ZERO at top, 217 edits 'two' → distinct → clean. So all three merge
        # pairwise clean → one group.
        self.assertEqual(groups, [["ARG1-215", "ARG1-216", "ARG1-217"]])
        wt = _git(self.repo, "worktree", "list", "--porcelain").stdout
        self.assertEqual(wt.count("worktree "), 1)


class MergeDriverTests(unittest.TestCase):
    """AC#4 — the dry-run exercises the configured ARG1-052 STATE.md driver."""

    _BASE_STATE = (
        "# STATE\n\n"
        "<!-- argos:entry id=base-1 author=verifier -->\n"
        "base entry\n"
        "<!-- /argos:entry -->\n"
    )

    def _state_with(self, entry_id: str, body: str) -> str:
        return (
            self._BASE_STATE
            + f"\n<!-- argos:entry id={entry_id} author=verifier -->\n"
            + f"{body}\n"
            + "<!-- /argos:entry -->\n"
        )

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        _init_repo(self.repo)
        # Install the *real* ARG1-052 driver into the fixture repo.
        driver_rel = "argos/scripts/state-merge-driver.sh"
        (self.repo / "argos" / "scripts").mkdir(parents=True, exist_ok=True)
        shutil.copy(_REAL_DRIVER, self.repo / driver_rel)
        os.chmod(self.repo / driver_rel, 0o755)
        _write(
            self.repo,
            ".gitattributes",
            "argos/specs/v1.0/STATE.md merge=argos-state\n",
        )
        _write(self.repo, "argos/specs/v1.0/STATE.md", self._BASE_STATE)
        _commit_all(self.repo, "seed state + driver")
        # Two branches each append a distinct entry block at EOF — under git's
        # default text merge these adjacent EOF appends CONFLICT; the append
        # driver resolves them cleanly.
        _branch_with(
            self.repo,
            "ARG1-301",
            {"argos/specs/v1.0/STATE.md": self._state_with("a-1", "a entry")},
            "append a",
        )
        _branch_with(
            self.repo,
            "ARG1-302",
            {"argos/specs/v1.0/STATE.md": self._state_with("b-1", "b entry")},
            "append b",
        )

    def _set_driver(self, enabled: bool) -> None:
        if enabled:
            _git(
                self.repo,
                "config",
                "merge.argos-state.driver",
                "argos/scripts/state-merge-driver.sh %O %A %B %P %L",
            )
        else:
            _git(self.repo, "config", "--unset-all", "merge.argos-state.driver", check=False)

    def test_state_pair_independent_under_driver(self) -> None:
        self._set_driver(True)
        r = is_independent(_T("ARG1-301"), _T("ARG1-302"), repo_root=self.repo)
        self.assertTrue(r.independent, msg=r.reason)

    def test_proves_driver_is_what_resolves(self) -> None:
        # Without the configured driver the same pair conflicts (default text
        # merge) → dependent. With it → independent. This proves the dry-run
        # exercised the driver, not a default strategy.
        self._set_driver(False)
        r_default = is_independent(_T("ARG1-301"), _T("ARG1-302"), repo_root=self.repo)
        self.assertFalse(
            r_default.independent,
            msg="expected default text merge to conflict on EOF appends",
        )
        self._set_driver(True)
        r_driver = is_independent(_T("ARG1-301"), _T("ARG1-302"), repo_root=self.repo)
        self.assertTrue(r_driver.independent, msg=r_driver.reason)


class HookInteractionTests(unittest.TestCase):
    """AC#5 — the detector's internal merges never fire the ARG1-032 hook."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        _init_repo(self.repo)
        _write(self.repo, "argos/cli/reg.py", "one\ntwo\nthree\n")
        _commit_all(self.repo, "seed")
        _branch_with(self.repo, "ARG1-401", {"argos/cli/reg.py": "one\ntwo\nthree\nFOUR\n"}, "f")
        _branch_with(self.repo, "ARG1-402", {"argos/cli/reg.py": "ZERO\none\ntwo\nthree\n"}, "z")
        # Install a pre-commit hook (ARG1-032 shape) that drops a sentinel if it
        # ever fires. Installed AFTER the branch commits so those don't trip it.
        self.sentinel = self.repo / "HOOK_FIRED"
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.write_text(
            "#!/bin/sh\n"
            f'echo fired > "{self.sentinel}"\n'
            "exit 0\n",
            encoding="utf-8",
        )
        os.chmod(hook, 0o755)

    def test_dryrun_does_not_fire_pre_commit_hook(self) -> None:
        with MergeStagingArea(self.repo) as st:
            r = is_independent(_T("ARG1-401"), _T("ARG1-402"), staging=st)
        self.assertTrue(r.independent, msg=r.reason)
        self.assertFalse(
            self.sentinel.exists(),
            msg="pre-commit hook fired during a --no-commit dry-run merge",
        )


class CLIMergeTests(unittest.TestCase):
    """AC#1 surface + merge behavior end-to-end through ``argos independence``."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        _init_repo(self.repo)
        # Ticket dir lives OUTSIDE the repo so branch checkouts never disturb
        # it (a ticket file committed on a branch would vanish on `checkout
        # main`). The detector reads tickets from --ticket-dir regardless.
        self._tdir_tmp = tempfile.TemporaryDirectory()
        self.tdir = Path(self._tdir_tmp.name)
        self.addCleanup(self._tdir_tmp.cleanup)
        _write(self.repo, "argos/cli/reg.py", "one\ntwo\nthree\n")
        _commit_all(self.repo, "seed")
        # Ticket files (depends_on parsed from frontmatter; files_touched from
        # Plan — present so a missing-branch pair would still load cleanly).
        for tid in ("ARG1-501", "ARG1-502", "ARG1-503"):
            _write_ticket(self.tdir, tid, files_touched=["argos/cli/reg.py"])
        # 501 appends a line at EOF; 502 prepends at BOF (distinct → clean).
        # 503 appends a DIFFERENT line at the same EOF position as 501, so it
        # conflicts with 501 but not with 502.
        _branch_with(self.repo, "ARG1-501", {"argos/cli/reg.py": "one\ntwo\nthree\nFOUR\n"}, "f")
        _branch_with(self.repo, "ARG1-502", {"argos/cli/reg.py": "ZERO\none\ntwo\nthree\n"}, "z")
        _branch_with(self.repo, "ARG1-503", {"argos/cli/reg.py": "one\ntwo\nthree\nFOUR-DIFFERENT\n"}, "c")

    def _cli(self, *args: str) -> subprocess.CompletedProcess:
        # cwd inside the repo so find_repo_root resolves the fixture, not the
        # argos repo. PYTHONPATH carries the argos package.
        env = dict(os.environ)
        env["PYTHONPATH"] = str(_REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run(
            [sys.executable, "-m", "argos.cli", "independence",
             "--ticket-dir", str(self.tdir), *args],
            cwd=str(self.repo),
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    def test_registration_pair_reported_independent(self) -> None:
        r = self._cli("ARG1-501", "ARG1-502")
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertIn("independent: ARG1-501 ARG1-502", r.stdout)

    def test_conflict_pair_reported_dependent(self) -> None:
        r = self._cli("ARG1-501", "ARG1-503")
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertIn("dependent: ARG1-501 ARG1-503", r.stdout)
        self.assertIn("merge conflict", r.stdout)

    def test_json_surface_unchanged(self) -> None:
        r = self._cli("--json", "ARG1-501", "ARG1-502", "ARG1-503")
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        payload = json.loads(r.stdout)
        self.assertIn("groups", payload)
        self.assertIn("pairs", payload)
        # 501 & 503 conflict → not in the same group.
        g_with_501 = [g for g in payload["groups"] if "ARG1-501" in g][0]
        self.assertNotIn("ARG1-503", g_with_501)

    def test_no_leaked_worktree_after_cli_run(self) -> None:
        self._cli("ARG1-501", "ARG1-502", "ARG1-503")
        wt = _git(self.repo, "worktree", "list", "--porcelain").stdout
        self.assertEqual(wt.count("worktree "), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
