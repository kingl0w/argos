"""Tests for the ARG1-051 ``argos state-append`` helper.

Runnable as::

    python3 -m unittest argos.cli.tests.test_state_append -v

Stdlib only — no third-party dependencies.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

# Make ``argos.cli...`` importable when tests are invoked from anywhere.
# argos/cli/tests/test_state_append.py
#   parents[3] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli.state_append import (  # noqa: E402
    InvalidSuffixError,
    SectionNotFoundError,
    append_block,
    build_block,
    generate_id,
)
from argos.cli.state_parser import parse_file  # noqa: E402

_ARGOS_BIN = Path(__file__).resolve().parents[1] / "argos"


_STATE_FIXTURE = """\
# Argos v1.0 — State

## Current focus

Bootstrapping.

## In progress

_none_

## Done this cycle

<!-- argos:entry id=2026-04-25T00:00:00Z-ARG1-000 ticket=ARG1-000 author=verifier session=sess-seed -->
- **[2026-04-25T00:00:00Z] ARG1-000 — verified** (seed entry)
  - Decision: pass
<!-- /argos:entry -->

## Open decisions

_none_

## Known drift

_none_
"""

_BODY_FIXTURE = """\
- **[2026-04-26T14:33:01Z] ARG1-099 — verified** (session sess-test, worktree `/tmp/x`)
  - Files changed: `argos/cli/state_append.py`
  - Findings: 0 critical, 0 major, 0 minor
  - Decision: pass\
