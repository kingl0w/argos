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


# A distinctive marker so conventions-inlining tests can assert verbatim
# inclusion without colliding with any contract-rule text.
_FIXTURE_CONVENTIONS = (
    "## Language\n\n- CONV-MARKER: implementation is Fortran 77 only.\n"
)


# Tokens each Argos-contract rule must surface so downstream consumers / tests
# can grep them. The ADR-001 / ADR-002 (language / stdlib) rules are no longer
# contract rules — they are target conventions sourced from
# ``argos/conventions.md`` (see ConventionsFileTests), so they must NOT appear
# here.
_RULE_TOKENS = (
    "argos state-append",
    "STATE.md",
    "do not merge",  # case-insensitive check below
    "argos/specs/v1.0/schemas/escalation.md",
)


class ContractRulesTests(unittest.TestCase):
    """Invariants on :data:`session_prompt.CONTRACT_RULES`."""

    def test_only_the_four_contract_rules_remain(self) -> None:
        # The two ADR/language rules were removed; the four argos-contract
        # rules (verify, state-append, push-don't-merge, escalate) remain.
        self.assertEqual(len(session_prompt.CONTRACT_RULES), 4)

    def test_contract_rules_carry_no_adr_tokens(self) -> None:
        joined = "\n".join(session_prompt.CONTRACT_RULES)
        self.assertNotIn("ADR-001", joined)
        self.assertNotIn("ADR-002", joined)
        # And no leftover stdlib/language framing.
        self.assertNotIn("standard library only", joined)


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

    def test_contains_each_contract_rule(self) -> None:
        prompt = session_prompt.build_prompt("ARG1-099", _FIXTURE_TICKET)
        lowered = prompt.lower()
        for token in _RULE_TOKENS:
            self.assertIn(token.lower(), lowered, f"missing rule token: {token!r}")
        # Every rule string itself is present.
        for rule in session_prompt.CONTRACT_RULES:
            self.assertIn(rule, prompt)

    def test_no_conventions_omits_section(self) -> None:
        # target_conventions=None (the default) → no conventions section.
        prompt = session_prompt.build_prompt("ARG1-099", _FIXTURE_TICKET)
        self.assertNotIn("Target conventions", prompt)
        # Explicit None and blank/whitespace behave the same.
        self.assertNotIn(
            "Target conventions",
            session_prompt.build_prompt(
                "ARG1-099", _FIXTURE_TICKET, target_conventions=None
            ),
        )
        self.assertNotIn(
            "Target conventions",
            session_prompt.build_prompt(
                "ARG1-099", _FIXTURE_TICKET, target_conventions="   \n  "
            ),
        )

    def test_conventions_included_verbatim(self) -> None:
        prompt = session_prompt.build_prompt(
            "ARG1-099", _FIXTURE_TICKET, target_conventions=_FIXTURE_CONVENTIONS
        )
        self.assertIn("Target conventions (from this repo):", prompt)
        self.assertIn("CONV-MARKER: implementation is Fortran 77 only.", prompt)
        # Conventions are inlined ahead of the contract rules.
        self.assertLess(
            prompt.index("CONV-MARKER"),
            prompt.index("Standing rules"),
        )

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
        for rule in session_prompt.CONTRACT_RULES:
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
        self.target_root = Path(self._tmp.name)
        self.ticket_dir = self.target_root / "argos" / "specs" / "v1.0" / "tickets"
        self.ticket_dir.mkdir(parents=True)
        self.conventions = self.target_root / "argos" / "conventions.md"
        self.conventions.write_text(
            "## Language\n\n- CONV-MARKER: stdlib only.\n", encoding="utf-8"
        )
        self.esc_dir = self.target_root / "argos" / "specs" / "escalations"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_reads_and_inlines_located_ticket(self) -> None:
        # Named `{id}-{slug}.md` per the project convention.
        (self.ticket_dir / "ARG1-099-fixture.md").write_text(
            _FIXTURE_TICKET, encoding="utf-8"
        )
        prompt = session_prompt.build_prompt_for_ticket(
            "ARG1-099", ticket_dir=self.ticket_dir, target_root=self.target_root
        )
        self.assertIn("ARG1-099", prompt)
        self.assertIn("the widget frobnicates the sprocket", prompt)
        # Target conventions are sourced from the repo and inlined.
        self.assertIn("Target conventions (from this repo):", prompt)
        self.assertIn("CONV-MARKER: stdlib only.", prompt)
        for rule in session_prompt.CONTRACT_RULES:
            self.assertIn(rule, prompt)

    def test_missing_ticket_file_degrades_gracefully(self) -> None:
        # No ticket file written, but conventions present — must not raise;
        # degrades to read-the-file prompt and still carries conventions.
        prompt = session_prompt.build_prompt_for_ticket(
            "ARG1-099", ticket_dir=self.ticket_dir, target_root=self.target_root
        )
        self.assertIn("ARG1-099", prompt)
        self.assertIn(str(self.ticket_dir), prompt)
        self.assertIn("CONV-MARKER: stdlib only.", prompt)
        for rule in session_prompt.CONTRACT_RULES:
            self.assertIn(rule, prompt)

    def test_missing_conventions_escalates(self) -> None:
        self.conventions.unlink()
        with self.assertRaises(session_prompt.MissingConventionsError) as ctx:
            session_prompt.build_prompt_for_ticket(
                "ARG1-099",
                ticket_dir=self.ticket_dir,
                target_root=self.target_root,
            )
        err = ctx.exception
        self.assertEqual(err.ticket_id, "ARG1-099")
        # A blocking escalation was written to the default escalations dir.
        self.assertTrue(err.escalation_path.exists())
        self.assertEqual(err.escalation_path.parent, self.esc_dir)
        text = err.escalation_path.read_text(encoding="utf-8")
        self.assertIn("severity: blocking", text)
        self.assertIn("raised_by: orchestrator", text)
        self.assertIn("ARG1-099", text)

    def test_empty_conventions_escalates(self) -> None:
        self.conventions.write_text("   \n\n", encoding="utf-8")
        with self.assertRaises(session_prompt.MissingConventionsError):
            session_prompt.build_prompt_for_ticket(
                "ARG1-099",
                ticket_dir=self.ticket_dir,
                target_root=self.target_root,
            )

    def test_escalation_dir_override_is_honored(self) -> None:
        self.conventions.unlink()
        override = self.target_root / "custom-esc"
        with self.assertRaises(session_prompt.MissingConventionsError) as ctx:
            session_prompt.build_prompt_for_ticket(
                "ARG1-099",
                ticket_dir=self.ticket_dir,
                target_root=self.target_root,
                escalation_dir=override,
            )
        self.assertEqual(ctx.exception.escalation_path.parent, override)


class ConventionsFileTests(unittest.TestCase):
    """argos's own ``argos/conventions.md`` is the new home for the ADR rules.

    The ADR-001 / ADR-002 language+stdlib rules that used to live in
    ``STANDING_RULES`` now live here; any consumer that greps for those tokens
    points at this file rather than the prompt builder.
    """

    def test_conventions_file_carries_adr_tokens(self) -> None:
        conventions = _REPO_ROOT / "argos" / "conventions.md"
        self.assertTrue(conventions.is_file(), conventions)
        text = conventions.read_text(encoding="utf-8")
        self.assertIn("ADR-001", text)
        self.assertIn("ADR-002", text)
        self.assertIn("standard library only", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
