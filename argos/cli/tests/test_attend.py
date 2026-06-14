"""Tests for argos.cli.commands.attend and the ``argos attend`` CLI (ARG1-005).

Stdlib ``unittest`` only — no pytest. Run from the repo root::

    python3 -m unittest argos.cli.tests.test_attend -v
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

from argos.cli.commands import attend  # noqa: E402

_ARGOS_BIN = _REPO_ROOT / "argos" / "cli" / "argos"


def _escalation_text(
    *,
    ticket_id: str = "ARG1-099",
    session_id: str = "sess-test-0001",
    severity: str = "blocking",
    raised_by: str = "coder",
    created: str = "2026-05-01T12:00:00Z",
    resolution: bool = False,
) -> str:
    text = textwrap.dedent(
        f"""\
        ---
        ticket_id: {ticket_id}
        session_id: {session_id}
        severity: {severity}
        raised_by: {raised_by}
        created: {created}
        ---

        ## Question

        Which option should we take?

        ## Context

        Some context here.

        ## Options considered

        - A: do the thing
        - B: do the other thing

        ## Why escalated

        Genuine ambiguity.
        """
    )
    if resolution:
        text += "\n## Resolution\n\nDrained already.\n"
    return text


def _write_escalation(esc_dir: Path, name: str, **kwargs: object) -> Path:
    esc_dir.mkdir(parents=True, exist_ok=True)
    path = esc_dir / name
    path.write_text(_escalation_text(**kwargs), encoding="utf-8")  # type: ignore[arg-type]
    return path


def _run_cli(
    *args: str,
    cwd: Path | None = None,
    stdin: str | None = None,
    timeout: float = 10.0,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_ARGOS_BIN), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd) if cwd else None,
        input=stdin,
        timeout=timeout,
    )


class ScanTests(unittest.TestCase):
    def test_empty_dir_no_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            esc_dir = Path(tmp) / "escalations"
            esc_dir.mkdir()
            pending, malformed = attend.scan(esc_dir)
            self.assertEqual(pending, [])
            self.assertEqual(malformed, [])

    def test_missing_dir_no_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pending, malformed = attend.scan(Path(tmp) / "nope")
            self.assertEqual(pending, [])
            self.assertEqual(malformed, [])

    def test_drained_file_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            esc_dir = Path(tmp) / "escalations"
            _write_escalation(esc_dir, "ARG1-099-a.md", resolution=True)
            pending, malformed = attend.scan(esc_dir)
            self.assertEqual(pending, [])
            self.assertEqual(malformed, [])

    def test_chronological_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            esc_dir = Path(tmp) / "escalations"
            # Write newest first by filename to prove sort is by `created`.
            _write_escalation(
                esc_dir, "ARG1-200-newer.md",
                ticket_id="ARG1-200", created="2026-06-01T00:00:00Z",
            )
            _write_escalation(
                esc_dir, "ARG1-100-older.md",
                ticket_id="ARG1-100", created="2026-01-01T00:00:00Z",
            )
            pending, malformed = attend.scan(esc_dir)
            self.assertEqual(malformed, [])
            self.assertEqual([e.ticket_id for e in pending], ["ARG1-100", "ARG1-200"])

    def test_ticket_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            esc_dir = Path(tmp) / "escalations"
            _write_escalation(esc_dir, "ARG1-100-a.md", ticket_id="ARG1-100")
            _write_escalation(esc_dir, "ARG1-200-a.md", ticket_id="ARG1-200")
            pending, _ = attend.scan(esc_dir, ticket_filter="ARG1-200")
            self.assertEqual([e.ticket_id for e in pending], ["ARG1-200"])

    def test_readme_sentinel_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            esc_dir = Path(tmp) / "escalations"
            esc_dir.mkdir()
            (esc_dir / "README.md").write_text(
                "# escalations\n\nnot an escalation\n", encoding="utf-8"
            )
            pending, malformed = attend.scan(esc_dir)
            self.assertEqual(pending, [])
            self.assertEqual(malformed, [])

    def test_malformed_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            esc_dir = Path(tmp) / "escalations"
            esc_dir.mkdir()
            bad = esc_dir / "ARG1-300-bad.md"
            bad.write_text("no frontmatter here\n", encoding="utf-8")
            pending, malformed = attend.scan(esc_dir)
            self.assertEqual(pending, [])
            self.assertEqual(len(malformed), 1)
            self.assertIn(str(bad), malformed[0])


class DecisionRecordingTests(unittest.TestCase):
    def test_creates_decisions_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tickets = Path(tmp) / "tickets"
            tickets.mkdir()
            ticket = tickets / "ARG1-099-thing.md"
            ticket.write_text("# ARG1-099\n\nbody\n", encoding="utf-8")
            esc = attend.Escalation(
                path=Path("ARG1-099-x.md"),
                ticket_id="ARG1-099",
                session_id="sess-1",
                severity="blocking",
                raised_by="coder",
                created="2026-05-01T12:00:00Z",
                body="",
            )
            attend.record_decision(tickets, esc, "use option A")
            out = ticket.read_text(encoding="utf-8")
            self.assertIn("## Decisions", out)
            self.assertIn("use option A", out)

    def test_appends_to_existing_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tickets = Path(tmp) / "tickets"
            tickets.mkdir()
            ticket = tickets / "ARG1-099-thing.md"
            ticket.write_text(
                "# ARG1-099\n\n## Decisions\n\n- prior decision\n\n## Next\n\ntail\n",
                encoding="utf-8",
            )
            esc = attend.Escalation(
                path=Path("ARG1-099-x.md"),
                ticket_id="ARG1-099",
                session_id="sess-1",
                severity="blocking",
                raised_by="coder",
                created="2026-05-01T12:00:00Z",
                body="",
            )
            attend.record_decision(tickets, esc, "use option B")
            out = ticket.read_text(encoding="utf-8")
            self.assertIn("- prior decision", out)
            self.assertIn("use option B", out)
            # New entry stays inside the Decisions section (before ## Next).
            self.assertLess(out.index("use option B"), out.index("## Next"))

    def test_missing_ticket_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tickets = Path(tmp) / "tickets"
            tickets.mkdir()
            esc = attend.Escalation(
                path=Path("ARG1-404-x.md"),
                ticket_id="ARG1-404",
                session_id="sess-1",
                severity="blocking",
                raised_by="coder",
                created="2026-05-01T12:00:00Z",
                body="",
            )
            with self.assertRaises(attend.TicketNotFoundError):
                attend.record_decision(tickets, esc, "anything")


class CliTests(unittest.TestCase):
    """End-to-end CLI exercises covering each acceptance criterion."""

    def _make_repo(self, tmp: Path) -> tuple[Path, Path]:
        esc_dir = tmp / "argos" / "specs" / "escalations"
        tickets_dir = tmp / "argos" / "specs" / "tickets"
        esc_dir.mkdir(parents=True)
        tickets_dir.mkdir(parents=True)
        # config marker so _find_repo_root resolves the temp dir as the root.
        (tmp / "argos" / "config.toml.template").write_text(
            '[project]\nname = "t"\n', encoding="utf-8"
        )
        return esc_dir, tickets_dir

    def test_ac1_empty_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            self._make_repo(tmp)
            res = _run_cli("attend", cwd=tmp)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("no pending escalations", res.stdout)

    def test_ac1_only_drained_reads_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            esc_dir, _ = self._make_repo(tmp)
            _write_escalation(esc_dir, "ARG1-057-x.md", ticket_id="ARG1-057", resolution=True)
            res = _run_cli("attend", cwd=tmp)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("no pending escalations", res.stdout)

    def test_ac2_list_shows_ticket_and_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            esc_dir, _ = self._make_repo(tmp)
            _write_escalation(
                esc_dir, "ARG1-099-a.md",
                ticket_id="ARG1-099", created="2026-05-01T12:00:00Z",
            )
            res = _run_cli("attend", "--list", cwd=tmp)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("ARG1-099", res.stdout)
            self.assertIn("2026-05-01T12:00:00Z", res.stdout)

    def test_ac3_list_chronological(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            esc_dir, _ = self._make_repo(tmp)
            _write_escalation(
                esc_dir, "ARG1-200-newer.md",
                ticket_id="ARG1-200", created="2026-06-01T00:00:00Z",
            )
            _write_escalation(
                esc_dir, "ARG1-100-older.md",
                ticket_id="ARG1-100", created="2026-01-01T00:00:00Z",
            )
            res = _run_cli("attend", "--list", cwd=tmp)
            self.assertEqual(res.returncode, 0, res.stderr)
            first = res.stdout.splitlines()[0]
            self.assertIn("ARG1-100", first)

    def test_ac4_drain_records_and_removes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            esc_dir, tickets_dir = self._make_repo(tmp)
            esc = _write_escalation(esc_dir, "ARG1-099-a.md", ticket_id="ARG1-099")
            ticket = tickets_dir / "ARG1-099-thing.md"
            ticket.write_text("# ARG1-099\n\nbody\n", encoding="utf-8")
            res = _run_cli("attend", "--ticket", "ARG1-099", cwd=tmp, stdin="use option A\n")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertFalse(esc.exists())
            self.assertIn("use option A", ticket.read_text(encoding="utf-8"))

    def test_ac5_malformed_nonzero_names_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            esc_dir, _ = self._make_repo(tmp)
            bad = esc_dir / "ARG1-300-bad.md"
            bad.write_text("missing frontmatter\n", encoding="utf-8")
            res = _run_cli("attend", "--list", cwd=tmp)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn(str(bad), res.stderr)

    def test_ac5_malformed_missing_required_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            esc_dir, _ = self._make_repo(tmp)
            bad = esc_dir / "ARG1-301-bad.md"
            # Valid delimiters but missing required keys (only ticket_id).
            bad.write_text(
                "---\nticket_id: ARG1-301\n---\n\n## Question\n\nq\n",
                encoding="utf-8",
            )
            res = _run_cli("attend", "--list", cwd=tmp)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn(str(bad), res.stderr)

    def test_ac6_filter_nonexistent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            esc_dir, _ = self._make_repo(tmp)
            _write_escalation(esc_dir, "ARG1-099-a.md", ticket_id="ARG1-099")
            res = _run_cli("attend", "--ticket", "NONEXISTENT", cwd=tmp)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("no pending escalations for NONEXISTENT", res.stdout)

    def test_eof_leaves_escalation_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            esc_dir, tickets_dir = self._make_repo(tmp)
            esc = _write_escalation(esc_dir, "ARG1-099-a.md", ticket_id="ARG1-099")
            (tickets_dir / "ARG1-099-thing.md").write_text("# t\n", encoding="utf-8")
            # No stdin -> immediate EOF -> nothing drained.
            res = _run_cli("attend", "--ticket", "ARG1-099", cwd=tmp, stdin="")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue(esc.exists())

    def test_missing_ticket_leaves_file_and_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            esc_dir, _ = self._make_repo(tmp)
            esc = _write_escalation(esc_dir, "ARG1-099-a.md", ticket_id="ARG1-099")
            res = _run_cli("attend", "--ticket", "ARG1-099", cwd=tmp, stdin="decide\n")
            self.assertNotEqual(res.returncode, 0)
            self.assertTrue(esc.exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
