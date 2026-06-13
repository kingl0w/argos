"""Tests for ARG1-069 ``session_prompt`` (headless dispatch prompt builder).

The builder is pure — these tests never invoke a live ``claude``. ADR-001 /
ADR-002: stdlib only, no third-party imports.

Runnable as::

    python3 -m unittest argos.cli.tests.test_session_prompt -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli.orchestrator import session_prompt  # noqa: E402


_FIXTURE_TICKET = """\
---
id: ARG1-099
title: A fixture ticket for prompt-builder tests
status: ready
files_touched: [argos/cli/example.py]
---

## Context

Some context paragraph that should survive into the prompt verbatim.

## Acceptance criteria

- [ ] AC#1: the widget frobnicates the sprocket.
- [ ] AC#2: argos lint-imports argos/ exits 0.

## Non-goals

- Not boiling the ocean.
"""


# Tokens each standing rule must surface so downstream consumers / tests can
# grep them. One per AC#1 rule.
_RULE_TOKENS = (
    "ADR-001",
    "ADR-002",
    "argos state-append",
    "STATE.md",
    "do not merge",  # case-insensitive check below
    "argos/specs/v1.0/schemas/escalation.md",
)


class BuildPromptTests(unittest.TestCase):
    """Pure :func:`session_prompt.build_prompt` behavior."""

    def test_contains_ticket_id(self) -> None:
        prompt = session_prompt.build_prompt("ARG1-099", _FIXTURE_TICKET)
        self.assertIn("ARG1-099", prompt)

    def test_contains_full_ticket_text(self) -> None:
        prompt = session_prompt.build_prompt("ARG1-099", _FIXTURE_TICKET)
        # The ticket body is inlined verbatim — spot-check distinctive lines.
        self.assertIn("the widget frobnicates the sprocket", prompt)
        self.assertIn("AC#2: argos lint-imports argos/ exits 0.", prompt)
        self.assertIn("Some context paragraph", prompt)

    def test_contains_each_standing_rule(self) -> None:
        prompt = session_prompt.build_prompt("ARG1-099", _FIXTURE_TICKET)
        lowered = prompt.lower()
        for token in _RULE_TOKENS:
            self.assertIn(token.lower(), lowered, f"missing rule token: {token!r}")
        # Every rule string itself is present.
        for rule in session_prompt.STANDING_RULES:
            self.assertIn(rule, prompt)

    def test_instructs_read_and_implement(self) -> None:
        prompt = session_prompt.build_prompt("ARG1-099", _FIXTURE_TICKET)
        lowered = prompt.lower()
        self.assertIn("implement", lowered)
        self.assertIn("ticket", lowered)

    def test_blank_text_degrades_to_read_instruction(self) -> None:
        prompt = session_prompt.build_prompt(
            "ARG1-099", "", ticket_path=Path("/wt/argos/specs/v1.0/tickets")
        )
        # Falls back to a read-the-file instruction; still carries id + rules.
        self.assertIn("ARG1-099", prompt)
        self.assertIn("/wt/argos/specs/v1.0/tickets", prompt)
        for rule in session_prompt.STANDING_RULES:
            self.assertIn(rule, prompt)

    def test_none_text_degrades_without_path(self) -> None:
        prompt = session_prompt.build_prompt("ARG1-099", None)
        self.assertIn("ARG1-099", prompt)
        self.assertIn("argos/specs/v1.0/tickets/", prompt)

    def test_empty_ticket_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            session_prompt.build_prompt("")


class BuildPromptForTicketTests(unittest.TestCase):
    """I/O wrapper :func:`session_prompt.build_prompt_for_ticket`."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.ticket_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_reads_and_inlines_located_ticket(self) -> None:
        # Named `{id}-{slug}.md` per the project convention.
        (self.ticket_dir / "ARG1-099-fixture.md").write_text(
            _FIXTURE_TICKET, encoding="utf-8"
        )
        prompt = session_prompt.build_prompt_for_ticket(
            "ARG1-099", ticket_dir=self.ticket_dir
        )
        self.assertIn("ARG1-099", prompt)
        self.assertIn("the widget frobnicates the sprocket", prompt)
        for rule in session_prompt.STANDING_RULES:
            self.assertIn(rule, prompt)

    def test_missing_ticket_file_degrades_gracefully(self) -> None:
        # No file written — must not raise; degrades to read-the-file prompt.
        prompt = session_prompt.build_prompt_for_ticket(
            "ARG1-099", ticket_dir=self.ticket_dir
        )
        self.assertIn("ARG1-099", prompt)
        self.assertIn(str(self.ticket_dir), prompt)
        for rule in session_prompt.STANDING_RULES:
            self.assertIn(rule, prompt)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
