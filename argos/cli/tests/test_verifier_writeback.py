"""Tests for argos.cli.verifier_writeback (ARG1-031).

Runnable as::

    python3 -m unittest argos.cli.tests.test_verifier_writeback -v

Stdlib only.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli.state_parser import parse_file  # noqa: E402
from argos.cli.verifier_writeback import (  # noqa: E402
    DECISION_PHASE,
    format_body,
)


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

## Known drift

_none_
"""


def _build_block_text(decision: str, findings_yaml: str, tests_ran: str = "true") -> str:
    return (
        "<!-- argos:verifier-output -->\n"
        f"tests_ran: {tests_ran}\n"
        f"findings:{findings_yaml}\n"
        f"decision: {decision}\n"
        "<!-- /argos:verifier-output -->\n"
    )


def _run_writeback(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "argos.cli", "verifier-writeback", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": str(_REPO_ROOT)},
    )


class FormatBodyTests(unittest.TestCase):
    def test_pass_body_contains_verified_and_ticket(self) -> None:
        body = format_body(
            parsed={"tests_ran": True, "findings": [], "decision": "pass"},
            ticket="ARG1-099",
            session="sess-test",
        )
        self.assertIn("verified", body)
        self.assertIn("ARG1-099", body)
        self.assertIn("Findings: 0 critical, 0 major, 0 minor", body)
        self.assertIn("Decision: pass", body)

    def test_pass_with_minors_lists_findings_and_counts(self) -> None:
        parsed = {
            "tests_ran": True,
            "findings": [
                {
                    "severity": "minor",
                    "description": "Unused import os",
                    "file": "src/foo.py:1",
                },
                {
                    "severity": "minor",
                    "description": "Trailing whitespace",
                    "file": "src/bar.py:42",
                },
            ],
            "decision": "pass-with-minors",
        }
        body = format_body(parsed=parsed, ticket="ARG1-099", session="sess-test")
        self.assertIn("verified-with-minors", body)
        self.assertIn("0 critical, 0 major, 2 minor", body)
        self.assertIn("src/foo.py:1", body)
        self.assertIn("src/bar.py:42", body)
        self.assertIn("Decision: pass-with-minors", body)

    def test_fail_body_embeds_test_stdout_verbatim(self) -> None:
        parsed = {
            "tests_ran": True,
            "findings": [
                {
                    "severity": "critical",
                    "description": "tests/test_x.py::test_y failed",
                    "file": "src/x.py:7",
                }
            ],
            "decision": "fail",
        }
        stdout = (
            "FAILED tests/test_x.py::test_y - "
            "AssertionError: expected 0, got None"
        )
        body = format_body(
            parsed=parsed,
            ticket="ARG1-099",
            session="sess-test",
            test_stdout=stdout,
        )
        self.assertIn("verification-failed", body)
        self.assertIn("Decision: fail", body)
        # AC#3 fragment grep must match.
        self.assertIn("AssertionError: expected 0, got None", body)


class WritebackCLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.workdir = Path(self.tmpdir.name)
        self.state_file = self.workdir / "STATE.md"
        self.state_file.write_text(_STATE_FIXTURE, encoding="utf-8")

    def _write_block(self, name: str, decision: str, findings_yaml: str,
                     tests_ran: str = "true") -> Path:
        block_path = self.workdir / name
        block_path.write_text(
            _build_block_text(decision, findings_yaml, tests_ran),
            encoding="utf-8",
        )
        return block_path

    def _state_text(self) -> str:
        return self.state_file.read_text(encoding="utf-8")

    def _new_block_for_ticket(self, ticket: str):
        blocks = parse_file(self.state_file)
        for block in blocks:
            if block.ticket == ticket:
                return block
        raise AssertionError(f"no block for {ticket} after writeback")

    # AC#1 — pass case writes a block with author=verifier, ticket id, "verified".
    def test_ac1_pass_writes_verified_block(self) -> None:
        block_path = self._write_block(
            "v.txt", decision="pass", findings_yaml=" []"
        )
        result = _run_writeback(
            [
                "--input", str(block_path),
                "--ticket", "ARG1-031",
                "--session", "sess-ac1",
                "--suffix", "verify",
                "--state-file", str(self.state_file),
            ],
            cwd=self.workdir,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)

        text = self._state_text()
        # AC#1 regex contract: <!-- argos:entry .* author=verifier .* -->
        # containing the literal `verified` and the ticket ID.
        opens = re.findall(
            r"<!-- argos:entry [^>]*author=verifier[^>]*-->", text
        )
        self.assertTrue(
            any("ARG1-031" in tag for tag in opens),
            msg=f"no verifier-authored ARG1-031 entry; opens={opens!r}",
        )
        # Locate the new block and assert it contains literal "verified".
        block = self._new_block_for_ticket("ARG1-031")
        self.assertIn("verified", block.body)
        self.assertIn("ARG1-031", block.id)

    # AC#2 — pass-with-minors with two minor findings.
    def test_ac2_pass_with_minors_lists_findings_and_counts(self) -> None:
        findings_yaml = (
            "\n"
            "  - severity: minor\n"
            "    description: \"Unused import\"\n"
            "    file: src/foo.py:7\n"
            "  - severity: minor\n"
            "    description: \"Trailing whitespace\"\n"
            "    file: src/bar.py:11\n"
        )
        block_path = self._write_block(
            "v.txt", decision="pass-with-minors", findings_yaml=findings_yaml
        )
        result = _run_writeback(
            [
                "--input", str(block_path),
                "--ticket", "ARG1-031",
                "--session", "sess-ac2",
                "--suffix", "verify",
                "--state-file", str(self.state_file),
            ],
            cwd=self.workdir,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)

        block = self._new_block_for_ticket("ARG1-031")
        self.assertIn("verified-with-minors", block.body)
        self.assertIn("src/foo.py:7", block.body)
        self.assertIn("src/bar.py:11", block.body)
        self.assertIn("0 critical, 0 major, 2 minor", block.body)

    # AC#3 — fail with one critical, body contains literal "verification-failed"
    # and a known test-stdout fragment is grep-discoverable.
    def test_ac3_fail_embeds_test_stdout_verbatim(self) -> None:
        findings_yaml = (
            "\n"
            "  - severity: critical\n"
            "    description: \"tests/test_x.py::test_y failed\"\n"
            "    file: src/x.py:42\n"
        )
        block_path = self._write_block(
            "v.txt", decision="fail", findings_yaml=findings_yaml
        )
        stdout_path = self.workdir / "stdout.txt"
        stdout_fragment = "AssertionError: expected 0, got None"
        stdout_path.write_text(
            f"FAILED tests/test_x.py::test_y - {stdout_fragment}\n",
            encoding="utf-8",
        )

        result = _run_writeback(
            [
                "--input", str(block_path),
                "--ticket", "ARG1-031",
                "--session", "sess-ac3",
                "--suffix", "verify",
                "--state-file", str(self.state_file),
                "--stdout-file", str(stdout_path),
            ],
            cwd=self.workdir,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)

        block = self._new_block_for_ticket("ARG1-031")
        self.assertIn("verification-failed", block.body)
        # Grep the verbatim fragment via subprocess to mirror the AC contract.
        grep = subprocess.run(
            ["grep", "-Fc", stdout_fragment, str(self.state_file)],
            capture_output=True, text=True,
        )
        self.assertEqual(grep.returncode, 0, msg=grep.stderr)
        self.assertGreaterEqual(int(grep.stdout.strip()), 1)

    # AC#4 — verifier never invokes a write tool other than `argos state-append`.
    # Verified at code level: the writeback wrapper calls append_block (the
    # ARG1-051 helper) and never opens STATE.md for write directly. The agent
    # prompt's `tools:` allowlist excludes Edit/Write entirely.
    def test_ac4_writeback_uses_only_state_append(self) -> None:
        wb_src = (
            _REPO_ROOT / "argos" / "cli" / "verifier_writeback.py"
        ).read_text(encoding="utf-8")
        self.assertIn("from argos.cli.state_append import", wb_src)
        self.assertIn("append_block", wb_src)
        # No direct STATE.md writes — neither Path.write_text nor open(...,"w")
        # targeting a STATE.md path appears in the wrapper source.
        self.assertNotRegex(wb_src, r"STATE\.md.*write_text|write_text.*STATE\.md")
        self.assertNotRegex(wb_src, r"open\([^)]*STATE\.md[^)]*['\"]w")

        # The verifier agent's tool allowlist must not include Edit or Write —
        # that's what enforces "no write tool other than argos state-append" at
        # session level.
        agent_src = (
            _REPO_ROOT / ".claude" / "agents" / "verifier.md"
        ).read_text(encoding="utf-8")
        # Frontmatter `tools:` line.
        m = re.search(r"^tools:\s*(.+)$", agent_src, flags=re.MULTILINE)
        self.assertIsNotNone(m, msg="verifier agent missing tools: line")
        allowed = {t.strip() for t in m.group(1).split(",")}
        self.assertNotIn("Edit", allowed)
        self.assertNotIn("Write", allowed)
        self.assertNotIn("NotebookEdit", allowed)

    # AC#5 — agent prompt contains the literal `argos state-append`.
    def test_ac5_agent_prompt_invokes_state_append(self) -> None:
        agent_src = (
            _REPO_ROOT / ".claude" / "agents" / "verifier.md"
        ).read_text(encoding="utf-8")
        mirror_src = (
            _REPO_ROOT / "argos" / "specs" / "v1.0" / "agents" / "verifier.md"
        ).read_text(encoding="utf-8")
        self.assertIn("argos state-append", agent_src)
        self.assertIn("argos state-append", mirror_src)
        # And the canonical mirror is byte-identical.
        self.assertEqual(agent_src, mirror_src)

    # AC#6 — two concurrent verifier writes (different tickets) both land,
    # neither overwritten.
    def test_ac6_concurrent_writes_both_land(self) -> None:
        block_a = self._write_block(
            "a.txt", decision="pass", findings_yaml=" []"
        )
        block_b = self._write_block(
            "b.txt", decision="pass", findings_yaml=" []"
        )

        results: dict[str, subprocess.CompletedProcess] = {}

        def run(label: str, ticket: str, block: Path) -> None:
            results[label] = _run_writeback(
                [
                    "--input", str(block),
                    "--ticket", ticket,
                    "--session", f"sess-{label}",
                    "--suffix", "verify",
                    "--state-file", str(self.state_file),
                ],
                cwd=self.workdir,
            )

        threads = [
            threading.Thread(
                target=run, args=("a", "ARG1-AAA", block_a)
            ),
            threading.Thread(
                target=run, args=("b", "ARG1-BBB", block_b)
            ),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for label, result in results.items():
            self.assertEqual(
                result.returncode, 0, msg=f"{label}: {result.stderr}"
            )

        blocks = parse_file(self.state_file)
        ids = [b.id for b in blocks]
        tickets = [b.ticket for b in blocks]
        self.assertEqual(len(ids), len(set(ids)), msg="duplicate ids")
        self.assertIn("ARG1-AAA", tickets)
        self.assertIn("ARG1-BBB", tickets)


if __name__ == "__main__":
    unittest.main()
