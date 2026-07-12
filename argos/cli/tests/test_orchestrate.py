"""Tests for ARG1-011: ``argos.cli.queue`` parser + ``argos orchestrate`` CLI.

Stdlib-only per ADR-001 / ADR-002 — :mod:`unittest`, :mod:`subprocess`,
:mod:`tempfile`, :mod:`pathlib`. No third-party imports.

Runnable as::

    python3 -m unittest argos.cli.tests.test_orchestrate -v
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli.queue import (  # noqa: E402
    QueueSectionMissingError,
    StateFileNotFoundError,
    parse_queue,
    parse_queue_file,
)

_ARGOS_BIN = Path(__file__).resolve().parents[1] / "argos"


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_ARGOS_BIN), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd) if cwd is not None else None,
    )


def _write_state(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


# Canonical fixture: a STATE.md with several queued tickets, an in-progress
# section, and a known-drift section. Mirrors v0.5 STATE.md shape so the
# parser is exercised against realistic input.
_FULL_STATE = """\
# Test STATE

## Current focus

Test fixture.

## Queue

Tickets ready to be worked, in rough priority order.

- ARG1-022 — independence detection (P0)
- ARG1-013 — auto-fix retry loop (P1)
- ARG1-023 — merge-on-pass + cleanup (P1)

## In progress

- [ ] _none_

## Done this cycle

_none_

## Known drift

_none_
"""

_EMPTY_QUEUE_STATE = """\
# Test STATE

## Current focus

Test fixture.

## Queue

_(populated as tickets are queued for dispatch; orchestrator reads this section)_

## In progress

_none_
"""

_NO_QUEUE_STATE = """\
# Test STATE

## Current focus

Test fixture — no Queue section at all.

## In progress

_none_
"""

_MIXED_QUEUE_STATE = """\
# Test STATE

## Queue

- ARG-001 — v0.5-shape ticket id (P2)
- not a ticket bullet
- ARG1-099 — v1.0-shape ticket id (P0)
  - ARG1-100 — indented bullet still counts as a queued id

