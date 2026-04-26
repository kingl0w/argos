"""Tests for argos.cli.verifier_parser."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DOC = REPO_ROOT / "argos" / "specs" / "v1.0" / "schemas" / "verifier-output.md"

EXAMPLE_OPEN = "<!-- argos:verifier-output:example -->"
EXAMPLE_CLOSE = "<!-- /argos:verifier-output:example -->"


def _extract_canonical_example() -> str:
    text = SCHEMA_DOC.read_text(encoding="utf-8")
    start = text.find(EXAMPLE_OPEN)
    end = text.find(EXAMPLE_CLOSE)
    assert start != -1 and end != -1, "schema doc missing example markers"
    inner = text[start + len(EXAMPLE_OPEN) : end]
    # The example markers wrap a real verifier-output block; return that block
    # verbatim so the parser can locate its own <!-- argos:verifier-output -->
    # delimiters.
    return inner


def _run_parser(payload: str) -> subprocess.CompletedProcess:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(payload)
        path = fh.name
    return subprocess.run(
        [sys.executable, "-m", "argos.cli.verifier_parser", path],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


class TestVerifierParser(unittest.TestCase):
    def test_canonical_example_round_trip(self) -> None:
        example = _extract_canonical_example()
        result = _run_parser(example)
        self.assertEqual(
            result.returncode, 0, msg=f"stderr: {result.stderr}"
        )
        parsed = json.loads(result.stdout)
        self.assertIn("findings", parsed)
        self.assertIn("decision", parsed)
        self.assertIsInstance(parsed["findings"], list)
        self.assertIn(
            parsed["decision"], {"pass", "pass-with-minors", "fail"}
        )

    def test_invalid_decision_value_rejected(self) -> None:
        bad = (
            "<!-- argos:verifier-output -->\n"
            "tests_ran: true\n"
            "findings: []\n"
            "decision: maybe\n"
            "<!-- /argos:verifier-output -->\n"
        )
        result = _run_parser(bad)
        self.assertEqual(result.returncode, 2)
        self.assertIn("decision", result.stderr)

    def test_missing_test_run_cannot_be_pass(self) -> None:
        bad = (
            "<!-- argos:verifier-output -->\n"
            "tests_ran: false\n"
            "findings: []\n"
            "decision: pass\n"
            "<!-- /argos:verifier-output -->\n"
        )
        result = _run_parser(bad)
        self.assertEqual(result.returncode, 2)
        self.assertIn("tests_ran=false", result.stderr)


if __name__ == "__main__":
    unittest.main()
