"""Tests for ``argos.cli.state_parser`` and the ``state-parse`` CLI shim.

Fixture paths are resolved relative to ``__file__`` so the tests run regardless
of the directory the test runner is invoked from.

Runnable as::

    python3 -m unittest argos.cli.tests.test_state_parser -v

Stdlib only (ADR-001 / ADR-002): no pytest, no third-party imports.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

# Make ``argos.cli...`` importable when the runner is invoked from anywhere.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli.state_parser import (  # noqa: E402  (sys.path tweak above)
    Block,
    DuplicateIdError,
    MalformedOpenTagError,
    MissingAttributeError,
    UnclosedEntryError,
    parse,
    parse_file,
)

# argos/cli/tests/test_state_parser.py
#   parents[0] = argos/cli/tests
#   parents[1] = argos/cli
#   parents[2] = argos
#   parents[3] = repo root
_FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "v1.0"
    / "schemas"
    / "examples"
)


def _fixture(name: str) -> Path:
    p = _FIXTURES / name
    assert p.exists(), f"fixture missing: {p}"
    return p


# ---------------------------------------------------------------------------
# parse() / parse_file() — direct API
# ---------------------------------------------------------------------------


class ParseApiTests(unittest.TestCase):
    def test_parse_valid_returns_blocks_with_required_attrs(self) -> None:
        blocks = parse_file(_fixture("state-valid.md"))
        self.assertGreaterEqual(len(blocks), 1)
        for b in blocks:
            self.assertIsInstance(b, Block)
            self.assertTrue(b.id, "id must be populated")
            self.assertTrue(b.ticket, "ticket must be populated")
            self.assertTrue(b.author, "author must be populated")
            self.assertTrue(b.session, "session must be populated")

    def test_parse_valid_dict_round_trips_to_json(self) -> None:
        blocks = parse_file(_fixture("state-valid.md"))
        payload = [b.to_dict() for b in blocks]
        s = json.dumps(payload)
        parsed = json.loads(s)
        self.assertEqual(parsed[0]["id"], blocks[0].id)
        self.assertEqual(parsed[0]["ticket"], blocks[0].ticket)
        self.assertEqual(parsed[0]["author"], blocks[0].author)
        self.assertEqual(parsed[0]["session"], blocks[0].session)

    def test_unclosed_block_raises_unclosed_entry(self) -> None:
        with self.assertRaises(UnclosedEntryError) as cm:
            parse_file(_fixture("state-unclosed-block.md"))
        msg = str(cm.exception)
        self.assertIn("unclosed entry", msg)
        self.assertIn("line ", msg)

    def test_duplicate_id_raises_with_offending_id(self) -> None:
        with self.assertRaises(DuplicateIdError) as cm:
            parse_file(_fixture("state-duplicate-id.md"))
        msg = str(cm.exception)
        self.assertIn("duplicate id", msg)
        # Offending id must appear verbatim in the error message.
        self.assertIn("2026-04-26T16:00:00Z-ARG-044", msg)

    def test_missing_attr_names_attribute_and_line(self) -> None:
        with self.assertRaises(MissingAttributeError) as cm:
            parse_file(_fixture("state-missing-attr.md"))
        msg = str(cm.exception)
        self.assertIn("session", msg)
        self.assertIn("line ", msg)

    def test_malformed_open_tag_raises(self) -> None:
        text = "<!-- argos:entry totally bogus -->\nbody\n<!-- /argos:entry -->\n"
        with self.assertRaises(MalformedOpenTagError):
            parse(text)

    def test_blocks_unordered_within_section_all_returned(self) -> None:
        """Acceptance criterion 7 — three blocks intermixed with prose return as a 3-element list."""
        text = (
            "## Done this cycle\n"
            "\n"
            "Some intro prose.\n"
            "\n"
            "<!-- argos:entry id=2026-04-26T10:00:00Z-ARG-100 ticket=ARG-100 author=verifier session=s1 -->\n"
            "- block one body\n"
            "<!-- /argos:entry -->\n"
            "\n"
            "Some prose between blocks.\n"
            "\n"
            "<!-- argos:entry id=2026-04-26T10:00:01Z-ARG-101 ticket=ARG-101 author=coder session=s2 -->\n"
            "- block two body\n"
            "<!-- /argos:entry -->\n"
            "\n"
            "More prose.\n"
            "\n"
            "<!-- argos:entry id=2026-04-26T10:00:02Z-ARG-102 ticket=ARG-102 author=planner session=s3 -->\n"
            "- block three body\n"
            "<!-- /argos:entry -->\n"
        )
        blocks = parse(text)
        self.assertEqual(len(blocks), 3)
        self.assertEqual(
            [b.id for b in blocks],
            [
                "2026-04-26T10:00:00Z-ARG-100",
                "2026-04-26T10:00:01Z-ARG-101",
                "2026-04-26T10:00:02Z-ARG-102",
            ],
        )
        self.assertEqual(
            [b.ticket for b in blocks], ["ARG-100", "ARG-101", "ARG-102"]
        )
        self.assertEqual(
            [b.author for b in blocks], ["verifier", "coder", "planner"]
        )

    def test_empty_text_returns_empty_list(self) -> None:
        self.assertEqual(parse(""), [])

    def test_stray_close_tag_outside_block_is_ignored(self) -> None:
        text = "<!-- /argos:entry -->\nsome prose\n"
        self.assertEqual(parse(text), [])


# ---------------------------------------------------------------------------
# CLI shim — subprocess invocations of `python3 -m argos.cli state-parse <path>`
# ---------------------------------------------------------------------------


def _run_cli(fixture_name: str) -> subprocess.CompletedProcess:
    fixture = _fixture(fixture_name)
    return subprocess.run(
        [sys.executable, "-m", "argos.cli", "state-parse", str(fixture)],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        check=False,
    )


class StateParseCLITests(unittest.TestCase):
    def test_cli_valid_exits_zero_and_emits_json(self) -> None:
        proc = _run_cli("state-valid.md")
        self.assertEqual(proc.returncode, 0, msg=f"stderr was: {proc.stderr!r}")
        payload = json.loads(proc.stdout)
        self.assertIsInstance(payload, list)
        self.assertGreaterEqual(len(payload), 1)
        for entry in payload:
            for key in ("id", "ticket", "author", "session"):
                self.assertIn(key, entry, msg=f"missing key {key!r} in CLI JSON output")
                self.assertTrue(entry[key], msg=f"empty value for key {key!r}")

    def test_cli_unclosed_exits_nonzero_with_substring(self) -> None:
        proc = _run_cli("state-unclosed-block.md")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("unclosed entry", proc.stderr)

    def test_cli_duplicate_exits_nonzero_with_id(self) -> None:
        proc = _run_cli("state-duplicate-id.md")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("duplicate id", proc.stderr)
        self.assertIn("2026-04-26T16:00:00Z-ARG-044", proc.stderr)

    def test_cli_missing_attr_exits_nonzero_naming_attr(self) -> None:
        proc = _run_cli("state-missing-attr.md")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("session", proc.stderr)
        self.assertIn("line ", proc.stderr)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