"""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_cli(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Invoke the in-repo argos launcher with the given args."""
    return subprocess.run(
        [sys.executable, str(_ARGOS_BIN), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


class StateAppendCLITests(unittest.TestCase):
    """End-to-end tests covering ARG1-051 acceptance criteria via the CLI."""

    def setUp(self) -> None:
        self._tmpdir_obj = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir_obj.name)
        self.state_file = self.tmpdir / "STATE.md"
        self.state_file.write_text(_STATE_FIXTURE, encoding="utf-8")
        self.body_file = self.tmpdir / "body.md"
        self.body_file.write_text(_BODY_FIXTURE, encoding="utf-8")

    def tearDown(self) -> None:
        self._tmpdir_obj.cleanup()

    # -------- AC#1 --------

    def test_basic_append_creates_block_with_attrs(self) -> None:
        result = _run_cli(
            "state-append",
            "--section", "Done this cycle",
            "--ticket", "ARG1-099",
            "--author", "verifier",
            "--session", "sess-test",
            "--body-file", str(self.body_file),
            "--state-file", str(self.state_file),
        )
        self.assertEqual(
            result.returncode, 0,
            f"expected exit 0; stderr={result.stderr!r}",
        )

        blocks = parse_file(self.state_file)
        # Seed block + new block.
        self.assertEqual(len(blocks), 2)
        new = next(b for b in blocks if b.ticket == "ARG1-099")

        self.assertEqual(new.ticket, "ARG1-099")
        self.assertEqual(new.author, "verifier")
        self.assertEqual(new.session, "sess-test")
        self.assertRegex(
            new.id,
            r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]+Z-ARG1-099$",
        )

    # -------- AC#2 --------

    def test_block_appears_under_named_section(self) -> None:
        result = _run_cli(
            "state-append",
            "--section", "Done this cycle",
            "--ticket", "ARG1-099",
            "--author", "verifier",
            "--session", "sess-test",
            "--body-file", str(self.body_file),
            "--state-file", str(self.state_file),
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        text = self.state_file.read_text(encoding="utf-8")
        lines = text.splitlines()

        # Find the new block's open-tag line.
        open_idx = next(
            i for i, ln in enumerate(lines)
            if "ticket=ARG1-099" in ln and ln.startswith("<!-- argos:entry")
        )

        # Walk backwards to find the most recent ``## `` heading.
        heading_idx = max(
            i for i in range(open_idx) if lines[i].startswith("## ")
        )
        self.assertEqual(lines[heading_idx], "## Done this cycle")

        # No other ``## `` heading sits between that heading and the new block.
        for i in range(heading_idx + 1, open_idx):
            self.assertFalse(
                lines[i].startswith("## "),
                f"unexpected heading on line {i}: {lines[i]!r}",
            )

    # -------- AC#3 --------

    def test_two_concurrent_distinct_tickets_both_present(self) -> None:
        text_pre = self.state_file.read_text(encoding="utf-8")
        count_pre = text_pre.count("<!-- argos:entry")

        def _spawn(ticket: str) -> subprocess.Popen:
            return subprocess.Popen(
                [
                    sys.executable, str(_ARGOS_BIN), "state-append",
                    "--section", "Done this cycle",
                    "--ticket", ticket,
                    "--author", "verifier",
                    "--session", f"sess-{ticket}",
                    "--body-file", str(self.body_file),
                    "--state-file", str(self.state_file),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        p1 = _spawn("ARG1-098")
        p2 = _spawn("ARG1-099")
        out1 = p1.communicate()
        out2 = p2.communicate()
        self.assertEqual(p1.returncode, 0, out1[1])
        self.assertEqual(p2.returncode, 0, out2[1])

        text_post = self.state_file.read_text(encoding="utf-8")
        count_post = text_post.count("<!-- argos:entry")
        self.assertEqual(count_post, count_pre + 2)

        blocks = parse_file(self.state_file)
        tickets = {b.ticket for b in blocks}
        self.assertIn("ARG1-098", tickets)
        self.assertIn("ARG1-099", tickets)

    # -------- AC#4 (library API) --------

    def test_two_same_second_same_ticket_get_distinct_ids(self) -> None:
        frozen = datetime(2026, 4, 26, 14, 33, 1, tzinfo=timezone.utc)

        first = append_block(
            self.state_file,
            section="Done this cycle",
            ticket="ARG1-099",
            author="verifier",
            session="sess-a",
            body=_BODY_FIXTURE,
            now=frozen,
        )
        second = append_block(
            self.state_file,
            section="Done this cycle",
            ticket="ARG1-099",
            author="verifier",
            session="sess-b",
            body=_BODY_FIXTURE,
            now=frozen,
        )

        self.assertNotEqual(first, second)

        blocks = parse_file(self.state_file)
        ids = [b.id for b in blocks if b.ticket == "ARG1-099"]
        self.assertEqual(len(ids), 2, f"expected two ARG1-099 blocks; got {ids!r}")
        self.assertEqual(len(set(ids)), 2, f"ids collided: {ids!r}")

        primary_re = re.compile(r"^2026-04-26T14:33:01Z-ARG1-099$")
        suffixed_re = re.compile(r"^2026-04-26T14:33:01Z-ARG1-099-[0-9a-f]{6}$")
        primaries = [i for i in ids if primary_re.match(i)]
        suffixed = [i for i in ids if suffixed_re.match(i)]
        self.assertEqual(len(primaries), 1, f"expected exactly one primary id; got {ids!r}")
        self.assertEqual(len(suffixed), 1, f"expected exactly one suffixed id; got {ids!r}")

    # -------- AC#5 --------

    def test_section_not_found_exits_nonzero(self) -> None:
        result = _run_cli(
            "state-append",
            "--section", "Nonexistent",
            "--ticket", "ARG1-099",
            "--author", "verifier",
            "--session", "sess-test",
            "--body-file", str(self.body_file),
            "--state-file", str(self.state_file),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("section not found", result.stderr)

    # -------- AC#6 --------

    def test_atomic_write_kill_leaves_file_unchanged(self) -> None:
        sha_pre = _sha256(self.state_file)

        env = os.environ.copy()
        env["ARGOS_TEST_DELAY_BEFORE_RENAME"] = "5.0"

        proc = subprocess.Popen(
            [
                sys.executable, str(_ARGOS_BIN), "state-append",
                "--section", "Done this cycle",
                "--ticket", "ARG1-099",
                "--author", "verifier",
                "--session", "sess-test",
                "--body-file", str(self.body_file),
                "--state-file", str(self.state_file),
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            time.sleep(1.0)
            proc.kill()
            proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                proc.kill()
            if proc.stdout is not None:
                proc.stdout.close()
            if proc.stderr is not None:
                proc.stderr.close()

        # Original file is byte-identical (rename never happened).
        sha_post = _sha256(self.state_file)
        self.assertEqual(sha_pre, sha_post, "STATE.md changed despite SIGKILL pre-rename")

        # Parser still parses cleanly.
        blocks = parse_file(self.state_file)
        self.assertEqual(len(blocks), 1)

        # Subsequent normal append still succeeds (no stale lock state).
        result = _run_cli(
            "state-append",
            "--section", "Done this cycle",
            "--ticket", "ARG1-099",
            "--author", "verifier",
            "--session", "sess-test",
            "--body-file", str(self.body_file),
            "--state-file", str(self.state_file),
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    # -------- AC#7 --------

    def test_dry_run_prints_block_and_does_not_modify_file(self) -> None:
        sha_pre = _sha256(self.state_file)

        result = _run_cli(
            "state-append",
            "--section", "Done this cycle",
            "--ticket", "ARG1-099",
            "--author", "verifier",
            "--session", "sess-test",
            "--body-file", str(self.body_file),
            "--state-file", str(self.state_file),
            "--dry-run",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<!-- argos:entry id=", result.stdout)
        self.assertIn("ticket=ARG1-099", result.stdout)
        self.assertIn("<!-- /argos:entry -->", result.stdout)

        sha_post = _sha256(self.state_file)
        self.assertEqual(sha_pre, sha_post, "dry-run modified STATE.md")

    # -------- defensive: body verbatim --------

    def test_body_content_preserved_verbatim(self) -> None:
        custom_body = (
            "- **canary** with `backticks`, *asterisks*, em-dash —\n"
            "  - nested item with trailing whitespace   \n"
            "  - another nested\n"
        )
        custom = self.tmpdir / "custom-body.md"
        custom.write_text(custom_body, encoding="utf-8")

        result = _run_cli(
            "state-append",
            "--section", "Done this cycle",
            "--ticket", "ARG1-099",
            "--author", "verifier",
            "--session", "sess-test",
            "--body-file", str(custom),
            "--state-file", str(self.state_file),
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        blocks = parse_file(self.state_file)
        new = next(b for b in blocks if b.ticket == "ARG1-099")
        self.assertEqual(new.body, custom_body.rstrip("\n"))


class StateAppendBuildBlockTests(unittest.TestCase):
    """Library smoke tests that don't touch the filesystem."""

    def test_build_block_shape(self) -> None:
        block = build_block(
            block_id="2026-04-26T14:33:01Z-ARG1-099",
            ticket="ARG1-099",
            author="verifier",
            session="sess-test",
            body="- one\n- two",
        )
        self.assertTrue(block.startswith("<!-- argos:entry id=2026-04-26T14:33:01Z-ARG1-099 "))
        self.assertIn("ticket=ARG1-099", block)
        self.assertIn("author=verifier", block)
        self.assertIn("session=sess-test", block)
        self.assertTrue(block.endswith("<!-- /argos:entry -->\n"))

    def test_generate_id_primary_when_no_collision(self) -> None:
        frozen = datetime(2026, 4, 26, 14, 33, 1, tzinfo=timezone.utc)
        out = generate_id("ARG1-099", now=frozen, existing_ids=set())
        self.assertEqual(out, "2026-04-26T14:33:01Z-ARG1-099")

    def test_generate_id_appends_suffix_on_collision(self) -> None:
        frozen = datetime(2026, 4, 26, 14, 33, 1, tzinfo=timezone.utc)
        existing = {"2026-04-26T14:33:01Z-ARG1-099"}
        out = generate_id("ARG1-099", now=frozen, existing_ids=existing)
        self.assertRegex(out, r"^2026-04-26T14:33:01Z-ARG1-099-[0-9a-f]{6}$")

    def test_section_not_found_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "STATE.md"
            state.write_text(_STATE_FIXTURE, encoding="utf-8")
            with self.assertRaises(SectionNotFoundError):
                append_block(
                    state,
                    section="Nonexistent",
                    ticket="ARG1-099",
                    author="verifier",
                    session="sess-test",
                    body="x",
                    dry_run=True,
                )


class StateAppendSuffixTests(unittest.TestCase):
    """Tests for ARG1-061 ``--suffix`` flag on ``argos state-append``."""

    def setUp(self) -> None:
        self._tmpdir_obj = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir_obj.name)
        self.state_file = self.tmpdir / "STATE.md"
        self.state_file.write_text(_STATE_FIXTURE, encoding="utf-8")
        self.body_file = self.tmpdir / "body.md"
        self.body_file.write_text(_BODY_FIXTURE, encoding="utf-8")

    def tearDown(self) -> None:
        self._tmpdir_obj.cleanup()

    def test_cli_suffix_appended_to_id(self) -> None:
        result = _run_cli(
            "state-append",
            "--section", "Known drift",
            "--ticket", "ARG1-099",
            "--author", "coder",
            "--session", "sess-test",
            "--body-file", str(self.body_file),
            "--state-file", str(self.state_file),
            "--suffix", "drift",
            "--dry-run",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        # Open tag's id attribute ends with "-ARG1-099-drift".
        match = re.search(r"id=(\S+)", result.stdout)
        self.assertIsNotNone(match, f"no id attribute in stdout: {result.stdout!r}")
        self.assertRegex(
            match.group(1),
            r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]+Z-ARG1-099-drift$",
        )

    def test_cli_suffix_with_space_rejected(self) -> None:
        result = _run_cli(
            "state-append",
            "--section", "Known drift",
            "--ticket", "ARG1-099",
            "--author", "coder",
            "--session", "sess-test",
            "--body-file", str(self.body_file),
            "--state-file", str(self.state_file),
            "--suffix", "bad space",
            "--dry-run",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid suffix", result.stderr)
        self.assertIn("bad space", result.stderr)

    def test_cli_suffix_uppercase_rejected(self) -> None:
        result = _run_cli(
            "state-append",
            "--section", "Known drift",
            "--ticket", "ARG1-099",
            "--author", "coder",
            "--session", "sess-test",
            "--body-file", str(self.body_file),
            "--state-file", str(self.state_file),
            "--suffix", "BAD",
            "--dry-run",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid suffix", result.stderr)

    def test_cli_suffix_empty_rejected(self) -> None:
        result = _run_cli(
            "state-append",
            "--section", "Known drift",
            "--ticket", "ARG1-099",
            "--author", "coder",
            "--session", "sess-test",
            "--body-file", str(self.body_file),
            "--state-file", str(self.state_file),
            "--suffix", "",
            "--dry-run",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid suffix", result.stderr)

    def test_cli_suffix_complex_slug_accepted(self) -> None:
        result = _run_cli(
            "state-append",
            "--section", "Known drift",
            "--ticket", "ARG1-099",
            "--author", "coder",
            "--session", "sess-test",
            "--body-file", str(self.body_file),
            "--state-file", str(self.state_file),
            "--suffix", "valid-slug-123",
            "--dry-run",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        match = re.search(r"id=(\S+)", result.stdout)
        self.assertIsNotNone(match)
        self.assertTrue(
            match.group(1).endswith("-ARG1-099-valid-slug-123"),
            f"id did not end with expected suffix: {match.group(1)!r}",
        )

    def test_library_suffix_collision_appends_hex(self) -> None:
        frozen = datetime(2026, 4, 26, 14, 33, 1, tzinfo=timezone.utc)

        first = append_block(
            self.state_file,
            section="Known drift",
            ticket="ARG1-099",
            author="coder",
            session="sess-a",
            body=_BODY_FIXTURE,
            now=frozen,
            suffix="drift",
        )
        second = append_block(
            self.state_file,
            section="Known drift",
            ticket="ARG1-099",
            author="coder",
            session="sess-b",
            body=_BODY_FIXTURE,
            now=frozen,
            suffix="drift",
        )

        self.assertNotEqual(first, second)

        ids = [b.id for b in parse_file(self.state_file) if b.ticket == "ARG1-099"]
        self.assertEqual(len(ids), 2, f"expected two ARG1-099 blocks; got {ids!r}")
        self.assertEqual(len(set(ids)), 2, f"ids collided: {ids!r}")

        primary_re = re.compile(r"^2026-04-26T14:33:01Z-ARG1-099-drift$")
        suffixed_re = re.compile(r"^2026-04-26T14:33:01Z-ARG1-099-drift-[0-9a-f]{6}$")
        primaries = [i for i in ids if primary_re.match(i)]
        suffixed = [i for i in ids if suffixed_re.match(i)]
        self.assertEqual(len(primaries), 1, f"expected one primary id; got {ids!r}")
        self.assertEqual(len(suffixed), 1, f"expected one collision-suffixed id; got {ids!r}")

    def test_library_suffix_invalid_raises(self) -> None:
        with self.assertRaises(InvalidSuffixError):
            generate_id("ARG1-099", suffix="BAD")
        with self.assertRaises(InvalidSuffixError):
            generate_id("ARG1-099", suffix="bad space")
        with self.assertRaises(InvalidSuffixError):
            generate_id("ARG1-099", suffix="")
        with self.assertRaises(InvalidSuffixError):
            generate_id("ARG1-099", suffix="under_score")

    def test_no_suffix_unchanged_format_regression(self) -> None:
        """Flagless invocation must still produce an id with no trailing dash."""
        frozen = datetime(2026, 4, 26, 14, 33, 1, tzinfo=timezone.utc)
        out = generate_id("ARG1-099", now=frozen, existing_ids=set())
        self.assertEqual(out, "2026-04-26T14:33:01Z-ARG1-099")
        self.assertNotIn("--", out)
        self.assertFalse(out.endswith("-"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