## Done this cycle
"""


class ParseQueueLibraryTests(unittest.TestCase):
    """Pure-library checks against ``parse_queue`` / ``parse_queue_file``."""

    def test_full_queue_returns_ids_in_order(self) -> None:
        ids = parse_queue(_FULL_STATE)
        self.assertEqual(ids, ["ARG1-022", "ARG1-013", "ARG1-023"])

    def test_empty_queue_returns_empty_list(self) -> None:
        ids = parse_queue(_EMPTY_QUEUE_STATE)
        self.assertEqual(ids, [])

    def test_no_queue_section_raises(self) -> None:
        with self.assertRaises(QueueSectionMissingError):
            parse_queue(_NO_QUEUE_STATE)

    def test_mixed_queue_skips_non_ticket_bullets(self) -> None:
        ids = parse_queue(_MIXED_QUEUE_STATE)
        # Indented bullet is still a bullet; non-ticket prose bullet is skipped.
        self.assertEqual(ids, ["ARG-001", "ARG1-099", "ARG1-100"])

    def test_parse_queue_file_missing_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "nope" / "STATE.md"
            with self.assertRaises(StateFileNotFoundError) as cm:
                parse_queue_file(missing)
            self.assertIn("STATE.md not found", str(cm.exception))

    def test_parse_queue_file_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "STATE.md"
            _write_state(p, _FULL_STATE)
            self.assertEqual(
                parse_queue_file(p),
                ["ARG1-022", "ARG1-013", "ARG1-023"],
            )


class OrchestrateCLITests(unittest.TestCase):
    """End-to-end ``argos orchestrate --dry-run`` checks against the launcher."""

    def test_dry_run_lists_queue(self) -> None:
        # ARG1-022 AC#6 ships the canonical markdown table format with
        # columns ticket_id / group / dispatch_order / parallel_with as
        # the dry-run output when every queued ticket loads with a
        # ``files_touched:`` Plan section. Pin --ticket-dir to a tempdir
        # with synthetic frontmatter so independence detection runs
        # against deterministic fixtures, not the live tickets/ tree.
        # Assertions check structure (header + three data rows with four
        # cells each) rather than specific group/dispatch_order values
        # to avoid re-coupling to detection internals (AC#2c).
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "STATE.md"
            _write_state(state, _FULL_STATE)
            tickets = Path(td) / "tickets"
            tickets.mkdir()
            for tid, touched in (
                ("ARG1-022", "argos/synthetic/a.py"),
                ("ARG1-013", "argos/synthetic/b.py"),
                ("ARG1-023", "argos/synthetic/c.py"),
            ):
                (tickets / f"{tid}.md").write_text(
                    "---\n"
                    f"id: {tid}\n"
                    "---\n"
                    "\n"
                    "## Plan\n"
                    "\n"
                    "files_touched:\n"
                    f"  - {touched}\n",
                    encoding="utf-8",
                )
            res = _run_cli(
                "orchestrate",
                "--dry-run",
                "--state-file",
                str(state),
                "--ticket-dir",
                str(tickets),
            )
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            lines = res.stdout.splitlines()
            header_rows = [
                line for line in lines
                if "ticket_id" in line
                and "group" in line
                and "dispatch_order" in line
                and "parallel_with" in line
            ]
            self.assertEqual(
                len(header_rows), 1,
                msg=(
                    "expected exactly one AC#6 header row in dry-run "
                    f"stdout, got:\n{res.stdout}"
                ),
            )
            data_rows_by_id: dict[str, list[str]] = {}
            for line in lines:
                if not line.startswith("|"):
                    continue
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) != 4 or cells[0] == "ticket_id":
                    continue
                data_rows_by_id.setdefault(cells[0], []).append(line)
            for tid in ("ARG1-022", "ARG1-013", "ARG1-023"):
                rows = data_rows_by_id.get(tid, [])
                self.assertEqual(
                    len(rows), 1,
                    msg=f"expected one data row for {tid}, got {rows}",
                )
                cells = [c.strip() for c in rows[0].strip("|").split("|")]
                self.assertEqual(cells[0], tid)
                # group + dispatch_order are independence-detector outputs
                # (AC#2c — assert non-empty rather than specific values).
                self.assertNotEqual(cells[1], "")
                self.assertNotEqual(cells[2], "")

    def test_dry_run_empty_queue_emits_marker(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "STATE.md"
            _write_state(state, _EMPTY_QUEUE_STATE)
            res = _run_cli("orchestrate", "--dry-run", "--state-file", str(state))
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            self.assertIn("queue empty", res.stdout)

    def test_dry_run_v1_tree_autoselect_notes_on_stderr(self) -> None:
        # ARG1-075 footgun guard: when bare `orchestrate` auto-selects the
        # versioned argos/specs/v1.0/ tree, say so on stderr; a flat
        # scaffolded tree and an explicit --state-file stay silent.
        with tempfile.TemporaryDirectory() as td:
            v1 = Path(td) / "argos" / "specs" / "v1.0"
            v1.mkdir(parents=True)
            _write_state(v1 / "STATE.md", _EMPTY_QUEUE_STATE)
            res = _run_cli("orchestrate", "--dry-run", cwd=Path(td))
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            self.assertIn("auto-selected versioned spec tree", res.stderr)
            # Explicit --state-file targeting the same file: no note.
            res = _run_cli(
                "orchestrate", "--dry-run",
                "--state-file", str(v1 / "STATE.md"),
                cwd=Path(td),
            )
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            self.assertNotIn("auto-selected", res.stderr)

    def test_dry_run_flat_tree_autoselect_is_silent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            specs = Path(td) / "argos" / "specs"
            specs.mkdir(parents=True)
            _write_state(specs / "STATE.md", _EMPTY_QUEUE_STATE)
            res = _run_cli("orchestrate", "--dry-run", cwd=Path(td))
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            self.assertNotIn("auto-selected", res.stderr)

    def test_dry_run_missing_state_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "does-not-exist" / "STATE.md"
            res = _run_cli(
                "orchestrate", "--dry-run", "--state-file", str(missing)
            )
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("STATE.md not found", res.stderr)

    def test_dry_run_batch_size_caps_output(self) -> None:
        # Pin --ticket-dir to an empty temp dir so independence
        # detection always falls back to serial id-list output. Without
        # this pin, the test silently coupled to whether the live
        # ticket files in the repo carry a ``files_touched:`` Plan
        # section — adding one to ARG1-013 would flip the output to
        # the AC#6 markdown table.
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "STATE.md"
            _write_state(state, _FULL_STATE)
            empty_tickets = Path(td) / "no-tickets"
            empty_tickets.mkdir()
            res = _run_cli(
                "orchestrate",
                "--dry-run",
                "--batch-size",
                "2",
                "--state-file",
                str(state),
                "--ticket-dir",
                str(empty_tickets),
            )
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            lines = res.stdout.splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines, ["ARG1-022", "ARG1-013"])

    def test_dry_run_batch_size_larger_than_queue(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "STATE.md"
            _write_state(state, _FULL_STATE)
            empty_tickets = Path(td) / "no-tickets"
            empty_tickets.mkdir()
            res = _run_cli(
                "orchestrate",
                "--dry-run",
                "--batch-size",
                "99",
                "--state-file",
                str(state),
                "--ticket-dir",
                str(empty_tickets),
            )
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            self.assertEqual(
                res.stdout.splitlines(),
                ["ARG1-022", "ARG1-013", "ARG1-023"],
            )

    def test_dry_run_batch_size_zero_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "STATE.md"
            _write_state(state, _FULL_STATE)
            res = _run_cli(
                "orchestrate",
                "--dry-run",
                "--batch-size",
                "0",
                "--state-file",
                str(state),
            )
            self.assertEqual(res.returncode, 2)
            self.assertIn("batch-size", res.stderr)

    def test_dry_run_no_queue_section_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "STATE.md"
            _write_state(state, _NO_QUEUE_STATE)
            res = _run_cli(
                "orchestrate", "--dry-run", "--state-file", str(state)
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("Queue", res.stderr)

    def test_no_dry_run_without_epic_rejected(self) -> None:
        # Real dispatch (ARG1-022) requires --epic; without it, exit 2.
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "STATE.md"
            _write_state(state, _FULL_STATE)
            res = _run_cli("orchestrate", "--state-file", str(state))
            self.assertEqual(res.returncode, 2)
            self.assertIn("--epic is required", res.stderr)

    def test_help_lists_orchestrate(self) -> None:
        res = _run_cli("--help")
        self.assertEqual(res.returncode, 0)
        self.assertIn("orchestrate", res.stdout)


class SlashCommandFileTests(unittest.TestCase):
    """ARG1-011 ACs that target the markdown surface, not the CLI."""

    def test_slash_command_file_exists(self) -> None:
        path = _REPO_ROOT / ".claude" / "commands" / "orchestrate.md"
        self.assertTrue(path.is_file(), f"missing {path}")

    def test_slash_command_references_orchestrator(self) -> None:
        path = _REPO_ROOT / ".claude" / "commands" / "orchestrate.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn("orchestrator", text)

    def test_slash_command_mirror_matches(self) -> None:
        primary = _REPO_ROOT / ".claude" / "commands" / "orchestrate.md"
        mirror = (
            _REPO_ROOT
            / "argos"
            / "specs"
            / "v1.0"
            / "commands"
            / "orchestrate.md"
        )
        self.assertTrue(mirror.is_file(), f"missing canonical mirror {mirror}")
        self.assertEqual(
            primary.read_bytes(),
            mirror.read_bytes(),
            "slash command and v1.0 canonical mirror are not byte-identical",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
