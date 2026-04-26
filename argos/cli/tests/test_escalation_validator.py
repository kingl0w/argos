"""Tests for argos.cli.escalation_validator.

Stdlib `unittest` only — no pytest. Run from repo root:

    python3 -m unittest argos.cli.tests.test_escalation_validator -v
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

from argos.cli import escalation_validator


# This file lives at <repo>/argos/cli/tests/test_escalation_validator.py.
#   parents[0] -> <repo>/argos/cli/tests
#   parents[1] -> <repo>/argos/cli
#   parents[2] -> <repo>/argos
# The fixtures live at <repo>/argos/specs/v1.0/schemas/examples, so we use
# parents[2] / "specs" / ... (the Plan's parents[3] suggestion was off by
# one; see ARG1-040 implementation notes).
_FIXTURES = (
    pathlib.Path(__file__).resolve().parents[2]
    / "specs"
    / "v1.0"
    / "schemas"
    / "examples"
)
BLOCKING_FIXTURE = _FIXTURES / "escalation-blocking.md"
MALFORMED_FIXTURE = _FIXTURES / "escalation-malformed.md"


def _valid_frontmatter() -> dict[str, str]:
    return {
        "ticket_id": "ARG1-042",
        "session_id": "sess-2026-04-26T14:33:01Z-a1b2",
        "severity": "blocking",
        "raised_by": "orchestrator",
        "created": "2026-04-26T14:33:01Z",
    }


def _valid_body() -> str:
    return textwrap.dedent(
        """\
        ## Question
        One paragraph.

        ## Context
        Context paragraph.

        ## Options considered
        - A: option — tradeoff

        ## Why escalated
        Genuine ambiguity.
        """
    )


def _render(fm: dict[str, str], body: str) -> str:
    lines = ["---"]
    for key, value in fm.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    return "\n".join(lines)


class FixtureTests(unittest.TestCase):
    def test_blocking_example_validates(self) -> None:
        errors = escalation_validator.validate(BLOCKING_FIXTURE)
        self.assertEqual(errors, [], f"unexpected errors: {errors}")

    def test_malformed_example_fails_with_severity_error(self) -> None:
        errors = escalation_validator.validate(MALFORMED_FIXTURE)
        self.assertTrue(errors, "expected at least one error")
        self.assertTrue(
            any("severity" in e for e in errors),
            f"expected an error mentioning 'severity', got: {errors}",
        )


class CliExitCodeTests(unittest.TestCase):
    def _run(self, fixture: pathlib.Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "argos.cli.escalation_validator", str(fixture)],
            capture_output=True,
            text=True,
        )

    def test_main_exit_codes(self) -> None:
        ok = self._run(BLOCKING_FIXTURE)
        self.assertEqual(ok.returncode, 0, f"stderr={ok.stderr!r}")
        self.assertEqual(ok.stdout, "")

        bad = self._run(MALFORMED_FIXTURE)
        self.assertNotEqual(bad.returncode, 0)
        self.assertNotEqual(bad.stderr, "", "expected stderr on failure")
        self.assertIn("severity", bad.stderr)


class MissingRequiredFieldTests(unittest.TestCase):
    def test_missing_required_field_each(self) -> None:
        body = _valid_body()
        for omit in escalation_validator.REQUIRED_FRONTMATTER_KEYS:
            with self.subTest(omit=omit):
                fm = _valid_frontmatter()
                del fm[omit]
                with tempfile.TemporaryDirectory() as tmp:
                    path = pathlib.Path(tmp) / "f.md"
                    path.write_text(_render(fm, body), encoding="utf-8")
                    errors = escalation_validator.validate(path)
                self.assertTrue(
                    any(omit in e for e in errors),
                    f"expected error naming {omit!r}, got: {errors}",
                )


class MissingBodySectionTests(unittest.TestCase):
    def test_missing_each_body_section(self) -> None:
        for omit in escalation_validator.REQUIRED_BODY_SECTIONS:
            with self.subTest(omit=omit):
                body_lines = _valid_body().splitlines()
                # Drop the heading line and the paragraph beneath it so the
                # heading does not survive in another role.
                pruned: list[str] = []
                skip = False
                for line in body_lines:
                    if line.strip() == omit:
                        skip = True
                        continue
                    if skip:
                        # Skip until next H2 heading or blank-then-heading
                        # boundary; here we simply skip through to the next
                        # H2.
                        if line.startswith("## "):
                            skip = False
                            pruned.append(line)
                        continue
                    pruned.append(line)
                body = "\n".join(pruned)
                fm = _valid_frontmatter()
                with tempfile.TemporaryDirectory() as tmp:
                    path = pathlib.Path(tmp) / "f.md"
                    path.write_text(_render(fm, body), encoding="utf-8")
                    errors = escalation_validator.validate(path)
                self.assertTrue(
                    any(omit in e for e in errors),
                    f"expected error naming {omit!r}, got: {errors}",
                )


class InvalidEnumTests(unittest.TestCase):
    def test_invalid_severity_value(self) -> None:
        fm = _valid_frontmatter()
        fm["severity"] = "urgent"
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "f.md"
            path.write_text(_render(fm, _valid_body()), encoding="utf-8")
            errors = escalation_validator.validate(path)
        joined = "\n".join(errors)
        self.assertIn("severity", joined)
        self.assertIn("urgent", joined)

    def test_invalid_raised_by_value(self) -> None:
        fm = _valid_frontmatter()
        fm["raised_by"] = "human"
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "f.md"
            path.write_text(_render(fm, _valid_body()), encoding="utf-8")
            errors = escalation_validator.validate(path)
        joined = "\n".join(errors)
        self.assertIn("raised_by", joined)
        self.assertIn("human", joined)


if __name__ == "__main__":
    unittest.main()
