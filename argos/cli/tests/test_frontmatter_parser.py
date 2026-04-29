"""Tests for the ARG1-060 ``argos frontmatter-parse`` subcommand.

Runnable as::

    python3 -m unittest argos.cli.tests.test_frontmatter_parser -v

Stdlib only — no third-party dependencies.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

# Make ``argos.cli...`` importable when tests are invoked from anywhere.
# argos/cli/tests/test_frontmatter_parser.py
#   parents[3] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli.frontmatter_parser import (  # noqa: E402
    FrontmatterParseError,
    parse,
    parse_file,
)

_ARGOS_BIN = Path(__file__).resolve().parents[1] / "argos"
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "frontmatter"
_AGENT_DIR = _REPO_ROOT / "argos" / "specs" / "v1.0" / "agents"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    """Invoke the in-repo argos launcher with the given args."""
    return subprocess.run(
        [sys.executable, str(_ARGOS_BIN), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class StdlibOnlyTests(unittest.TestCase):
    """AC#1 — module imports only stdlib."""

    _PERMITTED = {"__future__", "argparse", "dataclasses", "enum", "json", "pathlib", "re", "sys", "typing"}

    def test_module_imports_only_permitted_stdlib(self) -> None:
        module_path = _REPO_ROOT / "argos" / "cli" / "frontmatter_parser.py"
        text = module_path.read_text(encoding="utf-8")
        offenders: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            m = re.match(r"^(?:from|import)\s+([A-Za-z_][A-Za-z0-9_.]*)", stripped)
            if not m:
                continue
            top_level = m.group(1).split(".")[0]
            if top_level not in self._PERMITTED:
                offenders.append(stripped)
        self.assertEqual(
            offenders, [],
            f"frontmatter_parser.py imports non-stdlib modules: {offenders}",
        )


class IntegrationAgentFrontmatterTests(unittest.TestCase):
    """AC#2 + AC#3 — parse the actual shipped agent definitions."""

    def test_orchestrator_frontmatter_parses(self) -> None:
        result = _run_cli("frontmatter-parse", str(_AGENT_DIR / "orchestrator.md"))
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        for key in ("name", "description", "allowed_tools", "denied_paths"):
            self.assertIn(key, data, f"missing key {key!r}: {data!r}")
        self.assertIsInstance(data["allowed_tools"], list)
        self.assertIsInstance(data["denied_paths"], list)
        self.assertEqual(data["name"], "orchestrator")

    def test_verifier_frontmatter_parses(self) -> None:
        result = _run_cli("frontmatter-parse", str(_AGENT_DIR / "verifier.md"))
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        for key in ("name", "description", "tools"):
            self.assertIn(key, data)
        self.assertEqual(data["name"], "verifier")


class HappyPathTests(unittest.TestCase):
    """AC#4 + AC#5 — quoted scalar with brace-glob, comments preserved as no-ops."""

    def test_quoted_glob_round_trips_verbatim(self) -> None:
        result = _run_cli("frontmatter-parse", str(_FIXTURES / "good-quoted.md"))
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["denied_paths"], ["**/*.{ts,py}"])

    def test_quoted_glob_braces_preserved_via_library(self) -> None:
        text = (_FIXTURES / "good-quoted.md").read_text(encoding="utf-8")
        data = parse(text)
        self.assertEqual(data["denied_paths"], ["**/*.{ts,py}"])

    def test_comments_are_no_ops(self) -> None:
        result = _run_cli("frontmatter-parse", str(_FIXTURES / "good-comments.md"))
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["name"], "orchestrator")
        self.assertEqual(data["description"], "a value")
        self.assertNotIn("# leading comment", json.dumps(data))
        self.assertNotIn("trailing comment", json.dumps(data))


class RejectionTests(unittest.TestCase):
    """AC#6 through AC#13 — every rejected feature exits 2 with a cited reason."""

    def _expect_rejection(self, fixture: str, reason_substring: str) -> str:
        result = _run_cli("frontmatter-parse", str(_FIXTURES / fixture))
        self.assertEqual(
            result.returncode, 2,
            f"expected exit 2; got {result.returncode}; stderr={result.stderr!r}",
        )
        self.assertRegex(
            result.stderr,
            r"^frontmatter-parse: line \d+: ",
            f"stderr does not match contract prefix: {result.stderr!r}",
        )
        self.assertIn(reason_substring, result.stderr)
        return result.stderr

    def test_flow_style_sequence_rejected(self) -> None:
        stderr = self._expect_rejection("flow-seq.md", "flow-style sequence not supported")
        self.assertRegex(stderr, r"^frontmatter-parse: line \d+: flow-style sequence not supported$")

    def test_flow_style_mapping_rejected(self) -> None:
        self._expect_rejection("flow-map.md", "flow-style mapping not supported")

    def test_multiline_pipe_rejected(self) -> None:
        self._expect_rejection("multiline-pipe.md", "multiline scalar indicator '|' not supported")

    def test_nested_mapping_rejected(self) -> None:
        self._expect_rejection("nested-deep.md", "nested mapping at depth 2 not supported")

    def test_anchor_rejected(self) -> None:
        self._expect_rejection("anchor.md", "anchor")

    def test_alias_rejected(self) -> None:
        self._expect_rejection("alias.md", "alias")

    def test_tag_rejected(self) -> None:
        self._expect_rejection("tag.md", "tag")

    def test_non_utf8_rejected(self) -> None:
        result = _run_cli("frontmatter-parse", str(_FIXTURES / "non-utf8.md"))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("input not valid UTF-8", result.stderr)


class FileNotFoundTests(unittest.TestCase):
    """AC#14 — missing file exits 1, not 2."""

    def test_missing_file_exits_1(self) -> None:
        result = _run_cli(
            "frontmatter-parse",
            "/nonexistent/argos/path/that/does/not/exist.md",
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("/nonexistent/argos/path/that/does/not/exist.md", result.stderr)
        self.assertIn("not found", result.stderr)


class RegistrationTests(unittest.TestCase):
    """AC#15 — subcommand visible in --help; --help on the subcommand works."""

    def test_top_level_help_lists_frontmatter_parse(self) -> None:
        result = _run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("frontmatter-parse", result.stdout)

    def test_subcommand_help_exits_zero(self) -> None:
        result = _run_cli("frontmatter-parse", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("frontmatter-parse", result.stdout)


class LibraryAPITests(unittest.TestCase):
    """Library-level checks not visible from CLI tests."""

    def test_parse_pure_frontmatter_no_delimiters(self) -> None:
        data = parse("name: foo\nbar: 42\n")
        self.assertEqual(data, {"name": "foo", "bar": 42})

    def test_parse_handles_bool_null_int(self) -> None:
        data = parse("a: true\nb: false\nc: null\nd: ~\ne: 7\nf: -3\n")
        self.assertEqual(data["a"], True)
        self.assertEqual(data["b"], False)
        self.assertIsNone(data["c"])
        self.assertIsNone(data["d"])
        self.assertEqual(data["e"], 7)
        self.assertEqual(data["f"], -3)

    def test_quoted_strings_are_not_coerced_to_bool(self) -> None:
        data = parse('a: "true"\nb: \'42\'\n')
        self.assertEqual(data["a"], "true")
        self.assertEqual(data["b"], "42")

    def test_unclosed_frontmatter_delimiter_raises(self) -> None:
        with self.assertRaises(FrontmatterParseError) as cm:
            parse("---\nname: x\n")
        self.assertEqual(cm.exception.line_no, 1)

    def test_double_quoted_escape_sequences(self) -> None:
        data = parse('a: "x\\ty"\nb: "say \\"hi\\""\nc: "back\\\\slash"\n')
        self.assertEqual(data["a"], "x\ty")
        self.assertEqual(data["b"], 'say "hi"')
        self.assertEqual(data["c"], "back\\slash")

    def test_unsupported_double_quote_escape_raises(self) -> None:
        with self.assertRaises(FrontmatterParseError):
            parse('a: "x\\qy"\n')

    def test_block_sequence_of_strings(self) -> None:
        data = parse("tools:\n  - Read\n  - Bash\n  - Grep\n")
        self.assertEqual(data["tools"], ["Read", "Bash", "Grep"])

    def test_parse_file_via_path(self) -> None:
        data = parse_file(_AGENT_DIR / "orchestrator.md")
        self.assertEqual(data["name"], "orchestrator")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
